import datetime as dt

import click
from click.testing import CliRunner
import pytest

from be import todo
from be.cli import cli

TODAY = dt.date(2026, 10, 28)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(todo, "today", lambda: TODAY)


@pytest.fixture
def root(tmp_path, monkeypatch):
    path = tmp_path / "todos"
    monkeypatch.setenv("BE_TODO_DIR", str(path))
    return path


def run(*args):
    result = CliRunner().invoke(cli, ["todo", *args])
    assert result.exit_code == 0, result.output
    return result.output


def test_parse_due():
    assert todo.parse_due("2026-11-03") == "2026-11-03"
    assert todo.parse_due("today") == "2026-10-28"
    assert todo.parse_due("Tomorrow") == "2026-10-29"
    assert todo.parse_due("+3d") == "2026-10-31"
    assert todo.parse_due("+2w") == "2026-11-11"
    assert todo.parse_due("") is None
    with pytest.raises(click.ClickException):
        todo.parse_due("soon")


def test_add_writes_markdown(root):
    added = todo.add(root, "Renew the prod cert!", "+3d", "HIGH", ["infra", "infra", " oncall "], "adc-1", "see runbook")
    assert added["id"] == "renew-the-prod-cert"
    assert (root / "renew-the-prod-cert.md").read_text() == (
        "---\ntitle: Renew the prod cert!\nstatus: open\npriority: high\ndue: 2026-10-31\njira: ADC-1\n"
        "tags: [infra, oncall]\ncreated: 2026-10-28\n---\n\nsee runbook\n"
    )
    assert todo.add(root, "renew the prod cert")["id"] == "renew-the-prod-cert-2"


def test_add_rejects_bad_fields(root):
    for kwargs in ({"priority": "urgent"}, {"key": "not a key"}, {"due": "later"}):
        with pytest.raises(click.ClickException):
            todo.add(root, "x", **kwargs)
    with pytest.raises(click.ClickException):
        todo.add(root, "  ")


def test_list_order(root):
    todo.add(root, "no due")
    todo.add(root, "later low", "+5d", "low")
    todo.add(root, "later high", "+5d", "high")
    todo.add(root, "overdue", "2026-01-01")
    todo.add(root, "soon", "tomorrow")
    assert [t["id"] for t in todo.list_todos(root)] == ["overdue", "soon", "later-high", "later-low", "no-due"]
    assert todo.list_todos(root)[0]["overdue"]


def test_filters(root):
    todo.add(root, "a", tags=["work"], key="ACME-1")
    todo.add(root, "b", tags=["home"])
    assert [t["id"] for t in todo.list_todos(root, tag="work")] == ["a"]
    assert [t["id"] for t in todo.list_todos(root, key="acme-1")] == ["a"]


def test_done_moves_and_reopen(root):
    todo.add(root, "ship it", "2026-01-01")
    done = todo.set_done(root, "ship")
    assert not (root / "ship-it.md").exists() and (root / "done" / "ship-it.md").exists()
    assert done["status"] == "done" and done["completed"] == "2026-10-28" and not done["overdue"]
    assert todo.list_todos(root) == []
    assert [t["id"] for t in todo.list_todos(root, only_done=True)] == ["ship-it"]
    reopened = todo.set_done(root, "ship-it", False)
    assert reopened["status"] == "open" and reopened["completed"] is None
    assert (root / "ship-it.md").exists() and not (root / "done" / "ship-it.md").exists()


def test_find(root):
    todo.add(root, "buy milk")
    todo.add(root, "buy bread")
    todo.add(root, "buy")
    assert todo.find(root, "buy").stem == "buy"
    assert todo.find(root, "buy-m").stem == "buy-milk"
    with pytest.raises(click.ClickException, match="matches"):
        todo.remove(root, "buy-")
    with pytest.raises(click.ClickException, match="no todo"):
        todo.find(root, "nope")
    with pytest.raises(click.ClickException):
        todo.find(root, "../x")


def test_hand_written_files(root):
    root.mkdir()
    (root / "plain.md").write_text("just some notes\n")
    (root / "custom.md").write_text("---\ntitle: Custom\nowner: me\ndue: 2026-12-01\n---\nbody\n")
    plain, custom = todo.load(root / "plain.md"), todo.load(root / "custom.md")
    assert plain["title"] == "plain" and plain["notes"] == "just some notes"
    assert custom["due"] == "2026-12-01" and custom["owner"] == "me"
    todo.update(root, "custom", priority="low", notes="new body")
    text = (root / "custom.md").read_text()
    assert "owner: me" in text and "priority: low" in text and text.endswith("\nnew body\n")


def test_update_clears(root):
    todo.add(root, "x", "+1d", "high", ["a"], "ACME-1")
    updated = todo.update(root, "x", due="", priority="", tags=[], jira="", title=None)
    assert (updated["due"], updated["priority"], updated["tags"], updated["jira"]) == (None, None, [], None)
    assert updated["title"] == "x"
    with pytest.raises(click.ClickException):
        todo.update(root, "x", status="done")


def test_cli(root):
    assert run("add", "Renew", "cert", "-d", "2026-01-01", "-p", "high", "-t", "infra", "-j", "adc-1") == "renew-cert\n"
    assert run("add", "buy milk") == "buy-milk\n"
    assert run("ls").splitlines() == [
        "renew-cert  ! 2026-01-01  high  ADC-1  #infra  Renew cert",
        "buy-milk                                       buy milk",
    ]
    assert run("done", "renew") == "done renew-cert\n"
    assert run("ls") == "buy-milk  buy milk\n"
    assert run("ls", "--done") == "renew-cert  x 2026-01-01  high  ADC-1  #infra  Renew cert\n"
    assert "title: Renew cert" in run("show", "renew")
    assert run("reopen", "renew") == "reopened renew-cert\n"
    assert run("rm", "-y", "buy") == "deleted buy-milk\n"
    assert run("path") == f"{root}\n"
    assert run("ls", "-t", "nope") == "no todos\n"
