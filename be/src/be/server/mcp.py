"""`be server`'s MCP server, at /mcp: tools for managing the todos in todo.dir, as `be todo` does."""

from __future__ import annotations

import logging
from typing import Any, Literal

import click
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from starlette.routing import BaseRoute

from be import todo

log = logging.getLogger(__name__)

PATH = "/mcp"

INSTRUCTIONS = """Manage the user's todos. Each is a markdown file in their notes, with a title, optional due
date, priority (high, med or low), Jira issue key and tags, and free markdown notes. Tools that take a ref
accept a todo's id or any unique start of one; list_todos gives the ids."""

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
DELETE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

Priority = Literal["high", "med", "low", ""]


def shown(t: dict) -> dict:
    """t as a tool returns it: without overdue on done todos, where it's always false."""
    return t if t["status"] == "open" else {k: v for k, v in t.items() if k != "overdue"}


def run(what: str, change):
    """Run a change to the todos in todo.dir, turning why it couldn't into an error the model reads."""
    try:
        return change(todo.todo_dir())
    except click.ClickException as e:
        log.info("mcp %s failed: %s", what, e.format_message())
        raise ToolError(e.format_message()) from e
    except OSError as e:
        raise ToolError(f"could not {what}: {e.strerror or e}") from e


def build() -> MCPServer:
    """A new server, so each app runs its own session manager."""
    server = MCPServer("be", instructions=INSTRUCTIONS)

    @server.tool(annotations=READ)
    def list_todos(
        include_done: bool = False,
        only_done: bool = False,
        tag: str | None = None,
        jira: str | None = None,
    ) -> list[dict[str, Any]]:
        """List todos: open ones unless include_done or only_done, overdue first, then by due date, priority
        and created date. tag and jira (an issue key) narrow the list."""
        return run("list todos", lambda root: [shown(t) for t in todo.list_todos(root, include_done, only_done, tag, jira)])

    @server.tool(annotations=READ)
    def get_todo(ref: str) -> dict[str, Any]:
        """One todo, with its notes."""
        return run("read the todo", lambda root: shown(todo.load(todo.find(root, ref))))

    @server.tool(annotations=WRITE)
    def add_todo(
        title: str,
        due: str | None = None,
        priority: Priority | None = None,
        tags: list[str] | None = None,
        jira: str | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        """Add a todo. due is YYYY-MM-DD, today, tomorrow, +Nd or +Nw; jira is an issue key like ADC-123;
        notes are markdown."""
        return run("add the todo", lambda root: todo.add(root, title, due, priority, tags or (), jira, notes))

    @server.tool(annotations=WRITE)
    def update_todo(
        ref: str,
        title: str | None = None,
        due: str | None = None,
        priority: Priority | None = None,
        tags: list[str] | None = None,
        jira: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Change a todo's fields. Leave out (or pass null for) what stays as it is; an empty string or list
        clears it. notes replaces the whole body, so read it with get_todo first to add to it."""
        fields = {"title": title, "due": due, "priority": priority, "tags": tags, "jira": jira, "notes": notes}
        return run("save the todo", lambda root: todo.update(root, ref, **fields))

    @server.tool(annotations=WRITE)
    def complete_todo(ref: str) -> dict[str, Any]:
        """Mark a todo done."""
        return run("complete the todo", lambda root: shown(todo.set_done(root, ref)))

    @server.tool(annotations=WRITE)
    def reopen_todo(ref: str) -> dict[str, Any]:
        """Mark a done todo open again."""
        return run("reopen the todo", lambda root: todo.set_done(root, ref, False))

    @server.tool(annotations=DELETE)
    def delete_todo(ref: str) -> str:
        """Delete a todo's file. complete_todo is usually what's wanted; this can't be undone."""
        return "deleted " + run("delete the todo", lambda root: todo.remove(root, ref))

    return server


def routes(server: MCPServer, host: str) -> list[BaseRoute]:
    """The route serving server at PATH over streamable HTTP, stateless and answering in JSON. Bound to a
    local address, the SDK accepts only local Host and Origin headers there, against DNS rebinding."""
    app = server.streamable_http_app(streamable_http_path=PATH, stateless_http=True, json_response=True, host=host)
    return list(app.routes)
