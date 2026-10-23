import io
import json
import urllib.error
import urllib.parse
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


def test_in_progress_issues_pages(monkeypatch):
    configure(
        ("jira.url", "https://x.atlassian.net"),
        ("jira.email", "me@x.com"),
        ("jira.token", "tok"),
    )
    pages = [
        {"issues": [{"key": "ACME-2", "fields": {"summary": "Two", "issuetype": {"name": "Story"}, "parent": {"key": "ACME-9"}}}], "nextPageToken": "p2", "isLast": False},
        {"issues": [{"key": "ACME-1", "fields": {"summary": "One"}}], "isLast": True},
    ]
    seen = []

    def urlopen(request, timeout):
        seen.append(request.full_url)
        return io.BytesIO(json.dumps(pages.pop(0)).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert jira.in_progress_issues() == [
        {"key": "ACME-2", "type": "Story", "summary": "Two", "parent": "ACME-9"},
        {"key": "ACME-1", "type": "", "summary": "One", "parent": ""},
    ]
    assert seen[0].startswith("https://x.atlassian.net/rest/api/3/search/jql?jql=assignee")
    assert "statusCategory" in urllib.parse.unquote_plus(seen[0])
    assert "nextPageToken=p2" in seen[1]


ISSUES = [
    {"key": "ACME-12", "type": "Bug", "summary": "Fix login"},
    {"key": "ACME-3", "type": "Story", "summary": "Add page"},
]


def test_jira_ls(monkeypatch):
    monkeypatch.setattr(jira, "in_progress_issues", lambda: ISSUES)
    result = CliRunner().invoke(cli, ["jira", "ls"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == ["ACME-12  Bug    Fix login", "ACME-3   Story  Add page"]


FEATURE = {"key": "ACME-1", "type": "Feature", "summary": "Big thing"}


def test_jira_ls_hides_features(monkeypatch):
    monkeypatch.setattr(jira, "in_progress_issues", lambda: ISSUES + [FEATURE])
    result = CliRunner().invoke(cli, ["jira", "ls"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "1 hidden (Feature); --all shows them",
        "ACME-12  Bug    Fix login",
        "ACME-3   Story  Add page",
    ]
    result = CliRunner().invoke(cli, ["jira", "ls", "--all"])
    assert result.output.splitlines()[-1] == "ACME-1   Feature  Big thing"


def test_jira_ls_interactive_toggles_all(monkeypatch):
    from be.commands import jira as jira_command

    monkeypatch.setattr(jira, "in_progress_issues", lambda: [FEATURE])
    picks = [("all", 0), None]
    shown = []
    monkeypatch.setattr(
        jira_command,
        "choose",
        lambda rows, index=0, hint="", actions=(): shown.append(rows) or picks.pop(0),
    )
    assert CliRunner().invoke(cli, ["jira", "ls", "-i"]).exit_code == 0
    assert shown == [["no in progress issues assigned to you"], ["ACME-1  Feature  Big thing"]]


def test_jira_ls_empty(monkeypatch):
    monkeypatch.setattr(jira, "in_progress_issues", lambda: [])
    assert CliRunner().invoke(cli, ["jira", "ls"]).output == "no in progress issues assigned to you\n"


def test_jira_ls_unconfigured():
    result = CliRunner().invoke(cli, ["jira", "ls"])
    assert result.exit_code == 1
    assert "must be set" in result.output


def test_jira_ls_interactive_opens_browser(monkeypatch):
    from be.commands import jira as jira_command

    configure(("jira.url", "https://x.atlassian.net/"))
    monkeypatch.setattr(jira, "in_progress_issues", lambda: ISSUES)
    picks = [("browse", 1), None]
    monkeypatch.setattr(jira_command, "choose", lambda rows, index=0, hint="", actions=(): picks.pop(0))
    launched = []
    monkeypatch.setattr(jira_command.click, "launch", launched.append)
    result = CliRunner().invoke(cli, ["jira", "ls", "-i"])
    assert result.exit_code == 0, result.output
    assert launched == ["https://x.atlassian.net/browse/ACME-3"]


def open_issue_workspace(tmp_path, monkeypatch, issues, picks, dirs):
    from be.commands import jira as jira_command

    for name in dirs:
        (tmp_path / name).mkdir()
    configure(("ws.dir", str(tmp_path)))
    monkeypatch.setattr(jira, "in_progress_issues", lambda: issues)
    monkeypatch.setattr(jira_command, "choose", lambda rows, index=0, hint="", actions=(): picks.pop(0))
    opened = []
    monkeypatch.setattr(jira_command, "open_root", lambda root, window=None: opened.append(root))
    result = CliRunner().invoke(cli, ["jira", "ls", "-i"])
    assert result.exit_code == 0, result.output
    return result, opened


def test_jira_ls_interactive_opens_workspace(tmp_path, monkeypatch):
    issues = [dict(issue, parent="") for issue in ISSUES]
    _, opened = open_issue_workspace(
        tmp_path, monkeypatch, issues, [("open", 1)], ["acme-3", "ACME-12-other"]
    )
    assert opened == [tmp_path / "acme-3"]


def test_jira_ls_interactive_opens_parent_workspace(tmp_path, monkeypatch):
    issues = [{"key": "ACME-5", "type": "Sub-task", "summary": "Part", "parent": "ACME-4"}]
    _, opened = open_issue_workspace(
        tmp_path, monkeypatch, issues, [("open", 0)], ["ACME-4", "ACME-5x"]
    )
    assert opened == [tmp_path / "ACME-4"]


def test_jira_ls_interactive_prefers_issue_workspace(tmp_path, monkeypatch):
    issues = [{"key": "ACME-5", "type": "Sub-task", "summary": "Part", "parent": "ACME-4"}]
    _, opened = open_issue_workspace(
        tmp_path, monkeypatch, issues, [("open", 0)], ["ACME-4", "ACME-5"]
    )
    assert opened == [tmp_path / "ACME-5"]


def test_jira_ls_interactive_missing_workspace(tmp_path, monkeypatch):
    issues = [{"key": "ACME-5", "type": "Sub-task", "summary": "Part", "parent": "ACME-4"}]
    result, opened = open_issue_workspace(
        tmp_path, monkeypatch, issues, [("open", 0), None], ["ACME-6"]
    )
    assert opened == []
    assert "no workspace named ACME-5 or ACME-4" in result.output


def test_jira_ls_interactive_by_default(monkeypatch):
    from be.commands import jira as jira_command

    configure(("interactive", "true"))
    monkeypatch.setattr(jira_command.config, "in_terminal", lambda: True)
    monkeypatch.setattr(jira, "in_progress_issues", lambda: ISSUES)
    chosen = []
    monkeypatch.setattr(
        jira_command, "choose", lambda rows, index=0, hint="", actions=(): chosen.append(rows)
    )
    assert CliRunner().invoke(cli, ["jira", "ls"]).exit_code == 0
    assert len(chosen) == 1
    result = CliRunner().invoke(cli, ["jira", "ls", "-I"])
    assert result.output.splitlines()[-1].startswith("ACME-3")
    assert len(chosen) == 1
