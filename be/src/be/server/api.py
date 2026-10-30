"""`be server`'s JSON API, under /api. A failed action answers 422 with its message; bad input, 400."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import date

import click
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from be import claude_usage, config, cursor_usage, gcal, github, jira, todo
from be.commands import pr, ws
from be.server import views
from be.server.views import MINE_BUTTONS, SettingError

log = logging.getLogger(__name__)

LOG_LEVELS = config.SETTINGS["server.log_level"].choices
# run_mine_action says what it did, or why it didn't; these start what it did
DONE = ("marked ", "enabled ", "merged ")


class ActionFailed(Exception):
    """An action that ran but failed; the app shows the message."""


@dataclass
class State:
    """What `be server` was started with, and the tables it has fetched.

    fixed names the settings in views.FLAGS given as flags, which keep their value; the rest are
    reread when used. lock serializes requests, as the actions share loaded and the working directory."""

    parent: str | None = None
    fixed: tuple[str, ...] = ()
    agent: str = "claude"
    claude_model: str | None = None
    cursor_model: str | None = None
    # each PR table is fetched only when refreshed, then kept
    loaded: dict[str, list[dict] | str] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)

    def setting(self, key: str, given):
        """given if its flag was, else the setting as it's set now."""
        return given if key in self.fixed else config.resolve(key)[0]

    def review_agent(self, chosen: str | None) -> str:
        """The reviews page's toggle when it's claude or cursor, else --agent or pr.agent."""
        chosen = (chosen or "").strip().lower()
        return chosen if chosen in pr.AGENTS else views.review_agent(self.setting("pr.agent", self.agent))

    def mine_prs(self) -> list[dict]:
        if not isinstance(self.loaded.get("mine"), list):
            self.loaded["mine"] = views.fetch_table("mine")
        return self.loaded["mine"] if isinstance(self.loaded["mine"], list) else []

    def run_action(self, action: str, repo: str, number: int, bulk: bool = False) -> tuple[bool, str]:
        """Run action on your PR; in bulk, a PR the action isn't offered on is skipped."""
        mine = self.mine_prs()
        found = [p for p in mine if p["repo"] == repo and p["number"] == number]
        if not found:
            return False, f"{repo}#{number} is not one of your open PRs"
        if bulk and action not in views.mine_actions(found[0]):
            return False, f"skipped {repo}#{number}: no {MINE_BUTTONS[action]} on it"
        try:
            message = pr.run_mine_action(action, found[0])
        except click.ClickException as e:
            log.warning("%s on %s#%s failed: %s", action, repo, number, e.format_message())
            return False, f"{repo}#{number}: {e.format_message()}"
        if not message.startswith(DONE):
            return False, message
        log.info("%s#%s: %s", repo, number, message)
        # run_mine_action updates the row in place rather than us refetching the table, so a PR
        # marked ready offers auto-merge next, and one set to auto-merge offers nothing; a merged
        # one is dropped
        if message.startswith("merged"):
            mine.remove(found[0])
        return True, message


def state(request: Request) -> State:
    return request.app.state.be


router = APIRouter(prefix="/api")


def valid_name(name: str) -> str:
    if not name or "/" in name or name in (".", ".."):
        raise HTTPException(400, "not a workspace name")
    return name


def find_workspace(name: str):
    parent, _ = config.resolve("ws.dir")
    root = {entry.name: entry for entry in ws.workspace_entries(parent)}.get(name)
    if root is None:
        raise click.ClickException(f"{name} is not a workspace")
    return root


@router.get("/meta")
def meta(request: Request) -> dict:
    """The reviews page's starting agent, the agents it offers, and where the config is saved."""
    s = state(request)
    return {
        "agent": s.review_agent(None),
        "agents": list(pr.AGENTS),
        "config_path": str(config.config_path()),
    }


@router.get("/tables/{table}")
def table(table: str, request: Request, refresh: bool = False) -> dict:
    """The table's rows, or its error. Workspaces are always read afresh; the Jira tree is fetched
    the first time and on refresh; a PR table only on refresh, so rows is null until then."""
    if table not in views.TABLES:
        raise HTTPException(404, f"no table {table}")
    s = state(request)
    with s.lock:
        if table == "workspaces" or refresh or (table == "jira" and table not in s.loaded):
            s.loaded[table] = views.fetch_table(table)
        found = s.loaded.get(table)
        out: dict = {"table": table, "rows": None, "error": None}
        if isinstance(found, str):
            out["error"] = found
        elif found is not None:
            if table == "jira":
                # the tree finds issues' workspaces, so read those too
                spaces = views.fetch_table("workspaces")
                s.loaded["workspaces"] = spaces
                tree = views.issue_tree(found, spaces if isinstance(spaces, list) else [])
                out["rows"] = tree.pop("issues")
                out.update(tree)
            elif table == "workspaces":
                out["rows"] = found
            else:
                out["rows"] = [views.pr_row(p, table == "mine") for p in found]
        if table in pr.EMPTY:
            out["empty"] = pr.EMPTY[table]
        return out


class PrRef(BaseModel):
    repo: str
    number: int
    agent: str | None = None


@router.post("/prs/review")
def review(body: PrRef, request: Request) -> dict:
    s = state(request)
    with s.lock:
        try:
            pr.open_review(
                body.repo,
                body.number,
                s.setting("pr.dir", s.parent),
                s.review_agent(body.agent),
                s.setting("claude.pr.model", s.claude_model),
                s.setting("cursor.pr.model", s.cursor_model),
            )
        except click.ClickException as e:
            log.warning("reviewing %s#%s failed: %s", body.repo, body.number, e.format_message())
            raise ActionFailed(f"{body.repo}#{body.number}: {e.format_message()}") from e
    log.info("opened %s#%s for review", body.repo, body.number)
    return {"message": f"opened {body.repo}#{body.number}"}


class Bulk(BaseModel):
    action: str
    prs: list[str]


@router.post("/prs/bulk")
def bulk(body: Bulk, request: Request) -> dict:
    """Run the action on each of the "repo#number" PRs, carrying on past failures."""
    picked = [value.rpartition("#") for value in body.prs]
    if body.action not in MINE_BUTTONS or any(not n.isdigit() or not r for r, _, n in picked):
        raise HTTPException(400, "bad bulk action")
    if not picked:
        raise ActionFailed("no PRs selected")
    s = state(request)
    with s.lock:
        results = []
        for r, _, n in picked:
            ok, message = s.run_action(body.action, r, int(n), bulk=True)
            results.append({"pr": f"{r}#{n}", "ok": ok, "message": message})
    return {"message": "; ".join(x["message"] for x in results), "results": results}


class Starred(BaseModel):
    prs: list[str]


@router.post("/prs/starred")
def starred(body: Starred) -> dict:
    """The starred "repo#number" PRs as they are now: rows for those not merged, and the names of those
    merged, which the app drops. Stars are the browser's; the server only looks them up."""
    picked = [value.rpartition("#") for value in body.prs]
    if any(not n.isdigit() or "/" not in r for r, _, n in picked):
        raise HTTPException(400, "bad PR name")
    try:
        rows, merged = github.pr_states([(r, int(n)) for r, _, n in picked])
    except click.ClickException as e:
        log.warning("looking up starred PRs failed: %s", e.format_message())
        return {"rows": None, "merged": [], "error": e.format_message()}
    return {"rows": [views.pr_row(p, False) for p in rows], "merged": merged, "error": None}


@router.post("/prs/{action}")
def mine_action(action: str, body: PrRef, request: Request) -> dict:
    if action not in MINE_BUTTONS:
        raise HTTPException(404, f"no action {action}")
    s = state(request)
    with s.lock:
        ok, message = s.run_action(action, body.repo, body.number)
    if not ok:
        raise ActionFailed(message)
    return {"message": message}


@router.post("/workspaces/{name}/open")
def open_workspace(name: str, request: Request) -> dict:
    """Open a workspace directory in ws.dir, as `ws open` does."""
    valid_name(name)
    with state(request).lock:
        try:
            root = find_workspace(name)
            window, _ = config.resolve("cmux.window")
            ws.open_root(root, window=window)
        except click.ClickException as e:
            log.warning("opening workspace %s failed: %s", name, e.format_message())
            raise ActionFailed(f"{name}: {e.format_message()}") from e
    log.info("opened workspace %s", name)
    return {"message": f"opened {name}"}


class NewWorkspace(BaseModel):
    name: str
    repos: str = ""
    extra_dirs: str = ""
    description: str = ""
    issue_name: str = ""


@router.post("/workspaces")
def create_workspace(body: NewWorkspace, request: Request) -> dict:
    """Create a workspace in ws.dir and open it, as `ws create` does; issue_name is the summary of the
    issue it's for."""
    name = valid_name(body.name.strip())
    with state(request).lock:
        try:
            parent, _ = config.resolve("ws.dir")
            if any(entry.name == name for entry in ws.workspace_entries(parent)):
                raise click.ClickException(f"{name} already exists")
            model, _ = config.resolve("claude.model")
            org, _ = config.resolve("work_org")
            window, _ = config.resolve("cmux.window")
            # create_workspace changes into the new workspace, which the server shouldn't stay in
            cwd = os.getcwd()
            try:
                ws.create_workspace(
                    name,
                    body.repos.strip(),
                    body.extra_dirs.strip(),
                    body.description.strip(),
                    parent,
                    model,
                    org,
                    window,
                    body.issue_name.strip() or None,
                )
            finally:
                os.chdir(cwd)
        except click.ClickException as e:
            log.warning("creating workspace %s failed: %s", name, e.format_message())
            raise ActionFailed(f"{name}: {e.format_message()}") from e
        except click.exceptions.Exit as e:
            log.warning("creating workspace %s failed: cmux could not save its layout", name)
            raise ActionFailed(f"{name}: created, but cmux could not save its layout") from e
    log.info("created workspace %s", name)
    return {"message": f"created {name}"}


class Link(BaseModel):
    key: str


@router.post("/workspaces/{name}/link")
def link_workspace(name: str, body: Link, request: Request) -> dict:
    """Link the issue key to an existing workspace in ws.dir, then open it."""
    valid_name(name)
    key = body.key.strip().upper()
    if not jira.ISSUE_KEY.fullmatch(key):
        raise HTTPException(400, f"{body.key!r} is not an issue key")
    with state(request).lock:
        try:
            root = find_workspace(name)
            ws.link_issue(root, key)
            log.info("linked %s to workspace %s", key, name)
            window, _ = config.resolve("cmux.window")
            ws.open_root(root, window=window)
        except click.ClickException as e:
            log.warning("linking %s to workspace %s failed: %s", key, name, e.format_message())
            raise ActionFailed(f"{name}: {e.format_message()}") from e
        except OSError as e:
            log.warning("linking %s to workspace %s failed: %s", key, name, e)
            raise ActionFailed(f"{name}: could not save the link: {e.strerror or e}") from e
    return {"message": f"linked {key} to {name}; opened {name}"}


@router.post("/workspaces/{name}/start")
def start_work(name: str, body: Link, request: Request) -> dict:
    """Open the workspace in ws.dir and start claude in plan mode on the issue, in a new pane."""
    valid_name(name)
    key = body.key.strip().upper()
    if not jira.ISSUE_KEY.fullmatch(key):
        raise HTTPException(400, f"{body.key!r} is not an issue key")
    with state(request).lock:
        try:
            root = find_workspace(name)
            window, _ = config.resolve("cmux.window")
            ws.start_work(root, key, window=window)
        except click.ClickException as e:
            log.warning("starting %s in workspace %s failed: %s", key, name, e.format_message())
            raise ActionFailed(f"{name}: {e.format_message()}") from e
    log.info("started %s in workspace %s", key, name)
    return {"message": f"started {key} in {name}"}


def todo_row(t: dict) -> dict:
    """t with its Jira issue's link, or "" when it has none or jira.url isn't set."""
    url = ""
    if t["jira"]:
        try:
            url = jira.issue_url(t["jira"])
        except jira.JiraError:
            pass
    return {**t, "url": url}


@router.get("/todos")
def get_todos(done: bool = False) -> dict:
    """The open todos (and done ones, when done), as `todo ls` orders them, or why they couldn't be read."""
    out: dict = {"rows": None, "error": None, "dir": ""}
    try:
        root = todo.todo_dir()
        out["dir"] = str(root)
        out["rows"] = [todo_row(t) for t in todo.list_todos(root, include_done=done)]
    except click.ClickException as e:
        out["error"] = e.format_message()
    except OSError as e:
        out["error"] = f"could not read the todos: {e.strerror or e}"
    return out


class TodoFields(BaseModel):
    title: str | None = None
    due: str | None = None
    priority: str | None = None
    jira: str | None = None
    tags: list[str] | None = None
    notes: str | None = None


def todo_action(request: Request, what: str, run) -> dict:
    """Run a change to the todos, saying what it did, or failing with why it couldn't."""
    with state(request).lock:
        try:
            changed = run(todo.todo_dir())
        except click.ClickException as e:
            log.warning("%s failed: %s", what, e.format_message())
            raise ActionFailed(e.format_message()) from e
        except OSError as e:
            log.warning("%s failed: %s", what, e)
            raise ActionFailed(f"could not save the todo: {e.strerror or e}") from e
    log.info("%s %s", what, changed["id"])
    return {"message": f"{what} {changed['title']}", "todo": todo_row(changed)}


@router.post("/todos")
def add_todo(body: TodoFields, request: Request) -> dict:
    return todo_action(
        request,
        "added",
        lambda root: todo.add(root, body.title or "", body.due, body.priority, body.tags or (), body.jira, body.notes or ""),
    )


@router.put("/todos/{ref}")
def update_todo(ref: str, body: TodoFields, request: Request) -> dict:
    """Change the fields given; an empty one clears it."""
    return todo_action(request, "saved", lambda root: todo.update(root, ref, **body.model_dump(exclude_unset=True)))


@router.post("/todos/{ref}/done")
def done_todo(ref: str, request: Request) -> dict:
    return todo_action(request, "done", lambda root: todo.set_done(root, ref))


@router.post("/todos/{ref}/reopen")
def reopen_todo(ref: str, request: Request) -> dict:
    return todo_action(request, "reopened", lambda root: todo.set_done(root, ref, False))


@router.delete("/todos/{ref}")
def delete_todo(ref: str, request: Request) -> dict:
    with state(request).lock:
        try:
            removed = todo.remove(todo.todo_dir(), ref)
        except click.ClickException as e:
            raise ActionFailed(e.format_message()) from e
    log.info("deleted todo %s", removed)
    return {"message": f"deleted {removed}"}


@router.get("/config")
def get_config(request: Request) -> dict:
    """Every setting to edit, or why the file couldn't be read."""
    out = {"path": str(config.config_path()), "settings": [], "error": None}
    try:
        out["settings"] = views.config_settings(state(request).fixed)
    except click.ClickException as e:
        # e.g. the file isn't valid TOML: say why instead of the settings
        out["error"] = e.format_message()
    return out


@router.get("/claude-usage")
def get_claude_usage() -> dict:
    """Your Claude plan's limits from `claude /usage`, or why it couldn't be read."""
    out = {"limits": [], "plan_note": "", "details": "", "raw": "", "error": None, "fetched_at": time.time()}
    try:
        out.update(claude_usage.parse(claude_usage.fetch()))
    except click.ClickException as e:
        log.warning("reading claude usage failed: %s", e.format_message())
        out["error"] = e.format_message()
    return out


@router.get("/cursor-usage")
def get_cursor_usage() -> dict:
    """Your Cursor plan's usage this period from Cursor's API, or why it couldn't be read."""
    out = {"plan": "", "limits": [], "on_demand": None, "message": "", "error": None, "fetched_at": time.time()}
    try:
        out.update(cursor_usage.summarize(*cursor_usage.fetch()))
    except click.ClickException as e:
        log.warning("reading cursor usage failed: %s", e.format_message())
        out["error"] = e.format_message()
    return out


@router.get("/calendar")
def get_calendar(day: str, tz: str = "UTC") -> dict:
    """Your events on day (YYYY-MM-DD) in the browser's time zone, or why they couldn't be read."""
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(400, f"day must be YYYY-MM-DD, not {day!r}") from None
    out = {"day": day, "events": [], "error": None, "fetched_at": time.time()}
    try:
        out["events"] = gcal.events(parsed, tz)
    except gcal.CalendarError as e:
        log.warning("reading the calendar failed: %s", e)
        out["error"] = str(e)
    return out


class Value(BaseModel):
    value: str = ""
    # names the new entry when key is a map setting
    name: str = ""


def saved(request: Request, key: str, value: str, name: str, unset: bool) -> dict:
    s = state(request)
    with s.lock:
        try:
            message = views.save_setting(key, value, name, unset)
        except SettingError as e:
            raise ActionFailed(str(e)) from e
        if "server.log_level" not in s.fixed:
            # a saved log level applies now, unless its env var still wins
            level, _ = config.resolve("server.log_level")
            if str(level).lower() in LOG_LEVELS:
                logging.getLogger("be").setLevel(str(level).upper())
    return {"message": message}


@router.put("/config/{key}")
def set_config(key: str, body: Value, request: Request) -> dict:
    """Save the value; an empty one removes it."""
    return saved(request, key, body.value, body.name, unset=False)


@router.delete("/config/{key}")
def unset_config(key: str, request: Request) -> dict:
    return saved(request, key, "", "", unset=True)
