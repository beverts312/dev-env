import subprocess
import sys

import pytest
from click.testing import CliRunner

from be import dns as lib
from be.cli import cli


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({"Name": "example.com.", "Type": "NS", "ResourceRecords": [{"Value": "ns."}]}, []),
        (
            {"Name": "www.example.com.", "Type": "A", "TTL": 60, "ResourceRecords": [{"Value": "1.2.3.4"}]},
            [{"type": "A", "name": "www", "ttl": 60, "proxied": False, "content": "1.2.3.4"}],
        ),
        (
            {"Name": "example.com.", "Type": "TXT", "TTL": 300, "ResourceRecords": [{"Value": '"v=spf1"'}]},
            [{"type": "TXT", "name": "example.com", "ttl": 300, "proxied": False, "content": "v=spf1"}],
        ),
        (
            {
                "Name": "example.com.",
                "Type": "MX",
                "TTL": 999999,
                "ResourceRecords": [{"Value": "10 mx1.example.com."}, {"Value": "20 mx2.example.com."}],
            },
            [
                {"type": "MX", "name": "example.com", "ttl": 86400, "proxied": False, "content": "mx1.example.com", "priority": 10},
                {"type": "MX", "name": "example.com", "ttl": 86400, "proxied": False, "content": "mx2.example.com", "priority": 20},
            ],
        ),
        (
            {"Name": "_sip._tcp.example.com.", "Type": "SRV", "TTL": 300, "ResourceRecords": [{"Value": "1 2 5060 sip.example.com."}]},
            [
                {
                    "type": "SRV",
                    "name": "_sip._tcp",
                    "ttl": 300,
                    "proxied": False,
                    "data": {"priority": 1, "weight": 2, "port": 5060, "target": "sip.example.com"},
                }
            ],
        ),
        (
            {"Name": "app.example.com.", "Type": "A", "AliasTarget": {"DNSName": "lb.aws.com."}},
            [{"type": "CNAME", "name": "app", "ttl": 300, "proxied": False, "content": "lb.aws.com"}],
        ),
        ({"Name": "s.example.com.", "Type": "A", "AliasTarget": {"DNSName": "dualstack.lb.aws.com."}}, []),
    ],
)
def test_convert_record(record, expected):
    assert lib.convert_record(record, "example.com") == expected


class FakePaginator:
    def __init__(self, pages):
        self.pages = pages

    def paginate(self, **kwargs):
        return self.pages


class FakeRoute53:
    def get_paginator(self, name):
        if name == "list_hosted_zones":
            return FakePaginator([{"HostedZones": [{"Name": "example.com.", "Id": "/hostedzone/Z1"}]}])
        return FakePaginator(
            [
                {
                    "ResourceRecordSets": [
                        {"Name": "www.example.com.", "Type": "A", "TTL": 60, "ResourceRecords": [{"Value": "1.2.3.4"}]},
                        {"Name": "api.example.com.", "Type": "A", "TTL": 60, "ResourceRecords": [{"Value": "5.6.7.8"}]},
                    ]
                }
            ]
        )


class FakeCloudflare:
    def __init__(self, zone_exists=True):
        self.zone_exists = zone_exists
        self.calls = []
        self.zone = {"id": "cfz", "status": "active", "name_servers": ["a.ns.cloudflare.com"]}
        self.existing = [{"type": "A", "name": "www.example.com", "content": "1.2.3.4"}]

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("json")))
        if path == "/zones":
            if method == "GET":
                return {"result": [self.zone] if self.zone_exists else []}
            return {"result": self.zone}
        if method == "GET":
            return {"result": self.existing, "result_info": {"total_pages": 1}}
        return {"result": {}}

    def posts(self):
        return [json for method, _, json in self.calls if method == "POST"]


@pytest.fixture
def cloudflare(monkeypatch):
    fake = FakeCloudflare()
    monkeypatch.setattr(lib, "cf_request", fake.request)
    monkeypatch.setattr(lib, "boto3_client", lambda name, **kw: FakeRoute53())
    monkeypatch.setattr(lib.time, "sleep", lambda s: None)
    return fake


def test_r53_cf_creates_only_missing_records(cloudflare):
    result = CliRunner().invoke(cli, ["dns", "r53-cf", "example.com", "--skip-nameserver-update"])
    assert result.exit_code == 0, result.output
    assert cloudflare.posts() == [{"type": "A", "name": "api", "ttl": 60, "proxied": False, "content": "5.6.7.8"}]
    assert "exists  A www" in result.output


def test_r53_cf_dry_run_does_not_create_zone(cloudflare):
    cloudflare.zone_exists = False
    result = CliRunner().invoke(cli, ["dns", "r53-cf", "example.com", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert cloudflare.posts() == []
    assert "[dry-run] would create zone example.com" in result.output
    assert "[dry-run] would create A www" in result.output


def test_help_shows_account_envvar():
    help_text = " ".join(CliRunner().invoke(cli, ["dns", "r53-cf", "--help"]).output.split())
    assert "CLOUDFLARE_ACCOUNT_ID" in help_text
    assert "[config: cloudflare.account_id]" in help_text


def test_flush_local_runs_mac_commands(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "run", lambda cmd: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    result = CliRunner().invoke(cli, ["dns", "flush-local"])
    assert result.exit_code == 0, result.output
    assert calls == [
        ["sudo", "dscacheutil", "-flushcache"],
        ["sudo", "killall", "-HUP", "mDNSResponder"],
    ]


def test_flush_local_stops_on_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "run", lambda cmd: calls.append(cmd) or subprocess.CompletedProcess(cmd, 1))
    result = CliRunner().invoke(cli, ["dns", "flush-local"])
    assert result.exit_code != 0
    assert len(calls) == 1
    assert "exited with 1" in result.output


def test_flush_local_rejects_other_platforms(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", lambda cmd: pytest.fail("should not run"))
    result = CliRunner().invoke(cli, ["dns", "flush-local"])
    assert result.exit_code != 0
    assert "only supports macOS, not linux" in result.output
