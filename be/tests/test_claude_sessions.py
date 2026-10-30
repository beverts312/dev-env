import json
import os

import click
import pytest

from be import claude_sessions

ROOT_ID = "11111111-1111-1111-1111-111111111111"
SUB_ID = "22222222-2222-2222-2222-222222222222"
OTHER_ID = "33333333-3333-3333-3333-333333333333"


def transcript(home, cwd, session_id, *records, mtime=None):
    folder = home / ".claude" / "projects" / claude_sessions.project_key(cwd)
    folder.mkdir(parents=True, exist_ok=True)
    lines = [{"type": "mode", "mode": "normal"}, {"type": "user", "cwd": str(cwd), "timestamp": "t"}, *records]
    file = folder / f"{session_id}.jsonl"
    file.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in lines))
    if mtime:
        os.utime(file, (mtime, mtime))
    return file


@pytest.fixture
def spaces(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    root = tmp_path / "ws" / "ADC-1"
    (root / "api").mkdir(parents=True)
    transcript(home, root, ROOT_ID, {"type": "ai-title", "aiTitle": "Old"}, {"type": "ai-title", "aiTitle": "Fix login"},
               {"type": "last-prompt", "lastPrompt": "commit it"}, mtime=1000)
    transcript(home, root / "api", SUB_ID, {"type": "last-prompt", "lastPrompt": "run tests"}, mtime=2000)
    # a sibling workspace whose folder key starts with root's
    transcript(home, tmp_path / "ws" / "ADC-1-foo", OTHER_ID, {"type": "custom-title", "customTitle": "Other"})
    return home, root


def test_lists_root_and_subfolder_sessions(spaces):
    _, root = spaces
    sessions = claude_sessions.list_sessions(root)
    assert [s["id"] for s in sessions] == [SUB_ID, ROOT_ID]
    sub, top = sessions
    assert (top["title"], top["last_prompt"], top["subdir"], top["cwd"]) == ("Fix login", "commit it", "", str(root))
    # no title: the last prompt
    assert (sub["title"], sub["subdir"], sub["cwd"]) == ("run tests", "api", str(root / "api"))


def test_custom_title_wins(spaces):
    home, root = spaces
    transcript(home, root, ROOT_ID, {"type": "ai-title", "aiTitle": "Fix login"}, {"type": "custom-title", "customTitle": "Mine"})
    assert claude_sessions.get_session(root, ROOT_ID)["title"] == "Mine"


def test_no_projects_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert claude_sessions.list_sessions(tmp_path / "ws") == []


def test_delete_removes_transcript_and_its_folder(spaces):
    home, root = spaces
    folder = home / ".claude" / "projects" / claude_sessions.project_key(root)
    (folder / ROOT_ID / "subagents").mkdir(parents=True)
    assert claude_sessions.delete_session(root, ROOT_ID)["title"] == "Fix login"
    assert not (folder / f"{ROOT_ID}.jsonl").exists() and not (folder / ROOT_ID).exists()
    assert [s["id"] for s in claude_sessions.list_sessions(root)] == [SUB_ID]


def test_delete_only_this_workspaces_sessions(spaces):
    _, root = spaces
    with pytest.raises(click.ClickException, match="no session"):
        claude_sessions.delete_session(root, OTHER_ID)
    with pytest.raises(click.ClickException, match="not a session id"):
        claude_sessions.delete_session(root, "../../etc")


def test_delete_all_leaves_others_and_kept_memory(spaces, tmp_path):
    home, root = spaces
    projects = home / ".claude" / "projects"
    (projects / claude_sessions.project_key(root) / "memory").mkdir()
    (projects / claude_sessions.project_key(root / "api") / "memory").mkdir()
    (projects / claude_sessions.project_key(root / "api") / "memory" / "MEMORY.md").write_text("x")
    assert claude_sessions.delete_all(root) == 2
    assert claude_sessions.list_sessions(root) == []
    # its folder is gone; the subfolder's keeps its memory; the sibling workspace's session stays
    assert not (projects / claude_sessions.project_key(root)).exists()
    assert (projects / claude_sessions.project_key(root / "api") / "memory" / "MEMORY.md").exists()
    assert [s["id"] for s in claude_sessions.list_sessions(tmp_path / "ws" / "ADC-1-foo")] == [OTHER_ID]
