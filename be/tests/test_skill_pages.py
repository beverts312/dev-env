import json
import os
import subprocess

import click
import pytest

from be import config, skill_pages


class FakeProc:
    def __init__(self, code=None):
        self.code = code

    def poll(self):
        return self.code


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(skill_pages, "PAGES_DIR", tmp_path / "pages")
    return tmp_path


def test_latest_picks_newest(tmp_path):
    assert skill_pages.latest(str(tmp_path / "*.html")) is None
    old, new = tmp_path / "a.html", tmp_path / "b.html"
    old.write_text("old")
    new.write_text("new")
    os.utime(old, (1, 1))
    assert skill_pages.latest(str(tmp_path / "*.html")) == new


def test_pages_fill_defaults_and_skip_incomplete(home, isolated_config):
    config.set_value("pages.finops.skill", "/gcp-spend")
    config.set_value("pages.finops.output", "~/r/*.html")
    config.set_value("pages.bad.skill", "x")
    assert skill_pages.pages() == {
        "finops": {
            "name": "finops",
            "skill": "gcp-spend",
            "output": "~/r/*.html",
            "icon": "file-text",
            "prompt": "",
            "cwd": str(home / "pages" / "finops"),
        }
    }


def page(home, **kw):
    return {"name": "finops", "skill": "gcp-spend", "output": "", "icon": "", "prompt": "", "cwd": str(home / "pages" / "finops"), **kw}


def test_start_runs_from_default_dir(home, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: calls.append((cmd, kw)) or FakeProc())
    run = skill_pages.start(page(home, prompt="last 7 days"), "opus")
    (cmd, kw), = calls
    assert cmd == [
        "claude", "-p", "/gcp-spend last 7 days", "--output-format", "stream-json", "--verbose", "--model", "opus"
    ]
    assert kw["cwd"] == home / "pages" / "finops" and kw["cwd"].is_dir()
    assert run.log == home / "pages" / "finops" / "last-run.log"


def test_start_runs_from_configured_cwd(home, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: calls.append(kw) or FakeProc())
    with pytest.raises(click.ClickException, match="not a directory"):
        skill_pages.start(page(home, cwd=str(home / "missing")), None)
    (home / "proj").mkdir()
    run = skill_pages.start(page(home, cwd=str(home / "proj")), None)
    assert calls[0]["cwd"] == home / "proj"
    assert run.log == home / "pages" / "finops" / "last-run.log"


def test_status(tmp_path):
    assert skill_pages.status(None)["running"] is False
    log = tmp_path / "log"
    log.write_text("\n".join(f"line {i}" for i in range(100)))
    going = skill_pages.status(skill_pages.Run(FakeProc(), 5.0, log))
    assert going == {"running": True, "started_at": 5.0, "exit_code": None, "error": None}
    assert skill_pages.status(skill_pages.Run(FakeProc(0), 5.0, log))["error"] is None
    failed = skill_pages.status(skill_pages.Run(FakeProc(1), 5.0, log))
    assert failed["error"].startswith("claude exited 1\nline 60\n") and failed["error"].endswith("line 99")


A1 = "https://claude.ai/artifact/abc-123"
A2 = "https://claude.ai/code/artifact/0f9e8d7c"


def stream(*events):
    return "\n".join(json.dumps(e) for e in events) + "\n"


def test_read_log(tmp_path):
    log = tmp_path / "log"
    assert skill_pages.read_log(log) == {"links": [], "result": None, "is_error": False, "tail": []}
    log.write_text(stream(
        {"type": "system", "subtype": "init"},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": f"published {A1}"}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": f"updated {A2}"}]}},
        {"type": "result", "result": f"Report: {A1}", "is_error": False},
    ))
    found = skill_pages.read_log(log)
    assert found["links"] == [A1, A2]
    assert found["result"] == f"Report: {A1}" and found["is_error"] is False


def test_status_explains_failure_with_result(tmp_path):
    log = tmp_path / "log"
    log.write_text(stream({"type": "system"}, {"type": "result", "result": "no BigQuery access", "is_error": True}))
    failed = skill_pages.status(skill_pages.Run(FakeProc(1), 5.0, log))
    assert failed["error"] == "claude exited 1\nno BigQuery access"
    # an error result fails the run even when claude exits 0
    assert skill_pages.status(skill_pages.Run(FakeProc(0), 5.0, log))["error"] == "claude exited 0\nno BigQuery access"
