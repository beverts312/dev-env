import json
import os
import subprocess

from click.testing import CliRunner

from be import cmux
from be.cli import cli
from be.commands import ws


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
            {"pane": {"surfaces": [{"type": "terminal", "name": "claude", "focus": True}]}},
            {"pane": {"surfaces": [{"type": "terminal", "name": "repo", "cwd": "repo"}]}},
        ],
    }
    calls = []
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    monkeypatch.setattr(cmux, "get_layout", lambda binary, name: layout)
    monkeypatch.setattr(cmux, "new_workspace", lambda binary, args: calls.append(args) or "")
    result = CliRunner().invoke(cli, ["ws", "open", "proj", "--dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(calls[0][calls[0].index("--layout") + 1])
    claude = payload["children"][0]["pane"]["surfaces"][0]
    assert claude["command"] == "claude --model claude-opus-5-5"
    assert claude["cwd"] == str(workspace.resolve())
    assert "command" not in payload["children"][1]["pane"]["surfaces"][0]


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
    monkeypatch.setattr(ws, "choose", lambda names: names[1])
    calls = []
    monkeypatch.setattr(ws, "open_root", lambda root, model=None: calls.append(root))
    result = CliRunner().invoke(cli, ["ws", "ls", "-i", "--dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert calls == [(tmp_path / "beta").resolve()]


def test_ws_list_interactive_quit_does_not_open(tmp_path, monkeypatch):
    (tmp_path / "alpha").mkdir()

    def fail() -> None:
        raise AssertionError("cmux should not start")

    monkeypatch.setattr(ws, "choose", lambda names: None)
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


def test_read_key_arrow():
    read, write = os.pipe()
    try:
        os.write(write, b"\x1b[B")
        assert ws.read_key(read) == "down"
    finally:
        os.close(read)
        os.close(write)


def test_author_requires_env():
    result = CliRunner().invoke(cli, ["git", "author"], env={"GIT_EMAIL": None, "GIT_NAME": None})
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

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd) or Done())
    result = CliRunner().invoke(cli, ["git", "clone", "repo", "dest"], env={"WORK_ORG": "acme"})
    assert result.exit_code == 0, result.output
    assert calls == [
        ["git", "clone", "--recurse-submodules", "git@github.com:acme/repo.git", "dest"]
    ]


def test_clone_without_org_errors():
    result = CliRunner().invoke(cli, ["git", "clone", "repo"], env={"WORK_ORG": None})
    assert result.exit_code == 2
    assert "WORK_ORG" in result.output
