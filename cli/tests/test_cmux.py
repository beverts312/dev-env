import json
import subprocess

import click
import pytest

from be import cmux
from be.cmux import focus_existing as real_focus_existing

WINDOWS = [{"id": "w1", "index": 1}, {"id": "w2", "index": 2}]
WORKSPACES = {
    "w1": [{"ref": "workspace:1", "id": "a", "title": "other", "selected": True}],
    "w2": [
        {"ref": "workspace:2", "id": "b", "title": "Fix login", "selected": False},
        {"ref": "workspace:3", "id": "c", "title": "Fix login", "selected": True},
    ],
}


@pytest.fixture
def fake_cmux(monkeypatch):
    """Stand in for the cmux binary; returns the argv of each call, and lets tests fail commands."""
    calls = []
    failing = set()

    def run(args, **kwargs):
        calls.append(args)
        if args[1:3] == ["workspace", "list"]:
            out = json.dumps({"workspaces": WORKSPACES[args[4]]})
        else:
            out = ""
        code = 1 if args[1] in failing else 0
        return subprocess.CompletedProcess(args, code, out, "boom\n" if code else "")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(cmux, "list_windows", lambda binary: WINDOWS)
    monkeypatch.setattr(cmux, "focus_existing", real_focus_existing)
    return calls, failing


def test_find_workspace_searches_every_window(fake_cmux):
    assert cmux.find_workspace("cmux", "Fix login") == ("w2", "b")
    assert cmux.find_workspace("cmux", "nope") is None


def test_focus_existing_selects_the_workspace(fake_cmux, monkeypatch):
    calls, _ = fake_cmux
    monkeypatch.setenv("CMUX_WORKSPACE_ID", "x")
    assert cmux.focus_existing("cmux", "Fix login") is True
    switched = [c for c in calls if c[1:2] != ["workspace"]]
    assert switched == [
        ["cmux", "focus-window", "--window", "w2"],
        ["cmux", "select-workspace", "--workspace", "b", "--window", "w2"],
    ]


def test_focus_existing_raises_cmux_from_outside(fake_cmux, monkeypatch):
    calls, _ = fake_cmux
    monkeypatch.delenv("CMUX_WORKSPACE_ID", raising=False)
    assert cmux.focus_existing("cmux", "Fix login") is True
    assert calls[-1] == ["open", "-a", "cmux"]


def test_focus_existing_none_open(fake_cmux):
    calls, _ = fake_cmux
    assert cmux.focus_existing("cmux", "nope") is False
    assert all(c[1] == "workspace" for c in calls)


def test_show_workspace_reports_failure(fake_cmux):
    _, failing = fake_cmux
    failing.add("select-workspace")
    with pytest.raises(click.ClickException, match="could not switch"):
        cmux.show_workspace("cmux", "w2", "b")


def test_window_title_uses_selected_workspace(fake_cmux):
    assert cmux.window_title("cmux", "w2") == "Fix login"
    assert cmux.window_title("cmux", "w1") == "other"
