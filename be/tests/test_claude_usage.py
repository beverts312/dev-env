import json
import subprocess

import click
import pytest

from be import claude_usage

TEXT = """You are currently using your subscription to power your Claude Code usage

Current session: 9% used · resets Oct 28 at 9:39pm (America/Denver)
Current week (all models): 18% used · resets Oct 30 at 10:59am (America/Denver)

What's contributing to your limits usage?

Last 24h · 49 requests · 2 sessions
  64% of your usage was at >150k context"""


def test_parse():
    out = claude_usage.parse(TEXT)
    assert out["limits"] == [
        {"label": "Current session", "percent": 9, "resets": "Oct 28 at 9:39pm (America/Denver)"},
        {"label": "Current week (all models)", "percent": 18, "resets": "Oct 30 at 10:59am (America/Denver)"},
    ]
    assert out["plan_note"].startswith("You are currently using your subscription")
    assert out["details"].startswith("What's contributing")
    assert out["details"].endswith(">150k context")
    assert out["raw"] == TEXT


def test_parse_without_limits():
    out = claude_usage.parse("You are using an API key")
    assert out["limits"] == []
    assert out["details"] == ""
    assert out["raw"] == "You are using an API key"


def ran(monkeypatch, code=0, stdout="", stderr=""):
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, code, stdout, stderr)

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_fetch(monkeypatch):
    calls = ran(monkeypatch, stdout=json.dumps({"is_error": False, "result": TEXT}))
    assert claude_usage.fetch() == TEXT
    assert calls[0][0] == claude_usage.CMD


@pytest.mark.parametrize("code,stdout,message", [
    (1, "", "failed: boom"),
    (0, json.dumps({"is_error": True, "result": "not logged in"}), "not logged in"),
    (0, "nope", "no JSON"),
])
def test_fetch_errors(monkeypatch, code, stdout, message):
    ran(monkeypatch, code, stdout, "boom" if code else "")
    with pytest.raises(click.ClickException, match=message):
        claude_usage.fetch()


def test_fetch_without_claude(monkeypatch):
    def run(*args, **kwargs):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(click.ClickException, match="not on PATH"):
        claude_usage.fetch()
