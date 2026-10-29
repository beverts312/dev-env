import io
import json
import subprocess
import urllib.error
import urllib.request

import click
import pytest

from be import cursor_usage

# as a Team plan sends it
USAGE = {
    "billingCycleStart": "1791918759000",
    "billingCycleEnd": "1794597159000",
    "planUsage": {
        "totalSpend": 2990, "includedSpend": 2000, "bonusSpend": 990, "limit": 2000,
        "autoPercentUsed": 11.2, "apiPercentUsed": 15.95, "totalPercentUsed": 11.96,
    },
    "spendLimitUsage": {"pooledUsed": 0, "limitType": "team"},
    "displayMessage": "You've hit your usage limit",
}
PLAN = {"planInfo": {"planName": "Team"}}


def test_summarize():
    out = cursor_usage.summarize(USAGE, PLAN, {"noUsageBasedAllowed": True})
    assert out["plan"] == "Team"
    assert out["limits"] == [
        {"label": "Included", "percent": 12, "resets": "Nov 13"},
        {"label": "Auto", "percent": 11, "resets": "Nov 13"},
        {"label": "API", "percent": 16, "resets": "Nov 13"},
    ]
    assert out["on_demand"] == {"kind": "disabled", "used_dollars": 0, "limit_dollars": None}
    assert out["message"] == ""


def test_summarize_computes_missing_percent():
    usage = {"planUsage": {"includedSpend": 500, "limit": 2000}}
    out = cursor_usage.summarize(usage, {"planInfo": {"planName": "Pro", "billingCycleEnd": "1794597159000"}})
    assert out["limits"] == [{"label": "Included", "percent": 25, "resets": "Nov 13"}]


def test_summarize_without_plan_usage():
    out = cursor_usage.summarize({"billingCycleEnd": "0"}, {})
    assert out["limits"] == []
    assert out["message"] == "Usage details are not available for this plan."


@pytest.mark.parametrize("spend,hard_limit,expected", [
    ({"individualUsed": 1234, "individualLimit": 5000}, None, ("fixed", 12.34, 50)),
    ({"individualUsed": 0, "individualLimit": 0}, None, ("disabled", 0, None)),
    ({"limitType": "team"}, {"hardLimit": 100}, ("unlimited", 0, None)),
    ({"limitType": "team", "pooledLimit": 10000}, None, ("unlimited", 0, None)),
    ({"limitType": "team"}, None, ("unavailable", 0, None)),
    ({}, {"hardLimit": 2147483647}, ("unlimited", 0, None)),
    ({"individualUsed": 250}, {"hardLimit": 20}, ("fixed", 2.5, 20)),
    ({}, {"noUsageBasedAllowed": True, "hardLimit": 20}, ("disabled", 0, None)),
])
def test_on_demand(spend, hard_limit, expected):
    out = cursor_usage.on_demand({"spendLimitUsage": spend}, hard_limit)
    assert (out["kind"], out["used_dollars"], out["limit_dollars"]) == expected


def test_token_from_env(monkeypatch):
    monkeypatch.setenv("CURSOR_ACCESS_TOKEN", "abc")
    assert cursor_usage.token() == "abc"


def test_token_from_file(monkeypatch, tmp_path):
    monkeypatch.delenv("CURSOR_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("AGENT_CLI_CREDENTIAL_STORE", "file")
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".cursor" / "auth.json").write_text(json.dumps({"accessToken": "from-file"}))
    assert cursor_usage.token() == "from-file"


def test_token_from_keychain(monkeypatch):
    monkeypatch.delenv("CURSOR_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("AGENT_CLI_CREDENTIAL_STORE", raising=False)
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "from-keychain\n", "")

    monkeypatch.setattr(subprocess, "run", run)
    assert cursor_usage.token() == "from-keychain"
    assert calls[0][:6] == ["security", "find-generic-password", "-s", "cursor-access-token", "-a", "cursor-user"]


def test_token_missing(monkeypatch):
    monkeypatch.delenv("CURSOR_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("AGENT_CLI_CREDENTIAL_STORE", raising=False)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 44, "", "not found"))
    with pytest.raises(click.ClickException, match="agent login"):
        cursor_usage.token()


def test_call(monkeypatch):
    monkeypatch.delenv("CURSOR_API_ENDPOINT", raising=False)
    seen = []

    def urlopen(req, timeout):
        seen.append(req)
        return io.BytesIO(json.dumps(USAGE).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert cursor_usage.call("GetCurrentPeriodUsage", "abc") == USAGE
    req = seen[0]
    assert req.full_url == "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage"
    assert req.get_method() == "POST"
    assert req.get_header("Authorization") == "Bearer abc"
    assert req.get_header("Connect-protocol-version") == "1"


def test_call_expired(monkeypatch):
    def urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(click.ClickException, match="login expired"):
        cursor_usage.call("GetCurrentPeriodUsage", "abc")


def test_fetch_ignores_optional_calls(monkeypatch):
    monkeypatch.setattr(cursor_usage, "token", lambda: "abc")

    def call(method, access_token):
        if method == "GetCurrentPeriodUsage":
            return USAGE
        raise click.ClickException("down")

    monkeypatch.setattr(cursor_usage, "call", call)
    assert cursor_usage.fetch() == (USAGE, {}, None)
