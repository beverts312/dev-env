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
