import json
import os
import subprocess
from pathlib import Path

import click
import pytest
import yaml
from click.testing import CliRunner

from be import cmux
from be.cli import cli
from be.commands import pr, ws


def test_help_shows_envvars():
    runner = CliRunner()
    assert "GIT_EMAIL" in runner.invoke(cli, ["git", "author", "--help"]).output
    assert "WORK_ORG" in runner.invoke(cli, ["git", "clone", "--help"]).output
    assert "PRS_DIR" in runner.invoke(cli, ["pr", "review", "--help"]).output
    create_help = runner.invoke(cli, ["ws", "create", "--help"]).output
    assert "BE_CLAUDE_MODEL" in create_help
    assert "WS_DIR" in create_help
    assert "[config: ws.dir]" in create_help
    open_help = runner.invoke(cli, ["ws", "open", "--help"]).output
    assert "WS_DIR" in open_help
    assert "[config: ws.dir]" in open_help


def test_ws_open_starts_claude_in_main_pane(tmp_path, monkeypatch):
    workspace = tmp_path / "proj"
    workspace.mkdir()
    layout = {
        "direction": "horizontal",
        "children": [
            {
                "pane": {
                    "surfaces": [{"type": "terminal", "name": "claude", "focus": True}]
                }
            },
            {
                "pane": {
                    "surfaces": [{"type": "terminal", "name": "repo", "cwd": "repo"}]
                }
            },
        ],
    }
    calls = []
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    monkeypatch.setattr(cmux, "get_layout", lambda binary, name: layout)
    monkeypatch.setattr(
        cmux, "new_workspace", lambda binary, args: calls.append(args) or ""
    )
    result = CliRunner().invoke(cli, ["ws", "open", "proj", "--dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(calls[0][calls[0].index("--layout") + 1])
    claude = payload["children"][0]["pane"]["surfaces"][0]
    assert claude["command"] == "claude --model claude-opus-5-5"
    assert claude["cwd"] == str(workspace.resolve())
    assert "command" not in payload["children"][1]["pane"]["surfaces"][0]


def test_pr_review_opens_pr_in_browser_pane(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(pr, "clone_or_reuse", lambda slug, dest: None)
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    monkeypatch.setattr(cmux, "find_group", lambda binary, name: "workspace_group:1")
    monkeypatch.setattr(
        cmux, "new_workspace", lambda binary, args: calls.append(args) or ""
    )
    result = CliRunner().invoke(
        cli, ["pr", "review", "owner/repo", "42", "--parent", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    args = calls[0]
    assert args[args.index("--name") + 1] == "pr-repo-42"
    assert "--command" not in args
    layout = json.loads(args[args.index("--layout") + 1])
    claude, browser = (child["pane"]["surfaces"][0] for child in layout["children"])
    assert claude["command"] == "claude '/pr-review owner/repo 42'"
    assert claude["cwd"] == str((tmp_path / "repo").resolve())
    assert browser == {
        "type": "browser",
        "name": "pr",
        "url": "https://github.com/owner/repo/pull/42",
    }


def test_pr_review_joins_existing_prs_group(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(pr, "clone_or_reuse", lambda slug, dest: None)
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    monkeypatch.setattr(
        cmux,
        "find_group",
        lambda binary, name: "workspace_group:7" if name == "prs" else None,
    )
    monkeypatch.setattr(
        cmux,
        "new_workspace",
        lambda binary, args: calls.append(args) or "OK workspace:3",
    )
    monkeypatch.setattr(
        cmux,
        "create_group",
        lambda *a: (_ for _ in ()).throw(AssertionError("should not create")),
    )
    result = CliRunner().invoke(
        cli, ["pr", "review", "owner/repo", "42", "--parent", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert calls[0][calls[0].index("--group") + 1] == "workspace_group:7"


def test_pr_review_creates_prs_group_anchored_on_workspace(tmp_path, monkeypatch):
    calls, created = [], []
    monkeypatch.setattr(pr, "clone_or_reuse", lambda slug, dest: None)
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    monkeypatch.setattr(cmux, "find_group", lambda binary, name: None)
    monkeypatch.setattr(
        cmux,
        "new_workspace",
        lambda binary, args: calls.append(args) or "OK workspace:3",
    )
    monkeypatch.setattr(cmux, "create_group", lambda *a: created.append(a))
    result = CliRunner().invoke(
        cli, ["pr", "review", "owner/repo", "42", "--parent", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "--group" not in calls[0]
    assert created == [("cmux", "prs", "workspace:3")]


def test_ws_create_writes_manifest(tmp_path, monkeypatch):
    extra = tmp_path / "notes"
    extra.mkdir()
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    monkeypatch.setattr(cmux, "new_workspace", lambda binary, args: "OK workspace:1")
    monkeypatch.setattr(cmux, "workspace_ref", lambda output: "workspace:1")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0)
    )
    result = CliRunner().invoke(
        cli,
        [
            "ws",
            "create",
            "proj",
            "--dir",
            str(tmp_path),
            "--extra-dirs",
            str(extra),
            "-d",
            'fix "the" thing: soon',
        ],
    )
    assert result.exit_code == 0, result.output
    assert yaml.safe_load((tmp_path / "proj" / "workspace.yml").read_text()) == {
        "name": "proj",
        "description": 'fix "the" thing: soon',
        "extra_dirs": [str(extra.resolve())],
    }


def ws_create_jira(tmp_path, monkeypatch, summary):
    from be import jira

    CliRunner().invoke(cli, ["config", "set", "jira.projects.ACME", "Acme"])
    calls = []
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    monkeypatch.setattr(
        cmux, "new_workspace", lambda binary, args: calls.append(args) or ""
    )
    monkeypatch.setattr(cmux, "workspace_ref", lambda output: "workspace:1")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0)
    )
    monkeypatch.setattr(jira, "issue_summary", summary)
    result = CliRunner().invoke(
        cli, ["ws", "create", "acme-12-login", "--dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    manifest = yaml.safe_load((tmp_path / "acme-12-login" / "workspace.yml").read_text())
    return result, calls[0][calls[0].index("--name") + 1], manifest


def test_ws_create_names_workspace_after_jira_issue(tmp_path, monkeypatch):
    keys = []
    result, name, manifest = ws_create_jira(
        tmp_path, monkeypatch, lambda key: keys.append(key) or "Fix login"
    )
    assert keys == ["ACME-12"]
    assert name == "Fix login"
    assert manifest["issue_name"] == "Fix login"


def test_ws_create_continues_when_jira_fails(tmp_path, monkeypatch):
    from be import jira

    def fail(key):
        raise jira.JiraError("HTTP 401 from https://x.atlassian.net")

    result, name, manifest = ws_create_jira(tmp_path, monkeypatch, fail)
    assert "could not fetch Jira issue ACME-12: HTTP 401" in result.output
    assert name == "acme-12-login"
    assert "issue_name" not in manifest


def test_ws_create_interactive_prompts(tmp_path, monkeypatch):
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    calls = []
    monkeypatch.setattr(
        cmux, "new_workspace", lambda binary, args: calls.append(args) or ""
    )
    monkeypatch.setattr(cmux, "workspace_ref", lambda output: "workspace:1")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0)
    )
    result = CliRunner().invoke(
        cli, ["ws", "create", "-i", "--dir", str(tmp_path)], input="proj\n\n\nmy work\n"
    )
    assert result.exit_code == 0, result.output
    assert "Workspace name" in result.output
    assert calls[0][calls[0].index("--name") + 1] == "proj"
    assert (
        yaml.safe_load((tmp_path / "proj" / "workspace.yml").read_text())["description"]
        == "my work"
    )


def test_ws_create_interactive_defaults_to_given_values(tmp_path, monkeypatch):
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    monkeypatch.setattr(cmux, "new_workspace", lambda binary, args: "")
    monkeypatch.setattr(cmux, "workspace_ref", lambda output: "workspace:1")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0)
    )
    result = CliRunner().invoke(
        cli,
        ["ws", "create", "proj", "-i", "-d", "given", "--dir", str(tmp_path)],
        input="\n\n\n\n",
    )
    assert result.exit_code == 0, result.output
    assert (
        yaml.safe_load((tmp_path / "proj" / "workspace.yml").read_text())["description"]
        == "given"
    )


def test_ws_create_requires_work_dir_without_interactive():
    result = CliRunner().invoke(cli, ["ws", "create"])
    assert result.exit_code == 2
    assert "WORK_DIR" in result.output


def test_ws_create_manifest_without_extra_dirs(tmp_path):
    path = ws.write_manifest(tmp_path, "", [])
    assert yaml.safe_load(path.read_text()) == {
        "name": tmp_path.name,
        "description": "",
        "extra_dirs": [],
    }


def test_ws_open_missing_directory(tmp_path, monkeypatch):
    def fail() -> None:
        raise AssertionError("cmux should not start")

    monkeypatch.setattr(cmux, "start", fail)
    result = CliRunner().invoke(cli, ["ws", "open", "missing", "--dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "is not a directory" in result.output


def test_ws_list_names(tmp_path):
    (tmp_path / "beta").mkdir()
    (tmp_path / "alpha").mkdir()
    (tmp_path / "notes.txt").write_text("x")
    (tmp_path / ".hidden").mkdir()
    result = CliRunner().invoke(cli, ["ws", "list", "--dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == ["alpha", "beta"]


def test_ws_ls_is_list(tmp_path):
    (tmp_path / "alpha").mkdir()
    listed = CliRunner().invoke(cli, ["ws", "list", "--dir", str(tmp_path)])
    aliased = CliRunner().invoke(cli, ["ws", "ls", "--dir", str(tmp_path)])
    assert aliased.exit_code == 0, aliased.output
    assert aliased.output == listed.output
    assert "ls" in CliRunner().invoke(cli, ["ws", "--help"]).output


def test_ws_list_requires_dir():
    result = CliRunner().invoke(cli, ["ws", "list"])
    assert result.exit_code == 2
    assert "ws.dir" in result.output


def test_ws_list_interactive_opens_selection(tmp_path, monkeypatch):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    monkeypatch.setattr(ws, "choose", lambda names, index=0: ("open", 1))
    calls = []
    monkeypatch.setattr(ws, "open_root", lambda root, model=None, window=None: calls.append(root))
    result = CliRunner().invoke(cli, ["ws", "ls", "-i", "--dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert calls == [(tmp_path / "beta").resolve()]


def scripted_choose(actions):
    """Stand in for choose: replay actions and record the names shown each time."""
    shown = []

    def choose(names, index=0):
        shown.append((list(names), index))
        return actions.pop(0) if actions else None

    return choose, shown


def test_ws_get_shows_manifest_and_repos(tmp_path):
    root = tmp_path / "proj"
    (root / "api" / ".git").mkdir(parents=True)
    (root / "web" / ".git").mkdir(parents=True)
    (root / "scratch").mkdir()
    ws.write_manifest(root, "fix the thing", [Path("/tmp/notes")])
    result = CliRunner().invoke(cli, ["ws", "get", "proj", "--dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert yaml.safe_load(result.output) == {
        "name": "proj",
        "description": "fix the thing",
        "repos": ["api", "web"],
        "extra_dirs": ["/tmp/notes"],
    }


def test_ws_get_without_manifest(tmp_path):
    (tmp_path / "proj").mkdir()
    result = CliRunner().invoke(cli, ["ws", "get", "proj", "--dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert yaml.safe_load(result.output) == {
        "name": "proj",
        "description": "",
        "repos": [],
        "extra_dirs": [],
    }


def test_ws_get_missing_directory(tmp_path):
    result = CliRunner().invoke(cli, ["ws", "get", "missing", "--dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "is not a directory" in result.output


def test_ws_list_interactive_get_then_keeps_listing(tmp_path, monkeypatch):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    ws.write_manifest(tmp_path / "beta", "beta work", [])
    choose, shown = scripted_choose([("get", 1)])
    monkeypatch.setattr(ws, "choose", choose)
    result = CliRunner().invoke(cli, ["ws", "ls", "-i", "--dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "description: beta work" in result.output
    assert shown == [(["alpha", "beta   beta work"], 0), (["alpha", "beta   beta work"], 1)]


def test_ws_list_interactive_refreshes_jira(tmp_path, monkeypatch):
    from be import jira

    CliRunner().invoke(cli, ["config", "set", "jira.projects.ACME", "Acme"])
    tmp_path = tmp_path / "ws"
    (tmp_path / "ACME-1-x").mkdir(parents=True)
    (tmp_path / "notes").mkdir()
    ws.write_manifest(tmp_path / "ACME-1-x", "keep me", [])
    monkeypatch.setattr(jira, "issue_summary", lambda key: f"Summary of {key}")
    choose, shown = scripted_choose([("jira", 0), ("jira", 1)])
    monkeypatch.setattr(ws, "choose", choose)
    result = CliRunner().invoke(cli, ["ws", "ls", "-i", "--dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "ACME-1-x: Summary of ACME-1" in result.output
    assert "notes does not start with a key" in result.output
    manifest = yaml.safe_load((tmp_path / "ACME-1-x" / "workspace.yml").read_text())
    assert manifest["issue_name"] == "Summary of ACME-1"
    assert manifest["description"] == "keep me"
    assert not (tmp_path / "notes" / "workspace.yml").exists()


def test_workspace_labels(tmp_path):
    for name in ("ACME-1-x", "notes", "bare"):
        (tmp_path / name).mkdir()
    ws.write_manifest(tmp_path / "ACME-1-x", "login work", [], "Fix login")
    ws.write_manifest(tmp_path / "notes", "scratch", [])
    entries = [tmp_path / name for name in ("ACME-1-x", "notes", "bare")]
    assert ws.workspace_labels(entries) == [
        "ACME-1-x  Fix login - login work",
        "notes     scratch",
        "bare",
    ]


def stub_create(monkeypatch):
    calls = []
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    monkeypatch.setattr(cmux, "new_workspace", lambda binary, args: calls.append(args) or "")
    monkeypatch.setattr(cmux, "workspace_ref", lambda output: "workspace:1")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0))
    return calls


def window_arg(args):
    return args[args.index("--window") + 1] if "--window" in args else None


@pytest.fixture(autouse=True)
def inside_cmux(monkeypatch):
    """Run as if from a cmux terminal unless a test says otherwise."""
    monkeypatch.setenv("CMUX_WORKSPACE_ID", "test")


def test_ws_window_unset_outside_cmux_picks(monkeypatch):
    monkeypatch.delenv("CMUX_WORKSPACE_ID")
    windows = [{"id": "W0", "index": 0, "workspace_count": 2}, {"id": "W1", "index": 1, "workspace_count": 1}]
    monkeypatch.setattr(cmux, "list_windows", lambda binary: windows)
    monkeypatch.setattr(cmux, "current_window", lambda binary: pytest.fail("not inside cmux"))
    monkeypatch.setattr(cmux, "window_title", lambda binary, window: "t")
    seen = []
    monkeypatch.setattr(ws, "choose", lambda names, index=0, hint="": seen.append(names) or ("open", 1))
    assert ws.target_window("cmux", None) == "W1"
    assert seen == [["0: t (2 workspaces)", "1: t (1 workspaces)"]]
    assert ws.target_window("cmux", "2") == "2"


def test_ws_window_unset_inside_cmux_uses_callers_window(monkeypatch):
    monkeypatch.setattr(cmux, "list_windows", lambda binary: pytest.fail("listed windows"))
    assert ws.target_window("cmux", None) is None


def test_ws_create_window_passthrough(tmp_path, monkeypatch):
    calls = stub_create(monkeypatch)
    CliRunner().invoke(cli, ["ws", "create", "a", "--dir", str(tmp_path), "--window", "1"])
    CliRunner().invoke(cli, ["ws", "create", "b", "--dir", str(tmp_path)])
    assert [window_arg(args) for args in calls] == ["1", None]


def test_ws_create_window_pick(tmp_path, monkeypatch):
    calls = stub_create(monkeypatch)
    CliRunner().invoke(cli, ["config", "set", "cmux.window", "pick"])
    windows = [{"id": "W0", "index": 0, "workspace_count": 3}, {"id": "W1", "index": 1, "workspace_count": 1}]
    monkeypatch.setattr(cmux, "list_windows", lambda binary: windows)
    monkeypatch.setattr(cmux, "current_window", lambda binary: "W0")
    monkeypatch.setattr(cmux, "window_title", lambda binary, window: f"title {window}")
    seen = []

    def choose(names, index=0, hint=ws.LIST_HINT):
        seen.append((names, hint))
        return [("get", 0), ("open", 1)][len(seen) - 1]

    monkeypatch.setattr(ws, "choose", choose)
    result = CliRunner().invoke(cli, ["ws", "create", "a", "--dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert window_arg(calls[0]) == "W1"
    assert seen[0] == (
        ["0: title W0 (3 workspaces) - this window", "1: title W1 (1 workspaces)"],
        ws.WINDOW_HINT,
    )
    assert len(seen) == 2


def test_ws_window_pick_with_one_window_skips_prompt(tmp_path, monkeypatch):
    calls = stub_create(monkeypatch)
    monkeypatch.setattr(cmux, "list_windows", lambda binary: [{"id": "W0", "index": 0}])
    monkeypatch.setattr(ws, "choose", lambda *a, **k: pytest.fail("prompted"))
    result = CliRunner().invoke(cli, ["ws", "create", "a", "--dir", str(tmp_path), "--window", "pick"])
    assert result.exit_code == 0, result.output
    assert window_arg(calls[0]) is None


def test_ws_window_pick_quit_aborts(monkeypatch):
    monkeypatch.setattr(cmux, "list_windows", lambda binary: [{"id": "W0"}, {"id": "W1"}])
    monkeypatch.setattr(cmux, "current_window", lambda binary: None)
    monkeypatch.setattr(cmux, "window_title", lambda binary, window: "")
    monkeypatch.setattr(ws, "choose", lambda *a, **k: None)
    with pytest.raises(click.Abort):
        ws.target_window("cmux", "pick")


def test_ws_open_passes_window(tmp_path, monkeypatch):
    (tmp_path / "proj").mkdir()
    calls = []
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    monkeypatch.setattr(cmux, "get_layout", lambda binary, name: {"type": "terminal", "name": "claude"})
    monkeypatch.setattr(cmux, "new_workspace", lambda binary, args: calls.append(args) or "")
    result = CliRunner().invoke(cli, ["ws", "open", "proj", "--dir", str(tmp_path), "--window", "2"])
    assert result.exit_code == 0, result.output
    assert window_arg(calls[0]) == "2"


def test_ws_list_interactive_deletes_then_keeps_listing(tmp_path, monkeypatch):
    for name in ("alpha", "beta", "gamma"):
        (tmp_path / name).mkdir()
    choose, shown = scripted_choose([("delete", 2), ("delete", 1)])
    monkeypatch.setattr(ws, "choose", choose)
    deleted = []
    monkeypatch.setattr(cmux, "find_cmux", lambda: "cmux")
    monkeypatch.setattr(
        cmux, "delete_layout", lambda binary, name: deleted.append(name) or True
    )
    result = CliRunner().invoke(
        cli, ["ws", "ls", "-i", "--dir", str(tmp_path)], input="y\nn\n"
    )
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "gamma").exists()
    assert (tmp_path / "beta").is_dir()
    assert deleted == ["gamma"]
    assert shown == [
        (["alpha", "beta", "gamma"], 0),
        (["alpha", "beta"], 1),
        (["alpha", "beta"], 1),
    ]


def test_ws_list_interactive_delete_last_workspace(tmp_path, monkeypatch):
    (tmp_path / "alpha").mkdir()
    choose, _ = scripted_choose([("delete", 0)])
    monkeypatch.setattr(ws, "choose", choose)
    monkeypatch.setattr(cmux, "find_cmux", lambda: "cmux")
    monkeypatch.setattr(cmux, "delete_layout", lambda binary, name: True)
    result = CliRunner().invoke(
        cli, ["ws", "ls", "-i", "--dir", str(tmp_path)], input="y\n"
    )
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "alpha").exists()
    assert "no workspaces" in result.output


def test_ws_list_interactive_refuses_symlink(tmp_path, monkeypatch):
    target = tmp_path / "real"
    target.mkdir()
    (tmp_path / "link").symlink_to(target)
    choose, _ = scripted_choose([("delete", 0)])
    monkeypatch.setattr(ws, "choose", choose)
    result = CliRunner().invoke(cli, ["ws", "ls", "-i", "--dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "symlink" in result.output
    assert (tmp_path / "link").is_symlink()
    assert target.is_dir()


def test_ws_list_interactive_quit_does_not_open(tmp_path, monkeypatch):
    (tmp_path / "alpha").mkdir()

    def fail() -> None:
        raise AssertionError("cmux should not start")

    monkeypatch.setattr(ws, "choose", lambda names, index=0: None)
    monkeypatch.setattr(cmux, "start", fail)
    result = CliRunner().invoke(cli, ["ws", "list", "-i", "--dir", str(tmp_path)])
    assert result.exit_code == 0, result.output


def test_ws_list_interactive_needs_a_terminal(tmp_path):
    (tmp_path / "alpha").mkdir()
    result = CliRunner().invoke(cli, ["ws", "list", "-i", "--dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "needs a terminal" in result.output


def test_selection_enter_opens_current_row():
    assert ws.selection_action(1, 3, "\r") == (1, "open")
    assert ws.selection_action(1, 3, "\n") == (1, "open")
    assert ws.selection_action(0, 3, "down") == (1, "stay")
    assert ws.selection_action(0, 3, "up") == (2, "stay")
    assert ws.selection_action(1, 3, "q") == (1, "quit")
    assert ws.selection_action(1, 3, "d") == (1, "delete")
    assert ws.selection_action(1, 3, "g") == (1, "get")
    assert ws.selection_action(1, 3, "j") == (1, "jira")
    assert ws.selection_action(1, 3, "o") == (1, "browse")
    assert ws.selection_action(1, 3, "m") == (1, "toggle")
    assert ws.selection_action(1, 3, "a") == (1, "all")
    assert ws.selection_action(1, 3, "r") == (1, "ready")
    assert ws.selection_action(1, 3, "u") == (1, "automerge")


def test_read_key_arrow():
    read, write = os.pipe()
    try:
        os.write(write, b"\x1b[B")
        assert ws.read_key(read) == "down"
    finally:
        os.close(read)
        os.close(write)


def test_author_requires_env():
    result = CliRunner().invoke(
        cli, ["git", "author"], env={"GIT_EMAIL": None, "GIT_NAME": None}
    )
    assert result.exit_code == 2
    assert "--email" in result.output


def test_author_sets_config(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    result = CliRunner().invoke(
        cli, ["git", "author"], env={"GIT_EMAIL": "me@example.com", "GIT_NAME": "Me"}
    )
    assert result.exit_code == 0, result.output
    assert calls == [
        ["git", "config", "--global", "user.email", "me@example.com"],
        ["git", "config", "--global", "user.name", "Me"],
    ]


def test_clone_uses_org(monkeypatch):
    calls = []

    class Done:
        returncode = 0

    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **kw: calls.append(cmd) or Done()
    )
    result = CliRunner().invoke(
        cli, ["git", "clone", "repo", "dest"], env={"WORK_ORG": "acme"}
    )
    assert result.exit_code == 0, result.output
    assert calls == [
        ["git", "clone", "--recurse-submodules", "git@github.com:acme/repo.git", "dest"]
    ]


def test_clone_without_org_errors():
    result = CliRunner().invoke(cli, ["git", "clone", "repo"], env={"WORK_ORG": None})
    assert result.exit_code == 2
    assert "WORK_ORG" in result.output


def test_pr_r_is_review_alias():
    result = CliRunner().invoke(cli, ["pr", "r", "--help"])
    assert result.exit_code == 0, result.output
    assert "/pr-review" in result.output


def make_workspace(tmp_path):
    workspace = tmp_path / "proj"
    (workspace / "repo").mkdir(parents=True)
    (workspace / "workspace.yml").write_text('name: "proj"\n')
    return workspace


def test_ws_delete_removes_directory_and_layout(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path)
    deleted = []
    monkeypatch.setattr(cmux, "find_cmux", lambda: "cmux")
    monkeypatch.setattr(
        cmux, "delete_layout", lambda binary, name: deleted.append(name) or True
    )
    result = CliRunner().invoke(
        cli, ["ws", "delete", "proj", "--dir", str(tmp_path)], input="y\n"
    )
    assert result.exit_code == 0, result.output
    assert not workspace.exists()
    assert tmp_path.is_dir()
    assert deleted == ["proj"]


def test_ws_delete_declined_keeps_everything(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path)
    monkeypatch.setattr(
        cmux,
        "delete_layout",
        lambda *a: (_ for _ in ()).throw(AssertionError("should not delete")),
    )
    result = CliRunner().invoke(
        cli, ["ws", "rm", "proj", "--dir", str(tmp_path)], input="n\n"
    )
    assert result.exit_code == 1
    assert workspace.is_dir()


def test_ws_delete_dry_run(tmp_path):
    workspace = make_workspace(tmp_path)
    result = CliRunner().invoke(
        cli, ["ws", "delete", "proj", "--dir", str(tmp_path), "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert str(workspace.resolve()) in result.output
    assert workspace.is_dir()


def test_ws_delete_keep_layout(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path)
    monkeypatch.setattr(
        cmux,
        "find_cmux",
        lambda: (_ for _ in ()).throw(AssertionError("should not run cmux")),
    )
    result = CliRunner().invoke(
        cli, ["ws", "delete", "proj", "--dir", str(tmp_path), "--keep-layout", "-y"]
    )
    assert result.exit_code == 0, result.output
    assert not workspace.exists()


def test_ws_delete_layout_failure_still_deletes_directory(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path)
    monkeypatch.setattr(cmux, "find_cmux", lambda: "cmux")
    monkeypatch.setattr(cmux, "delete_layout", lambda binary, name: False)
    result = CliRunner().invoke(
        cli, ["ws", "delete", "proj", "--dir", str(tmp_path), "-y"]
    )
    assert result.exit_code == 0, result.output
    assert not workspace.exists()
    assert "could not delete cmux layout proj" in result.output


def test_ws_delete_refuses_parent_and_home(tmp_path, monkeypatch):
    make_workspace(tmp_path)
    for name in (".", str(tmp_path), "~"):
        result = CliRunner().invoke(
            cli, ["ws", "delete", name, "--dir", str(tmp_path), "-y"]
        )
        assert result.exit_code == 1
        assert "refusing to delete" in result.output
    assert tmp_path.is_dir()


def test_ws_delete_missing_or_symlink(tmp_path):
    target = make_workspace(tmp_path)
    (tmp_path / "link").symlink_to(target)
    for name in ("missing", "link"):
        result = CliRunner().invoke(
            cli, ["ws", "delete", name, "--dir", str(tmp_path), "-y"]
        )
        assert result.exit_code == 1
        assert "not a workspace directory" in result.output
    assert target.is_dir()
    assert (tmp_path / "link").is_symlink()
