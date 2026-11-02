import asyncio
import logging

from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError
import pytest

from be import config, todo
from be.server import app, mcp

HEADERS = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("BE_TODO_DIR", str(tmp_path / "todos"))
    return tmp_path / "todos"


def call(server, name, **args):
    return asyncio.run(server.call_tool(name, args))


def result(server, name, **args):
    found = call(server, name, **args)
    assert not found.is_error, found.content
    return found.structured_content


def test_tools(root):
    server = mcp.build()
    added = result(server, "add_todo", title="Ship it", due="2026-11-03", priority="high", tags=["work"], jira="adc-1")
    assert (added["id"], added["jira"], added["tags"]) == ("ship-it", "ADC-1", ["work"])
    assert (root / "ship-it.md").exists()
    assert [t["id"] for t in result(server, "list_todos", tag="work")["result"]] == ["ship-it"]
    updated = result(server, "update_todo", ref="ship", notes="details", priority="")
    assert (updated["notes"], updated["priority"], updated["due"]) == ("details", None, "2026-11-03")
    assert result(server, "get_todo", ref="ship-it")["notes"] == "details"
    done = result(server, "complete_todo", ref="ship-it")
    assert done["status"] == "done" and "overdue" not in done
    assert result(server, "list_todos")["result"] == []
    assert [t["id"] for t in result(server, "list_todos", only_done=True)["result"]] == ["ship-it"]
    assert result(server, "reopen_todo", ref="ship-it")["status"] == "open"
    assert result(server, "delete_todo", ref="ship-it") == {"result": "deleted ship-it"}
    assert not list(root.rglob("*.md"))


def test_tool_errors(root):
    server = mcp.build()
    for name, args, message in (
        ("complete_todo", {"ref": "nope"}, "no todo nope"),
        ("add_todo", {"title": "x", "due": "someday"}, "bad due date"),
        ("add_todo", {"title": " "}, "needs a title"),
    ):
        with pytest.raises(ToolError, match=message):
            call(server, name, **args)


def test_config_tools(isolated_config, monkeypatch):
    server = mcp.build()
    assert result(server, "set_config", key="git.name", value="Me") == {"result": "saved git.name"}
    assert result(server, "set_config", key="jira.projects.ADC", value="Ads")["result"] == "saved jira.projects.ADC"
    result(server, "set_config", key="jira.token", value="hunter2")
    assert config.file_value("jira.projects") == {"ADC": "Ads"}
    assert result(server, "get_config", key="git.name") == {"key": "git.name", "value": "Me", "source": "file"}
    assert result(server, "get_config", key="jira.projects.ADC")["value"] == "Ads"
    assert result(server, "get_config", key="jira.token")["value"] == "********"
    listed = result(server, "list_config")
    assert listed["path"] == str(isolated_config)
    rows = {r["key"]: r for r in listed["settings"]}
    assert rows["server.log_level"]["choices"] == ["debug", "info", "warning", "error"]
    assert (rows["todo.dir"]["value"], rows["todo.dir"]["source"]) == ("~/notes/todos", "default")
    assert rows["jira.token"]["value"] == "********" and rows["pages"]["fields"][0] == "skill"
    monkeypatch.setenv("GIT_NAME", "Env")
    assert "GIT_NAME is set and overrides it" in result(server, "set_config", key="git.name", value="Me")["result"]
    assert result(server, "unset_config", key="git.name") == {"result": "removed git.name"}
    assert result(server, "set_config", key="jira.projects.ADC", value="") == {"result": "removed jira.projects.ADC"}
    assert config.file_value("git.name") is None and config.file_value("jira.projects") is None


def test_config_tool_errors(isolated_config):
    server = mcp.build()
    for name, args, message in (
        ("get_config", {"key": "nope"}, "unknown key 'nope'"),
        ("set_config", {"key": "nope", "value": "x"}, "unknown key 'nope'"),
        ("set_config", {"key": "server.log_level", "value": "loud"}, "must be one of debug"),
        ("set_config", {"key": "pages.mail.nope", "value": "x"}, "unknown field 'nope'"),
        ("unset_config", {"key": "nope"}, "unknown key 'nope'"),
    ):
        with pytest.raises(ToolError, match=message):
            call(server, name, **args)


def test_set_log_level_applies(isolated_config):
    logger = logging.getLogger("be")
    before = logger.level
    try:
        call(mcp.build(app.State()), "set_config", key="server.log_level", value="debug")
        assert logger.level == logging.DEBUG
        logger.setLevel(logging.WARNING)
        # --log-level was given, so the saved one waits for a restart
        call(mcp.build(app.State(fixed=("server.log_level",))), "set_config", key="server.log_level", value="info")
        assert logger.level == logging.WARNING
    finally:
        logger.setLevel(before)


def test_tool_annotations():
    tools = {t.name: t for t in asyncio.run(mcp.build().list_tools())}
    assert tools["list_todos"].annotations.read_only_hint
    assert tools["delete_todo"].annotations.destructive_hint
    assert not tools["complete_todo"].annotations.destructive_hint
    assert tools["get_config"].annotations.read_only_hint
    assert tools["unset_config"].annotations.destructive_hint


def test_served_at_mcp(root):
    rpc = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    with TestClient(app.create_app(static=None), base_url="http://127.0.0.1:8765") as c:
        resp = c.post("/mcp", json=rpc, headers=HEADERS)
        assert resp.status_code == 200, resp.text
        assert "add_todo" in {t["name"] for t in resp.json()["result"]["tools"]}
        # against DNS rebinding, a local server answers only local Host headers
        assert c.post("/mcp", json=rpc, headers={**HEADERS, "Host": "evil.example"}).status_code == 421
