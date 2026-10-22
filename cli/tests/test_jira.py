import io
import json
import urllib.error
import urllib.request

import pytest
from click.testing import CliRunner

from be import jira
from be.cli import cli


def configure(*pairs):
    for key, value in pairs:
        assert CliRunner().invoke(cli, ["config", "set", key, value]).exit_code == 0


def test_issue_key():
    projects = {"ACME": "Acme"}
    assert jira.issue_key("ACME-123-login", projects) == "ACME-123"
    assert jira.issue_key("acme-7", projects) == "ACME-7"
    assert jira.issue_key("OPS-1-x", projects) is None
    assert jira.issue_key("ACME-login", projects) is None
    assert jira.issue_key("ACME-1", {}) is None


def test_issue_summary(monkeypatch):
    configure(
        ("jira.url", "https://x.atlassian.net/"),
        ("jira.email", "me@x.com"),
        ("jira.token", "tok"),
    )
    seen = []

    def urlopen(request, timeout):
        seen.append(request)
        return io.BytesIO(json.dumps({"fields": {"summary": "Fix login"}}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert jira.issue_summary("ACME-1") == "Fix login"
    assert (
        seen[0].full_url
        == "https://x.atlassian.net/rest/api/3/issue/ACME-1?fields=summary"
    )
    assert seen[0].get_header("Authorization").startswith("Basic ")


def test_issue_summary_errors(monkeypatch):
    configure(("jira.url", "https://x.atlassian.net"), ("jira.email", "me@x.com"))
    with pytest.raises(jira.JiraError, match="must be set"):
        jira.issue_summary("ACME-1")
    monkeypatch.setenv("JIRA_API_TOKEN", "tok")

    def not_found(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", not_found)
    with pytest.raises(jira.JiraError, match="HTTP 404"):
        jira.issue_summary("ACME-1")
