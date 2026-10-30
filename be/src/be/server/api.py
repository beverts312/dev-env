"""`be server`'s JSON API, under /api. A failed action answers 422 with its message; bad input, 400."""

from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import click
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from be import claude_sessions, claude_usage, config, cursor_usage, gcal, github, gmail, jira, todo
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


@router.post("/workspaces/{name}/vscode")
def open_vscode(name: str) -> dict:
    """Open a workspace directory in ws.dir in VS Code."""
    valid_name(name)
    try:
        ws.open_vscode(find_workspace(name))
    except click.ClickException as e:
        log.warning("opening workspace %s in VS Code failed: %s", name, e.format_message())
        raise ActionFailed(f"{name}: {e.format_message()}") from e
    log.info("opened workspace %s in VS Code", name)
    return {"message": f"opened {name} in VS Code"}


def notes_dir() -> Path:
    value, _ = config.resolve("notes.dir")
    return Path(value).expanduser()


def open_in_vscode(what: str, path: Path, ok: bool, setting: str) -> dict:
    try:
        if not ok:
            raise click.ClickException(f"{path} not found; set {setting}")
        ws.open_vscode(path)
    except click.ClickException as e:
        log.warning("opening %s in VS Code failed: %s", what, e.format_message())
        raise ActionFailed(f"{what}: {e.format_message()}") from e
    log.info("opened %s in VS Code", what)
    return {"message": f"opened {path} in VS Code"}


@router.post("/notes/vscode")
def open_notes() -> dict:
    """Open notes.dir in VS Code."""
    notes = notes_dir()
    return open_in_vscode("notes", notes, notes.is_dir(), "notes.dir")


@router.post("/configs/vscode")
def open_configs() -> dict:
    """Open the configs VS Code workspace: configs.workspace, else notes.dir's workspaces/configs.code-workspace."""
    value, _ = config.resolve("configs.workspace")
    path = Path(value).expanduser() if value else notes_dir() / "workspaces" / "configs.code-workspace"
    return open_in_vscode("configs", path, path.is_file(), "configs.workspace")


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


@router.delete("/workspaces/{name}")
def delete_workspace(name: str, request: Request) -> dict:
    """Delete a workspace in ws.dir, as `ws delete` does: its directory and its saved cmux layout;
    then the claude sessions run in it."""
    valid_name(name)
    with state(request).lock:
        try:
            find_workspace(name)
            parent, _ = config.resolve("ws.dir")
            root = ws.delete_target(name, parent)
            ws.remove_workspace(root)
            sessions = claude_sessions.delete_all(root)
        except click.ClickException as e:
            log.warning("deleting workspace %s failed: %s", name, e.format_message())
            raise ActionFailed(f"{name}: {e.format_message()}") from e
    log.info("deleted workspace %s and %d claude sessions", name, sessions)
    return {"message": f"deleted {name} and {sessions} claude session{'' if sessions == 1 else 's'}"}


@router.get("/workspaces/{name}/sessions")
def workspace_sessions(name: str) -> dict:
    """The claude sessions run in the workspace or folders under it, the most recent first."""
    valid_name(name)
    try:
        root = find_workspace(name)
        return {"sessions": claude_sessions.list_sessions(root)}
    except click.ClickException as e:
        raise ActionFailed(f"{name}: {e.format_message()}") from e


@router.post("/workspaces/{name}/sessions/{session_id}/resume")
def resume_session(name: str, session_id: str, request: Request) -> dict:
    """Open the workspace and resume the claude session in a new pane, from the folder it ran in."""
    valid_name(name)
    with state(request).lock:
        try:
            root = find_workspace(name)
            session = claude_sessions.get_session(root, session_id)
            window, _ = config.resolve("cmux.window")
            ws.resume_session(root, Path(session["cwd"]), session_id, window=window)
        except click.ClickException as e:
            log.warning("resuming %s in workspace %s failed: %s", session_id, name, e.format_message())
            raise ActionFailed(f"{name}: {e.format_message()}") from e
    log.info("resumed %s in workspace %s", session_id, name)
    return {"message": f"resumed {session['title']}"}


@router.delete("/workspaces/{name}/sessions/{session_id}")
def delete_session(name: str, session_id: str, request: Request) -> dict:
    valid_name(name)
    with state(request).lock:
        try:
            session = claude_sessions.delete_session(find_workspace(name), session_id)
        except click.ClickException as e:
            raise ActionFailed(f"{name}: {e.format_message()}") from e
    log.info("deleted session %s in workspace %s", session_id, name)
    return {"message": f"deleted {session['title']}"}


class CloudIssue(BaseModel):
    text: str


@router.post("/jira/cloud-issue")
def cloud_issue(body: CloudIssue, request: Request) -> dict:
    """Open a cmux workspace running claude's /cloud-issue on the text."""
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "describe the issue")
    with state(request).lock:
        try:
            window, _ = config.resolve("cmux.window")
            ws.cloud_issue(text, window=window)
        except click.ClickException as e:
            log.warning("opening /cloud-issue failed: %s", e.format_message())
            raise ActionFailed(f"cloud issue: {e.format_message()}") from e
        except click.exceptions.Exit as e:
            log.warning("opening /cloud-issue failed: cmux could not open a workspace")
            raise ActionFailed("cloud issue: cmux could not open a workspace") from e
    log.info("opened /cloud-issue")
    return {"message": "opened claude to file a cloud issue"}


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


@router.get("/mail")
def get_mail(q: str = "in:inbox", page: str | None = None) -> dict:
    """The threads the Gmail query q finds, or why they couldn't be read."""
    out = {"threads": [], "next_page": None, "error": None, "fetched_at": time.time()}
    try:
        out["threads"], out["next_page"] = gmail.list_threads(q, page)
    except gmail.MailError as e:
        log.warning("reading mail failed: %s", e)
        out["error"] = str(e)
    return out


@router.get("/mail/actions")
def mail_actions() -> dict:
    return {"actions": gmail.ACTIONS}


def mail_call(what: str, run):
    try:
        return run()
    except gmail.MailError as e:
        log.warning("%s failed: %s", what, e)
        raise ActionFailed(f"{what}: {e}") from e


@router.get("/mail/{thread_id}")
def get_thread(thread_id: str) -> dict:
    return mail_call("reading the thread", lambda: gmail.get_thread(thread_id))


class Labels(BaseModel):
    add: list[str] = []
    remove: list[str] = []


@router.post("/mail/{thread_id}/modify")
def modify_thread(thread_id: str, body: Labels) -> dict:
    if not body.add and not body.remove:
        raise HTTPException(400, "give labels to add or remove")
    mail_call("changing the thread", lambda: gmail.modify(thread_id, body.add, body.remove))
    return {"message": "updated the thread"}


class Threads(BaseModel):
    ids: list[str]


@router.post("/mail/trash")
def trash_threads(body: Threads) -> dict:
    """Move each thread to Trash; says how many failed, if any did."""
    if not body.ids:
        raise HTTPException(400, "pick threads to delete")

    def one(id: str) -> str | None:
        try:
            gmail.trash(id)
        except gmail.MailError as e:
            log.warning("deleting mail thread %s failed: %s", id, e)
            return str(e)
        return None

    with ThreadPoolExecutor(8) as pool:
        errors = [e for e in pool.map(one, body.ids) if e]
    done = len(body.ids) - len(errors)
    if errors:
        raise ActionFailed(f"moved {done} of {len(body.ids)} threads to Trash; {errors[0]}")
    return {"message": f"moved {done} thread{'' if done == 1 else 's'} to Trash"}


@router.post("/mail/{thread_id}/trash")
def trash_thread(thread_id: str) -> dict:
    mail_call("deleting the thread", lambda: gmail.trash(thread_id))
    return {"message": "moved the thread to Trash"}


class MailAction(BaseModel):
    action: str | None = None
    prompt: str | None = None


@router.post("/mail/{thread_id}/action")
def mail_action(thread_id: str, body: MailAction, request: Request) -> dict:
    """Open a cmux workspace running claude on the thread, with a built-in action's prompt or your own."""
    if body.action:
        found = next((a for a in gmail.ACTIONS if a["key"] == body.action), None)
        if not found:
            raise HTTPException(400, f"no mail action {body.action!r}")
        prompt, label = found["prompt"], found["label"].lower()
    else:
        prompt, label = (body.prompt or "").strip(), "claude"
        if not prompt:
            raise HTTPException(400, "say what to ask claude")
    thread = mail_call("reading the thread", lambda: gmail.get_thread(thread_id))
    with state(request).lock:
        try:
            window, _ = config.resolve("cmux.window")
            ws.mail_action(gmail.save_thread(thread), prompt, f"mail: {thread['subject'][:40]}", window=window)
        except click.ClickException as e:
            log.warning("opening a mail action failed: %s", e.format_message())
            raise ActionFailed(f"mail: {e.format_message()}") from e
        except click.exceptions.Exit as e:
            log.warning("opening a mail action failed: cmux could not open a workspace")
            raise ActionFailed("mail: cmux could not open a workspace") from e
    log.info("opened %s on mail thread %s", label, thread_id)
    return {"message": f"opened claude: {label}"}


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
