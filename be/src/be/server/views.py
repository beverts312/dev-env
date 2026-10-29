"""The data `be server`'s web app shows, shaped for it: the tables' rows and the config page's settings."""

from __future__ import annotations

import logging

import click

from be import config, jira
from be.commands import pr, ws
from be.commands.jira import TOP_LEVEL
from be.github import same_login

log = logging.getLogger(__name__)

# the flag that fixes each setting the server reads, until it restarts, when given
FLAGS = {
    "pr.dir": "--parent",
    "server.log_level": "--log-level",
    "pr.agent": "--agent",
    "claude.pr.model": "--claude-model",
    "cursor.pr.model": "--cursor-model",
}

# the tables the app shows; a PR table's id is its pr.KINDS kind
TABLES = (*pr.KINDS, "jira", "workspaces")

# button label for each action on your own PRs
MINE_BUTTONS = {"ready": "ready", "automerge": "auto-merge", pr.MERGE_ACTION: "merge"}


class SettingError(Exception):
    """A setting couldn't be saved; the message says why."""


def mine_actions(p: dict) -> list[str]:
    """The actions offered on your PR p: only drafts can be marked ready, GitHub won't
    auto-merge a draft, and nothing is offered once auto-merge is on; approved PRs
    can be merged now."""
    if p["draft"]:
        return ["ready"]
    if p["auto_merge"]:
        return []
    return ["automerge", pr.MERGE_ACTION] if p["approved"] else ["automerge"]


def review_agent(agent: str | None) -> str:
    """claude or cursor; anything else falls back to claude, the pr.agent default."""
    name = str(agent or "").lower()
    return name if name in pr.AGENTS else "claude"


def workspace_rows() -> list[dict]:
    """Each workspace in ws.dir, with dir set to the directory `ws open` takes."""
    parent, _ = config.resolve("ws.dir")
    return [
        {**ws.workspace_details(entry), "dir": entry.name}
        for entry in ws.workspace_entries(parent)
    ]


def fetch_table(table: str) -> list[dict] | str:
    """The table's rows, or the error message from looking them up."""
    log.debug("fetching %s", table)
    try:
        if table == "jira":
            rows = jira.issue_tree()
        elif table == "workspaces":
            rows = workspace_rows()
        else:
            rows = pr.fetch_prs(table)
    except click.ClickException as e:
        message = e.format_message()
    except jira.JiraError as e:
        message = str(e)
    else:
        log.info("fetched %d rows for %s", len(rows), table)
        return rows
    log.warning("fetching %s failed: %s", table, message)
    return message


def pr_row(p: dict, mine: bool) -> dict:
    """p as the app shows it: with its GitHub link and, on your PRs, the actions it offers."""
    row = {key: value for key, value in p.items() if key != "merge_flag"}
    row["url"] = pr.pr_url(p["repo"], p["number"])
    row["renovate"] = same_login(p["author"], pr.RENOVATE_USER)
    if mine:
        row["actions"] = mine_actions(p)
    return row


def issue_workspace(issue: dict, workspaces: dict[str, str]) -> str:
    """The workspace named after or linked to the issue's key, else its parent's key, ignoring case, as
    `jira ls -i` finds it; workspaces is as ws.issue_workspaces maps it. "" when there's none."""
    for key in (issue["key"], issue["parent"]):
        if key and key.upper() in workspaces:
            return workspaces[key.upper()]
    return ""


def issue_project(issue: dict) -> str:
    """The project key an issue key starts with: ACME for ACME-12."""
    return issue["key"].rpartition("-")[0].upper()


def tree_issues(issues: list[dict]) -> list[dict]:
    """Every issue in the tree, parents before their children."""
    return [found for issue in issues for found in (issue, *tree_issues(issue["children"]))]


# the order status categories sort in: To Do, then In Progress, then Done
CATEGORY_ORDER = ("new", "indeterminate", "done")


def tree_statuses(issues: list[dict]) -> list[str]:
    """Every status in the tree, To Do ones first, then In Progress, then any other, each by name."""
    found = {(issue["category"], issue["status"]) for issue in tree_issues(issues) if issue["status"]}
    rank = {category: n for n, category in enumerate(CATEGORY_ORDER)}
    return [status for _, status in sorted(found, key=lambda c: (rank.get(c[0], len(rank)), c[1].lower()))]


def project_notes() -> dict[str, str]:
    """Each project's jira.projects description, by upper-cased key."""
    try:
        described, _ = config.resolve("jira.projects")
    except click.ClickException:
        return {}
    return {key.upper(): str(value) for key, value in described.items()} if isinstance(described, dict) else {}


def issue_node(issue: dict, workspaces: dict[str, str]) -> dict:
    """The issue with its Jira link, project, workspace (or ""), whether a new workspace could be for its
    Feature or Epic parent instead (as `jira ls -i` asks), and its children likewise."""
    return {
        **issue,
        "url": jira.issue_url(issue["key"]),
        "project": issue_project(issue),
        "workspace": issue_workspace(issue, workspaces),
        "parent_offer": issue["type"] not in TOP_LEVEL and issue["parent_type"] in TOP_LEVEL,
        "children": [issue_node(child, workspaces) for child in issue["children"]],
    }


def issue_tree(issues: list[dict], workspaces: list[dict]) -> dict:
    """The tree for the app, with the projects and statuses its filters offer; workspaces is as
    workspace_rows gives them."""
    names = ws.issue_workspaces([(row["dir"], row.get("issues")) for row in workspaces])
    notes = project_notes()
    projects = sorted({issue_project(issue) for issue in tree_issues(issues)})
    return {
        "issues": [issue_node(issue, names) for issue in issues],
        "projects": [{"key": key, "note": notes.get(key, "")} for key in projects],
        "statuses": tree_statuses(issues),
    }


def save_setting(key: str, value: str, name: str = "", unset: bool = False) -> str:
    """Set or unset key (a map setting's key with a name adds that entry), and say what happened;
    raises SettingError when it can't."""
    value, name = value.strip(), name.strip()
    try:
        s = config.setting(key)
        if s.kind == "map" and key == s.key:
            if not name or "." in name:
                raise SettingError(f"{key}: give the new entry a name, without dots")
            key = f"{key}.{name}"
        if unset or not value:
            config.unset_value(key)
            log.info("removed %s from the config", key)
            return f"removed {key}"
        if s.choices and value not in s.choices:
            raise SettingError(f"{key} must be one of {', '.join(s.choices)}, not {value!r}")
        overridden = config.set_value(key, value)
    except click.ClickException as e:
        raise SettingError(f"{key}: {e.message}") from e
    log.info("set %s in the config", key)
    return f"saved {key}" + (f"; {s.env} is set and overrides it" if overridden else "")


def override_note(s: config.Setting, effective) -> str:
    """The note on a setting whose env var wins over the file, with the value it gives (masked if secret)."""
    if s.secret:
        shown = "********"
    elif isinstance(effective, dict):
        shown = ", ".join(effective) or "no entries"
    else:
        shown = effective
    return f"{s.env} overrides the file: {shown}"


def flag_note(key: str) -> str:
    if key == "pr.agent":
        return f"{FLAGS[key]} was given, so the reviews page starts on it; its toggle picks the agent for a review"
    return f"{FLAGS[key]} was given, so `be server` uses it until restarted"


def config_settings(fixed: tuple[str, ...]) -> list[dict]:
    """Every setting with its file value (a map's as entries), source, and any notes on what overrides it."""
    data = config.load_file()
    out = []
    for s in config.SETTINGS.values():
        effective, source = config.resolve(s.key)
        file = config.file_value(s.key, data)
        notes = [override_note(s, effective)] if source.startswith("env:") else []
        if s.key in fixed:
            notes.append(flag_note(s.key))
        row = {
            "key": s.key,
            "env": s.env,
            "help": s.help,
            "default": s.default,
            "kind": s.kind,
            "secret": s.secret,
            "choices": list(s.choices),
            "source": source,
            "notes": notes,
        }
        if s.kind == "map":
            row["entries"] = {str(k): str(v) for k, v in file.items()} if isinstance(file, dict) else {}
        else:
            row["value"] = "" if file is None else str(file)
        out.append(row)
    return out
