#!/usr/bin/env python3
"""
Migrate DNS from AWS Route53 to Cloudflare.

Usage:
  python r53_toCf.py example.com
  python r53_toCf.py example.com --dry-run
  python r53_toCf.py example.com --skip-nameserver-update
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

import boto3
import requests

CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"

SKIP_TYPES = {"NS", "SOA"}

ALIAS_SKIP_PREFIXES = (
    "dualstack.",
    "s3-website",
)


class MigrationError(Exception):
    pass


DNS_PERMISSIONS_HINT = (
    "Your Cloudflare API token needs DNS permissions for this zone. "
    "Edit the token at https://dash.cloudflare.com/profile/api-tokens and add:\n"
    "  - Zone > DNS > Read\n"
    "  - Zone > DNS > Edit\n"
    "Also ensure the token is scoped to this zone (or All zones)."
)


def cf_headers() -> dict[str, str]:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not token:
        raise MigrationError("CLOUDFLARE_API_TOKEN environment variable is required")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def cf_request(method: str, path: str, **kwargs) -> dict[str, Any]:
    resp = requests.request(
        method,
        f"{CLOUDFLARE_API}{path}",
        headers=cf_headers(),
        timeout=60,
        **kwargs,
    )
    try:
        data = resp.json()
    except requests.JSONDecodeError as e:
        raise MigrationError(
            f"Cloudflare API returned non-JSON response (HTTP {resp.status_code})"
        ) from e

    if not data.get("success"):
        errors = data.get("errors", data)
        if _is_auth_error(errors, resp.status_code):
            raise MigrationError(f"Cloudflare authentication failed: {errors}\n\n{DNS_PERMISSIONS_HINT}")
        raise MigrationError(f"Cloudflare API error ({method} {path}): {errors}")
    return data


def _is_auth_error(errors: Any, status_code: int) -> bool:
    if status_code in (401, 403):
        return True
    if isinstance(errors, list):
        return any(e.get("code") == 10000 for e in errors if isinstance(e, dict))
    return False


def get_or_create_cloudflare_zone(
    domain: str, account_id: str | None
) -> tuple[str, list[str]]:
    """Return (zone_id, nameservers), creating the zone if needed."""
    existing = cf_request("GET", f"/zones?name={domain}")
    results = existing.get("result", [])
    if results:
        zone = results[0]
        print(f"   Using existing zone (status: {zone.get('status', 'unknown')})")
    else:
        body: dict[str, Any] = {"name": domain, "jump_start": False}
        if account_id:
            body["account"] = {"id": account_id}
        data = cf_request("POST", "/zones", json=body)
        zone = data["result"]

    zone_id = zone["id"]
    nameservers = zone.get("name_servers") or []
    if not nameservers:
        raise MigrationError(f"No nameservers returned for zone {zone_id}")
    return zone_id, nameservers


def find_route53_hosted_zone(route53, domain: str, hosted_zone_id: str | None) -> str:
    if hosted_zone_id:
        return hosted_zone_id

    paginator = route53.get_paginator("list_hosted_zones")
    matches = []
    for page in paginator.paginate():
        for zone in page["HostedZones"]:
            name = zone["Name"].rstrip(".")
            if name == domain:
                matches.append(zone)

    if not matches:
        raise MigrationError(f"No Route53 hosted zone found for {domain}")
    if len(matches) > 1:
        raise MigrationError(
            f"Multiple hosted zones match {domain}; pass --hosted-zone-id"
        )
    return matches[0]["Id"].split("/")[-1]


def list_route53_records(route53, hosted_zone_id: str) -> list[dict]:
    records = []
    paginator = route53.get_paginator("list_resource_record_sets")
    for page in paginator.paginate(HostedZoneId=hosted_zone_id):
        records.extend(page["ResourceRecordSets"])
    return records


def route53_name_to_cloudflare(name: str, domain: str) -> str:
    name = name.rstrip(".")
    domain = domain.rstrip(".")
    if name == domain:
        return domain
    suffix = f".{domain}"
    if name.endswith(suffix):
        return name[: -len(suffix)]
    return name


def convert_route53_record(record: dict, domain: str) -> dict[str, Any] | None:
    rtype = record["Type"]
    if rtype in SKIP_TYPES:
        return None

    name = route53_name_to_cloudflare(record["Name"], domain)
    ttl = record.get("TTL", 300)

    if "AliasTarget" in record:
        target = record["AliasTarget"]["DNSName"].rstrip(".")
        if any(target.startswith(p) for p in ALIAS_SKIP_PREFIXES):
            print(f"  SKIP alias {record['Name']} -> {target} (manual review needed)")
            return None
        print(f"  WARN alias {record['Name']} -> CNAME {target}")
        return {
            "type": "CNAME",
            "name": name,
            "content": target,
            "ttl": 1 if ttl == 0 else min(ttl, 86400),
            "proxied": False,
        }

    values = [rr["Value"] for rr in record.get("ResourceRecords", [])]

    if rtype == "TXT":
        content = "".join(v.strip('"') for v in values)
        return {
            "type": "TXT",
            "name": name,
            "content": content,
            "ttl": min(ttl, 86400),
            "proxied": False,
        }

    if rtype == "MX":
        payloads = []
        for value in values:
            priority, host = value.split(" ", 1)
            payloads.append(
                {
                    "type": "MX",
                    "name": name,
                    "content": host.rstrip("."),
                    "priority": int(priority),
                    "ttl": min(ttl, 86400),
                    "proxied": False,
                }
            )
        return {"_multi": payloads}

    if rtype == "CAA":
        payloads = [
            {
                "type": "CAA",
                "name": name,
                "content": v.strip('"'),
                "ttl": min(ttl, 86400),
                "proxied": False,
            }
            for v in values
        ]
        return {"_multi": payloads}

    if len(values) != 1:
        print(f"  SKIP {rtype} {name}: multiple RRs not handled ({len(values)} values)")
        return None

    content = values[0].rstrip(".")
    payload: dict[str, Any] = {
        "type": rtype,
        "name": name,
        "content": content,
        "ttl": min(ttl, 86400),
        "proxied": False,
    }

    if rtype == "SRV":
        parts = content.split()
        if len(parts) == 4:
            payload["data"] = {
                "priority": int(parts[0]),
                "weight": int(parts[1]),
                "port": int(parts[2]),
                "target": parts[3].rstrip("."),
            }
            del payload["content"]

    return payload


def list_cloudflare_records(zone_id: str) -> list[dict]:
    records = []
    page = 1
    while True:
        data = cf_request(
            "GET",
            f"/zones/{zone_id}/dns_records",
            params={"per_page": 100, "page": page},
        )
        records.extend(data["result"])
        info = data.get("result_info", {})
        if page >= info.get("total_pages", 1):
            break
        page += 1
    return records


def record_key(payload: dict) -> tuple:
    return (payload["type"], payload.get("name", ""), payload.get("content", ""))


def import_records_to_cloudflare(
    zone_id: str,
    route53_records: list[dict],
    domain: str,
    dry_run: bool,
) -> None:
    # Always probe DNS API access so dry-run catches missing DNS:Read permission.
    existing = list_cloudflare_records(zone_id)
    existing_keys = {
        (r["type"], r["name"], r.get("content", "")) for r in existing
    }

    created = skipped = failed = 0

    for record in route53_records:
        converted = convert_route53_record(record, domain)
        if converted is None:
            skipped += 1
            continue

        payloads = converted.get("_multi", [converted])

        for payload in payloads:
            label = f"{payload['type']} {payload.get('name', '@')}"
            key = record_key(payload)

            if key in existing_keys:
                print(f"  exists  {label}")
                skipped += 1
                continue

            if dry_run:
                print(
                    f"  [dry-run] would create {label} -> "
                    f"{payload.get('content', payload.get('data'))}"
                )
                created += 1
                continue

            try:
                cf_request("POST", f"/zones/{zone_id}/dns_records", json=payload)
                print(f"  created {label}")
                existing_keys.add(key)
                created += 1
                time.sleep(0.2)
            except MigrationError as e:
                print(f"  FAILED {label}: {e}")
                failed += 1

    print(f"\nImport summary: {created} created, {skipped} skipped, {failed} failed")


def update_route53_domain_nameservers(
    domains_client,
    domain: str,
    nameservers: list[str],
    dry_run: bool,
) -> None:
    detail = domains_client.get_domain_detail(DomainName=domain)
    current = [ns["Name"] for ns in detail.get("Nameservers", [])]

    if sorted(current) == sorted(nameservers):
        print("Nameservers already set to Cloudflare values.")
        return

    print(f"Current registrar NS: {current}")
    print(f"New Cloudflare NS:    {nameservers}")

    if dry_run:
        print("[dry-run] would update domain nameservers")
        return

    domains_client.update_domain_nameservers(
        DomainName=domain,
        Nameservers=[{"Name": ns} for ns in nameservers],
    )
    print("Registrar nameservers updated.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate DNS from Route53 to Cloudflare"
    )
    parser.add_argument("domain", help="Domain name, e.g. example.com")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument(
        "--skip-nameserver-update",
        action="store_true",
        help="Import records only; do not change registrar NS",
    )
    parser.add_argument(
        "--hosted-zone-id",
        help="Route53 hosted zone ID (without /hostedzone/ prefix)",
    )
    parser.add_argument(
        "--account-id",
        default=os.environ.get("CLOUDFLARE_ACCOUNT_ID"),
        help="Cloudflare account ID (optional)",
    )
    args = parser.parse_args()

    domain = args.domain.lower().strip(".")
    route53 = boto3.client("route53")
    domains_client = boto3.client("route53domains", region_name="us-east-1")

    print(f"=== Migrating {domain} ===\n")

    print("1. Creating Cloudflare zone...")
    zone_id, cf_nameservers = get_or_create_cloudflare_zone(domain, args.account_id)
    print(f"   Zone ID: {zone_id}")
    print(f"   Nameservers: {', '.join(cf_nameservers)}\n")

    print("2. Importing records from Route53...")
    hosted_zone_id = find_route53_hosted_zone(
        route53, domain, args.hosted_zone_id
    )
    print(f"   Hosted zone: {hosted_zone_id}")
    records = list_route53_records(route53, hosted_zone_id)
    import_records_to_cloudflare(zone_id, records, domain, args.dry_run)
    print()

    if args.skip_nameserver_update:
        print("3. Skipping nameserver update (--skip-nameserver-update)")
    else:
        print("3. Updating nameservers at AWS domain registration...")
        try:
            update_route53_domain_nameservers(
                domains_client, domain, cf_nameservers, args.dry_run
            )
        except domains_client.exceptions.InvalidInput as e:
            raise MigrationError(
                f"Could not update nameservers via Route53 Domains: {e}\n"
                "If the domain is registered elsewhere, update NS at that registrar manually."
            ) from e

    print("\nDone.")
    if not args.dry_run and not args.skip_nameserver_update:
        print("DNS propagation may take up to 48 hours (usually much less).")
        print("Verify records in the Cloudflare dashboard before relying on production traffic.")


if __name__ == "__main__":
    try:
        main()
    except MigrationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
