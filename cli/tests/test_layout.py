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
