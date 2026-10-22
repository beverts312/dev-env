"""`be dns`: DNS helpers (replaces scripts/r53_to_cf.py)."""

from __future__ import annotations

import subprocess
import sys

import click

from be import config
from be import dns as lib


@click.group()
def dns() -> None:
    """DNS helpers."""


@dns.command("r53-cf")
@click.argument("domain")
@click.option("--dry-run", is_flag=True, help="Preview only; create and change nothing.")
@click.option(
    "--skip-nameserver-update",
    is_flag=True,
    help="Import records only; do not change the registrar nameservers.",
)
@click.option("--hosted-zone-id", help="Route53 hosted zone ID (without the /hostedzone/ prefix).")
@config.option("cloudflare.account_id", "--account-id")
def r53_cf(
    domain: str,
    dry_run: bool,
    skip_nameserver_update: bool,
    hosted_zone_id: str | None,
    account_id: str | None,
) -> None:
    """Migrate DOMAIN's DNS records from Route53 to Cloudflare.

    Creates the Cloudflare zone if needed, copies the Route53 records into it,
    then points the domain's Route53 Domains registration at Cloudflare's
    nameservers. Needs CLOUDFLARE_API_TOKEN with Zone > DNS Read and Edit.
    """
    domain = domain.lower().strip(".")
    route53 = lib.boto3_client("route53")
    click.echo(f"=== Migrating {domain} ===\n")

    click.echo("1. Creating Cloudflare zone...")
    zone = lib.find_cloudflare_zone(domain)
    if zone:
        click.echo(f"   Using existing zone (status: {zone.get('status', 'unknown')})")
    elif dry_run:
        click.echo(f"   [dry-run] would create zone {domain}")
    else:
        zone = lib.create_cloudflare_zone(domain, account_id)

    nameservers: list[str] = []
    if zone:
        nameservers = zone.get("name_servers") or []
        if not nameservers:
            raise click.ClickException(f"no nameservers returned for zone {zone['id']}")
        click.echo(f"   Zone ID: {zone['id']}")
        click.echo(f"   Nameservers: {', '.join(nameservers)}")
    click.echo()

    click.echo("2. Importing records from Route53...")
    zone_id = lib.find_route53_hosted_zone(route53, domain, hosted_zone_id)
    click.echo(f"   Hosted zone: {zone_id}")
    records = lib.list_route53_records(route53, zone_id)
    lib.import_records(zone["id"] if zone else None, records, domain, dry_run)
    click.echo()

    if skip_nameserver_update:
        click.echo("3. Skipping nameserver update (--skip-nameserver-update)")
    elif not nameservers:
        click.echo("3. [dry-run] nameservers are assigned when the zone is created; skipping")
    else:
        click.echo("3. Updating nameservers at AWS domain registration...")
        domains_client = lib.boto3_client("route53domains", region_name="us-east-1")
        try:
            lib.update_registrar_nameservers(domains_client, domain, nameservers, dry_run)
        except domains_client.exceptions.InvalidInput as e:
            raise click.ClickException(
                f"could not update nameservers via Route53 Domains: {e}\n"
                "If the domain is registered elsewhere, update NS at that registrar manually."
            ) from None

    click.echo("\nDone.")
    if not dry_run and not skip_nameserver_update:
        click.echo("DNS propagation may take up to 48 hours (usually much less).")
        click.echo("Verify records in the Cloudflare dashboard before relying on production traffic.")


FLUSH_COMMANDS = (
    ["sudo", "dscacheutil", "-flushcache"],
    ["sudo", "killall", "-HUP", "mDNSResponder"],
)


@dns.command("flush-local")
def flush_local() -> None:
    """Flush the local DNS cache (macOS only; prompts for sudo)."""
    if sys.platform != "darwin":
        raise click.ClickException(f"flush-local only supports macOS, not {sys.platform}")
    for cmd in FLUSH_COMMANDS:
        code = subprocess.run(cmd).returncode
        if code != 0:
            raise click.ClickException(f"{' '.join(cmd)} exited with {code}")
    click.echo("Local DNS cache flushed.")
