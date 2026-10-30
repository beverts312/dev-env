import importlib.util
import json
from pathlib import Path

import click
import pytest

from be.commands import ws
from be.github import repo_slug

ORIGINAL = Path(__file__).resolve().parents[2] / "scripts" / "workspace_setup.py"


def load_original():
    spec = importlib.util.spec_from_file_location("workspace_setup", ORIGINAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repo_slug():
    assert repo_slug("owner/repo", None) == "owner/repo"
    assert repo_slug("repo", "org") == "org/repo"
    with pytest.raises(click.UsageError):
        repo_slug("repo", None)


def test_workspace_root_relative_uses_parent(tmp_path):
    assert ws.workspace_root("proj", str(tmp_path)) == (tmp_path / "proj").resolve()


def test_workspace_root_absolute_ignores_parent(tmp_path):
    absolute = tmp_path / "proj"
    assert ws.workspace_root(str(absolute), "/elsewhere") == absolute.resolve()


def test_workspace_root_expands_user(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert ws.workspace_root("proj", "~/workspaces") == (tmp_path / "workspaces" / "proj").resolve()


def test_workspace_root_unset_parent_is_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert ws.workspace_root("proj", None) == (tmp_path / "proj").resolve()


def test_stamp_claude_targets_named_pane():
    layout = {
        "children": [
            {"pane": {"surfaces": [{"type": "terminal", "name": "claude"}]}},
            {"pane": {"surfaces": [{"type": "terminal", "name": "repo"}]}},
        ]
    }
    ws.stamp_claude(layout, "claude --model m", "/work")
    assert layout["children"][0]["pane"]["surfaces"][0]["command"] == "claude --model m"
    assert layout["children"][1]["pane"]["surfaces"][0].get("command") is None


def test_stamp_claude_uses_only_pane_when_unnamed():
    layout = {"pane": {"surfaces": [{"type": "terminal"}]}}
    ws.stamp_claude(layout, "claude", "/work")
    assert layout["pane"]["surfaces"][0]["command"] == "claude"


def test_stamp_claude_requires_a_main_pane():
    layout = {
        "children": [
            {"pane": {"surfaces": [{"type": "terminal", "name": "a"}]}},
            {"pane": {"surfaces": [{"type": "terminal", "name": "b"}]}},
        ]
    }
    with pytest.raises(click.ClickException, match="claude pane"):
        ws.stamp_claude(layout, "claude", "/work")


def test_pane_name_dedupes():
    used: set[str] = set()
    assert [ws.pane_name("a", used) for _ in range(3)] == ["a", "a-2", "a-3"]


def test_claude_command_quotes():
    cmd = ws.claude_command([Path("/tmp/with space")], "m")
    assert cmd == "claude --model m --add-dir '/tmp/with space'"


@pytest.mark.skipif(not ORIGINAL.exists(), reason="original script not present")
def test_layout_matches_original(tmp_path):
    original = load_original()
    extra = [tmp_path / "notes", tmp_path / "other" / "notes"]
    args = (tmp_path, ["api", "web"], extra, "claude-opus-5-5")
    assert json.dumps(ws.build_layout(*args)) == json.dumps(original.build_layout(*args))


def test_start_work_opens_plan_mode_pane(tmp_path, monkeypatch):
    from be import cmux

    root = tmp_path / "my proj"
    root.mkdir()
    (root / "workspace.yml").write_text("issue_name: Fix login\n")
    opened, panes = [], []
    monkeypatch.setattr(ws, "open_root", lambda root, model=None, window=None: opened.append((root, model, window)))
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    monkeypatch.setattr(cmux, "find_workspace", lambda binary, title: ("w1", "ws1") if title == "Fix login" else None)
    monkeypatch.setattr(cmux, "new_pane", lambda *args: panes.append(args))
    ws.start_work(root, "ACME-12", "opus", "w1")
    assert opened == [(root, "opus", "w1")]
    assert panes == [
        ("cmux", "w1", "ws1", f"cd '{root}' && claude --model opus --permission-mode plan 'lets get started on ACME-12'")
    ]


def test_resume_session_opens_pane_in_its_folder(tmp_path, monkeypatch):
    from be import cmux

    monkeypatch.setattr(ws, "open_root", lambda root, model=None, window=None: None)
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    monkeypatch.setattr(cmux, "find_workspace", lambda binary, title: ("w1", "ws1"))
    panes = []
    monkeypatch.setattr(cmux, "new_pane", lambda *args: panes.append(args))
    ws.resume_session(tmp_path, tmp_path / "api", "abc", "opus")
    assert panes == [("cmux", "w1", "ws1", f"cd {tmp_path / 'api'} && claude --model opus --resume abc")]


def test_start_work_needs_the_open_workspace(tmp_path, monkeypatch):
    from be import cmux

    monkeypatch.setattr(ws, "open_root", lambda root, model=None, window=None: None)
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    monkeypatch.setattr(cmux, "find_workspace", lambda binary, title: None)
    with pytest.raises(click.ClickException, match="could not find"):
        ws.start_work(tmp_path, "ACME-12", "opus")


def test_cloud_issue_opens_claude_in_ws_dir(tmp_path, monkeypatch):
    from be import cmux, config

    config.set_value("ws.dir", str(tmp_path))
    created = []
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    monkeypatch.setattr(cmux, "new_workspace", lambda binary, args: created.append((binary, args)))
    ws.cloud_issue("rotate the NAT gateway's IP", "opus", "w1")
    assert created == [
        (
            "cmux",
            ["--name", "cloud issue", "--cwd", str(tmp_path), "--focus", "true", "--command",
             "claude --model opus '/cloud-issue rotate the NAT gateway'\"'\"'s IP'", "--window", "w1"],
        )
    ]


def test_cloud_issue_defaults_to_home(monkeypatch):
    from be import cmux

    created = []
    monkeypatch.setattr(cmux, "start", lambda: "cmux")
    monkeypatch.setattr(cmux, "new_workspace", lambda binary, args: created.append(args))
    ws.cloud_issue("x", "opus", "w1")
    assert created[0][3] == str(Path.home())
