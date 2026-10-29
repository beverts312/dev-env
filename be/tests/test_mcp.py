import asyncio

from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError
import pytest

from be import todo
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


def test_tool_annotations():
    tools = {t.name: t for t in asyncio.run(mcp.build().list_tools())}
    assert tools["list_todos"].annotations.read_only_hint
    assert tools["delete_todo"].annotations.destructive_hint
    assert not tools["complete_todo"].annotations.destructive_hint


def test_served_at_mcp(root):
    rpc = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    with TestClient(app.create_app(static=None), base_url="http://127.0.0.1:8765") as c:
        resp = c.post("/mcp", json=rpc, headers=HEADERS)
        assert resp.status_code == 200, resp.text
        assert "add_todo" in {t["name"] for t in resp.json()["result"]["tools"]}
        # against DNS rebinding, a local server answers only local Host headers
        assert c.post("/mcp", json=rpc, headers={**HEADERS, "Host": "evil.example"}).status_code == 421
