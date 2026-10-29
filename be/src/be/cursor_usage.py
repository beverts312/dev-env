"""Your Cursor plan's usage this billing period, from the API behind the Cursor agent's /usage.

The CLI has no command that prints it, so this calls Cursor's dashboard API with the CLI's login."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import click

ENDPOINT = "https://api2.cursor.sh"
SERVICE = "aiserver.v1.DashboardService"
# where `agent login` saves the token on macOS: <domain>-access-token for account <domain>-user
KEYCHAIN = ("cursor-access-token", "cursor-user")
LOGIN = "not logged in to Cursor; run `agent login`"


def token() -> str:
    """The Cursor CLI's access token: $CURSOR_ACCESS_TOKEN, else wherever the CLI keeps it."""
    if os.environ.get("CURSOR_ACCESS_TOKEN"):
        return os.environ["CURSOR_ACCESS_TOKEN"]
    if os.environ.get("AGENT_CLI_CREDENTIAL_STORE") == "file":
        try:
            found = json.loads((Path.home() / ".cursor" / "auth.json").read_text()).get("accessToken")
        except (OSError, ValueError, AttributeError):
            found = None
    else:
        service, account = KEYCHAIN
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
            capture_output=True,
            text=True,
        )
        found = result.stdout.strip() if result.returncode == 0 else None
    if not found:
        raise click.ClickException(LOGIN)
    return found


def call(method: str, access_token: str) -> dict:
    """A DashboardService method's JSON answer, over Connect."""
    endpoint = os.environ.get("CURSOR_API_ENDPOINT") or ENDPOINT
    req = urllib.request.Request(
        f"{endpoint}/{SERVICE}/{method}",
        data=b"{}",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Connect-Protocol-Version": "1",
            "Authorization": f"Bearer {access_token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise click.ClickException("Cursor login expired; run `agent status` or `agent login`") from e
        raise click.ClickException(f"Cursor {method} failed: HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise click.ClickException(f"Cursor {method} failed: {getattr(e, 'reason', e)}") from e


def fetch() -> tuple[dict, dict, dict | None]:
    """The current period's usage, the plan's info and the on-demand hard limit. The last two are
    optional, as in the CLI: {} and None when their calls fail."""
    access_token = token()
    usage = call("GetCurrentPeriodUsage", access_token)
    try:
        plan = call("GetPlanInfo", access_token)
    except click.ClickException:
        plan = {}
    try:
        hard_limit = call("GetHardLimit", access_token)
    except click.ClickException:
        hard_limit = None
    return usage, plan, hard_limit


def reset_label(millis) -> str:
    """e.g. "Nov 12", in UTC as the CLI shows it; "" when unknown."""
    n = int(millis or 0)
    if n <= 0:
        return ""
    d = datetime.fromtimestamp(n / 1000, tz=timezone.utc)
    return f"{d:%b} {d.day}"


# the most a hard limit can be, which means no limit
UNLIMITED = 2147483647


def on_demand(usage: dict, hard_limit: dict | None) -> dict:
    """On-demand spend as the CLI shows it: kind is fixed (with limit_dollars), unlimited, disabled
    or unavailable. A team member's limit is their own when set, else the team's."""
    spend = usage.get("spendLimitUsage") or {}
    used = spend.get("individualUsed", 0) / 100
    own = None
    if "individualLimit" in spend:
        cents = spend["individualLimit"]
        own = {"kind": "fixed", "limit_dollars": cents / 100} if cents > 0 else {"kind": "disabled"}
    if spend.get("limitType") == "team":
        if own:
            found = own
        elif hard_limit is not None:
            no_limit = hard_limit.get("noUsageBasedAllowed") or hard_limit.get("hardLimit", 0) <= 0
            found = {"kind": "disabled" if no_limit else "unlimited"}
        else:
            found = {"kind": "unlimited" if int(spend.get("pooledLimit") or 0) > 0 else "unavailable"}
    elif hard_limit is None:
        found = own or {"kind": "unavailable"}
    elif hard_limit.get("noUsageBasedAllowed"):
        found = {"kind": "disabled"}
    elif hard_limit.get("hardLimit", 0) >= UNLIMITED:
        found = {"kind": "unlimited"}
    elif hard_limit.get("hardLimit", 0) > 0:
        # the hard limit is in dollars, unlike the spend fields
        found = {"kind": "fixed", "limit_dollars": hard_limit["hardLimit"]}
    else:
        found = {"kind": "disabled"}
    return {"kind": found["kind"], "used_dollars": used, "limit_dollars": found.get("limit_dollars")}


def summarize(usage: dict, plan: dict, hard_limit: dict | None = None) -> dict:
    """Included, Auto and API use as limits like Claude's, plus on-demand spend."""
    info = plan.get("planInfo") or {}
    resets = reset_label(usage.get("billingCycleEnd")) or reset_label(info.get("billingCycleEnd"))
    limits = []
    plan_usage = usage.get("planUsage")
    if plan_usage is not None:
        # the CLI's fallback when the percentage isn't sent: included spend over the limit
        limit = plan_usage.get("limit", 0)
        total = plan_usage.get("totalPercentUsed")
        if total is None:
            total = plan_usage.get("includedSpend", 0) / limit * 100 if limit > 0 else 0
        parts = [("Included", total), ("Auto", plan_usage.get("autoPercentUsed")), ("API", plan_usage.get("apiPercentUsed"))]
        limits = [{"label": label, "percent": round(p), "resets": resets} for label, p in parts if p is not None]
    return {
        "plan": info.get("planName", ""),
        "limits": limits,
        "on_demand": on_demand(usage, hard_limit),
        # enterprise plans send spend only, which the CLI charts and this doesn't
        "message": "" if limits else "Usage details are not available for this plan.",
    }
