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
        {"issues": [{"key": "ACME-2", "fields": {"summary": "Two", "issuetype": {"name": "Story"}, "parent": {"key": "ACME-9", "fields": {"summary": "Nine", "issuetype": {"name": "Epic"}}}}}], "nextPageToken": "p2", "isLast": False},
        {"issues": [{"key": "ACME-1", "fields": {"summary": "One"}}], "isLast": True},
    ]
    seen = []

    def urlopen(request, timeout):
        seen.append(request.full_url)
        return io.BytesIO(json.dumps(pages.pop(0)).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert jira.in_progress_issues() == [
        {"key": "ACME-2", "type": "Story", "summary": "Two", "parent": "ACME-9", "parent_type": "Epic", "parent_summary": "Nine"},
        {"key": "ACME-1", "type": "", "summary": "One", "parent": "", "parent_type": "", "parent_summary": ""},
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


def guided_create(tmp_path, monkeypatch, issue, answers):
    """Pick issue, answer the prompts, and return what create_workspace was given."""
    from be.commands import jira as jira_command

    configure(("ws.dir", str(tmp_path)))
    monkeypatch.setattr(jira, "in_progress_issues", lambda: [issue])
    picks = [("open", 0), None]
    monkeypatch.setattr(jira_command, "choose", lambda rows, index=0, hint="", actions=(): picks.pop(0))
    created = []
    monkeypatch.setattr(jira_command, "create_workspace", lambda *args: created.append(args))
    result = CliRunner().invoke(cli, ["jira", "ls", "-i"], input="".join(f"{a}\n" for a in answers))
    assert result.exit_code == 0, result.output
    return result, created


STORY = {
    "key": "ACME-5",
    "type": "Story",
    "summary": "Part",
    "parent": "ACME-4",
    "parent_type": "Epic",
    "parent_summary": "Whole",
}


def test_jira_ls_creates_issue_workspace(tmp_path, monkeypatch):
    # create, issue level, keep the name, repos, no extra dirs, a description
    result, created = guided_create(tmp_path, monkeypatch, STORY, ["", "i", "", "api", "", "notes"])
    assert "(p) its Epic ACME-4 (Whole)" in result.output
    assert len(created) == 1
    work_dir, repos, extra_dirs, description, parent, *_, issue_name = created[0]
    assert (work_dir, repos, extra_dirs, description) == ("ACME-5", "api", "", "notes")
    assert parent == str(tmp_path)
    assert issue_name == "Part"


def test_jira_ls_creates_parent_workspace(tmp_path, monkeypatch):
    _, created = guided_create(tmp_path, monkeypatch, STORY, ["y", "p", "", "", "", ""])
    assert created[0][0] == "ACME-4"
    assert created[0][-1] == "Whole"


def test_jira_ls_create_skips_level_for_epics(tmp_path, monkeypatch):
    epic = dict(STORY, type="Epic", parent="ACME-1", parent_type="Feature")
    result, created = guided_create(tmp_path, monkeypatch, epic, ["", "", "", "", ""])
    assert "Workspace for" not in result.output
    assert created[0][0] == "ACME-5"


def test_jira_ls_create_skips_level_without_feature_parent(tmp_path, monkeypatch):
    task = dict(STORY, type="Sub-task", parent_type="Story")
    result, created = guided_create(tmp_path, monkeypatch, task, ["", "", "", "", ""])
    assert "Workspace for" not in result.output
    assert created[0][0] == "ACME-5"


def test_jira_ls_create_declined(tmp_path, monkeypatch):
    result, created = guided_create(tmp_path, monkeypatch, STORY, ["n"])
    assert "No workspace for ACME-5. Create one?" in result.output
    assert created == []


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


def test_jira_ls_creates_workspace_end_to_end(tmp_path, monkeypatch):
    import subprocess

    import yaml

    from be import cmux
    from be.commands import jira as jira_command

    configure(("ws.dir", str(tmp_path)))
    monkeypatch.setattr(jira, "in_progress_issues", lambda: [STORY])
    picks = [("open", 0)]
    monkeypatch.setattr(jira_command, "choose", lambda rows, index=0, hint="", actions=(): picks.pop(0))
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    calls = []
    monkeypatch.setattr(cmux, "new_workspace", lambda binary, args: calls.append(args) or "")
    monkeypatch.setattr(cmux, "workspace_ref", lambda output: "workspace:1")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0))
    result = CliRunner().invoke(
        cli, ["jira", "ls", "-i", "--window", "1"], input="y\np\n\n\n\nbig work\n"
    )
    assert result.exit_code == 0, result.output
    manifest = yaml.safe_load((tmp_path / "ACME-4" / "workspace.yml").read_text())
    assert manifest["issue_name"] == "Whole"
    assert manifest["description"] == "big work"
    assert calls[0][:2] == ["--name", "Whole"]
