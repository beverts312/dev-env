"""Route53 -> Cloudflare DNS migration (replaces scripts/r53_to_cf.py).

Cloudflare auth uses the CLOUDFLARE_API_TOKEN env var; AWS uses the standard
credential chain.
"""

from __future__ import annotations

import os
import time
from typing import Any

import click

CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"
TOKEN_ENV = "CLOUDFLARE_API_TOKEN"

SKIP_TYPES = {"NS", "SOA"}
ALIAS_SKIP_PREFIXES = ("dualstack.", "s3-website")
MAX_TTL = 86400

DNS_PERMISSIONS_HINT = (
    "Your Cloudflare API token needs DNS permissions for this zone. "
    "Edit the token at https://dash.cloudflare.com/profile/api-tokens and add:\n"
    "  - Zone > DNS > Read\n"
    "  - Zone > DNS > Edit\n"
    "Also ensure the token is scoped to this zone (or All zones)."
)
EXTRA_HINT = "install be with the dns extra: uv tool install --editable './be[dns]'"


def _requests():
    try:
        import requests
    except ImportError:
        raise click.ClickException(f"requests is not installed; {EXTRA_HINT}") from None
    return requests


def boto3_client(name: str, **kwargs: Any):
    try:
        import boto3
    except ImportError:
        raise click.ClickException(f"boto3 is not installed; {EXTRA_HINT}") from None
    return boto3.client(name, **kwargs)


# Cloudflare


def cf_headers() -> dict[str, str]:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise click.ClickException(f"{TOKEN_ENV} environment variable is required")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _is_auth_error(errors: Any, status_code: int) -> bool:
    if status_code in (401, 403):
        return True
    if isinstance(errors, list):
        return any(e.get("code") == 10000 for e in errors if isinstance(e, dict))
    return False


def cf_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    requests = _requests()
    resp = requests.request(
        method, f"{CLOUDFLARE_API}{path}", headers=cf_headers(), timeout=60, **kwargs
    )
    try:
        data = resp.json()
    except requests.JSONDecodeError:
        raise click.ClickException(
            f"Cloudflare API returned non-JSON response (HTTP {resp.status_code})"
        ) from None

    if not data.get("success"):
        errors = data.get("errors", data)
        if _is_auth_error(errors, resp.status_code):
            raise click.ClickException(
                f"Cloudflare authentication failed: {errors}\n\n{DNS_PERMISSIONS_HINT}"
            )
        raise click.ClickException(f"Cloudflare API error ({method} {path}): {errors}")
    return data


def find_cloudflare_zone(domain: str) -> dict | None:
    results = cf_request("GET", "/zones", params={"name": domain}).get("result", [])
    return results[0] if results else None


def create_cloudflare_zone(domain: str, account_id: str | None) -> dict:
    body: dict[str, Any] = {"name": domain, "jump_start": False}
    if account_id:
        body["account"] = {"id": account_id}
    return cf_request("POST", "/zones", json=body)["result"]


def list_cloudflare_records(zone_id: str) -> list[dict]:
    records = []
    page = 1
    while True:
        data = cf_request(
            "GET", f"/zones/{zone_id}/dns_records", params={"per_page": 100, "page": page}
        )
        records.extend(data["result"])
        if page >= data.get("result_info", {}).get("total_pages", 1):
            break
        page += 1
    return records


# Route53


def find_route53_hosted_zone(route53, domain: str, hosted_zone_id: str | None) -> str:
    if hosted_zone_id:
        return hosted_zone_id
    matches = [
        zone
        for page in route53.get_paginator("list_hosted_zones").paginate()
        for zone in page["HostedZones"]
        if zone["Name"].rstrip(".") == domain
    ]
    if not matches:
        raise click.ClickException(f"no Route53 hosted zone found for {domain}")
    if len(matches) > 1:
        raise click.ClickException(f"multiple hosted zones match {domain}; pass --hosted-zone-id")
    return matches[0]["Id"].split("/")[-1]


def list_route53_records(route53, hosted_zone_id: str) -> list[dict]:
    records = []
    for page in route53.get_paginator("list_resource_record_sets").paginate(
        HostedZoneId=hosted_zone_id
    ):
        records.extend(page["ResourceRecordSets"])
    return records


def update_registrar_nameservers(domains_client, domain: str, nameservers: list[str], dry_run: bool) -> None:
    detail = domains_client.get_domain_detail(DomainName=domain)
    current = [ns["Name"] for ns in detail.get("Nameservers", [])]
    if sorted(current) == sorted(nameservers):
        click.echo("Nameservers already set to Cloudflare values.")
        return

    click.echo(f"Current registrar NS: {current}")
    click.echo(f"New Cloudflare NS:    {nameservers}")
    if dry_run:
        click.echo("[dry-run] would update domain nameservers")
        return
    domains_client.update_domain_nameservers(
        DomainName=domain, Nameservers=[{"Name": ns} for ns in nameservers]
    )
    click.echo("Registrar nameservers updated.")


# Record conversion


def relative_name(name: str, domain: str) -> str:
    """Route53 FQDN -> Cloudflare record name (relative, or the apex domain)."""
    name = name.rstrip(".")
    domain = domain.rstrip(".")
    if name == domain:
        return domain
    suffix = f".{domain}"
    return name[: -len(suffix)] if name.endswith(suffix) else name


def full_name(name: str, domain: str) -> str:
    """Cloudflare record name -> FQDN, which is how Cloudflare lists records."""
    if name == domain or name.endswith(f".{domain}"):
        return name
    return f"{name}.{domain}"


def convert_record(record: dict, domain: str) -> list[dict[str, Any]]:
    """Return the Cloudflare payloads for one Route53 record set (empty to skip)."""
    rtype = record["Type"]
    if rtype in SKIP_TYPES:
        return []

    name = relative_name(record["Name"], domain)
    ttl = record.get("TTL", 300)
    base = {"type": rtype, "name": name, "ttl": min(ttl, MAX_TTL), "proxied": False}

    if "AliasTarget" in record:
        target = record["AliasTarget"]["DNSName"].rstrip(".")
        if target.startswith(ALIAS_SKIP_PREFIXES):
            click.echo(f"  SKIP alias {record['Name']} -> {target} (manual review needed)")
            return []
        click.echo(f"  WARN alias {record['Name']} -> CNAME {target}")
        return [{**base, "type": "CNAME", "content": target, "ttl": 1 if ttl == 0 else base["ttl"]}]

    values = [rr["Value"] for rr in record.get("ResourceRecords", [])]

    if rtype == "TXT":
        return [{**base, "content": "".join(v.strip('"') for v in values)}]

    if rtype == "MX":
        payloads = []
        for value in values:
            priority, host = value.split(" ", 1)
            payloads.append({**base, "content": host.rstrip("."), "priority": int(priority)})
        return payloads

    if rtype == "CAA":
        return [{**base, "content": v.strip('"')} for v in values]

    if len(values) != 1:
        click.echo(f"  SKIP {rtype} {name}: multiple RRs not handled ({len(values)} values)")
        return []

    content = values[0].rstrip(".")
    if rtype == "SRV":
        parts = content.split()
        if len(parts) == 4:
            data = {
                "priority": int(parts[0]),
                "weight": int(parts[1]),
                "port": int(parts[2]),
                "target": parts[3].rstrip("."),
            }
            return [{**base, "data": data}]
    return [{**base, "content": content}]


def import_records(zone_id: str | None, route53_records: list[dict], domain: str, dry_run: bool) -> None:
    # A dry run still lists existing records, so it catches a missing DNS:Read permission.
    existing = list_cloudflare_records(zone_id) if zone_id else []
    existing_keys = {(r["type"], r["name"], r.get("content", "")) for r in existing}

    created = skipped = failed = 0
    for record in route53_records:
        payloads = convert_record(record, domain)
        if not payloads:
            skipped += 1
            continue

        for payload in payloads:
            label = f"{payload['type']} {payload['name']}"
            key = (payload["type"], full_name(payload["name"], domain), payload.get("content", ""))
            if key in existing_keys:
                click.echo(f"  exists  {label}")
                skipped += 1
                continue

            if dry_run:
                click.echo(
                    f"  [dry-run] would create {label} -> {payload.get('content', payload.get('data'))}"
                )
                created += 1
                continue

            try:
                cf_request("POST", f"/zones/{zone_id}/dns_records", json=payload)
            except click.ClickException as e:
                click.echo(f"  FAILED {label}: {e.message}")
                failed += 1
                continue
            click.echo(f"  created {label}")
            existing_keys.add(key)
            created += 1
            time.sleep(0.2)

    click.echo(f"\nImport summary: {created} created, {skipped} skipped, {failed} failed")
