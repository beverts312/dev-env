"""`be jira`: Jira issue helpers."""

from __future__ import annotations

from pathlib import Path

import click

from be import config, jira
from be.commands.ws import choose, open_root, workspace_entries

EMPTY = "no in progress issues assigned to you"
FEATURE = "Feature"


@click.group(name="jira")
def jira_group() -> None:
    """Jira issue helpers."""


def issue_rows(issues: list[dict]) -> list[str]:
    """One aligned line per issue: key, type, then summary."""
    key_width = max(len(issue["key"]) for issue in issues)
    type_width = max(len(issue["type"]) for issue in issues)
    return [
        f"{issue['key'].ljust(key_width)}  {issue['type'].ljust(type_width)}  {issue['summary']}"
        for issue in issues
    ]


def filter_issues(issues: list[dict], show_all: bool) -> tuple[list[dict], int]:
    """Issues that aren't Features, unless show_all; returns (issues, hidden)."""
    if show_all:
        return issues, 0
    shown = [issue for issue in issues if issue["type"] != FEATURE]
    return shown, len(issues) - len(shown)


def hidden_note(hidden: int) -> str:
    return f"{hidden} hidden ({FEATURE}); --all shows them"


def issue_workspace(issue: dict, parent: str | None) -> Path | None:
    """The workspace named after the issue's key, else after its parent's key."""
    entries = {entry.name.upper(): entry for entry in workspace_entries(parent)}
    for key in (issue["key"], issue.get("parent")):
        if key and key.upper() in entries:
            return entries[key.upper()]
    return None


@jira_group.command(name="list")
@config.interactive_option(
    "Select an issue; enter opens its workspace, o opens it in the browser, a toggles --all."
)
@click.option("-a", "--all", "show_all", is_flag=True, help="Include issues whose type is Feature.")
@config.option("ws.dir", "--dir", "parent", help="Directory that holds the workspaces.")
@config.option(
    "cmux.window", "--window", help="cmux window to open in: pick, or an index, ref or UUID."
)
def list_issues(
    interactive: bool | None, show_all: bool, parent: str | None, window: str | None
) -> None:
    """List in progress issues assigned to you. Also available as ls.

    Features are hidden unless you pass --all.
    """
    interactive = config.interactive(interactive)
    try:
        fetched = jira.in_progress_issues()
    except jira.JiraError as e:
        raise click.ClickException(str(e)) from None
    if not interactive:
        issues, hidden = filter_issues(fetched, show_all)
        if hidden:
            click.echo(hidden_note(hidden), err=True)
        if not issues:
            click.echo(EMPTY)
            return
        for row in issue_rows(issues):
            click.echo(row)
        return
    index = 0
    while True:
        issues, hidden = filter_issues(fetched, show_all)
        title = "in progress"
        if hidden:
            title += f" ({hidden} hidden)"
        toggle = f"a {'filter' if show_all else 'show all'}"
        if issues:
            rows = issue_rows(issues)
            hint = f"{title} · enter open workspace, o open in browser, {toggle}, q quit"
            actions = ("open", "browse", "all")
        else:
            rows = [EMPTY]
            hint = f"{title} · {toggle}, q quit"
            actions = ("all",)
        chosen = choose(rows, min(index, len(rows) - 1), hint=hint, actions=actions)
        if chosen is None:
            return
        action, index = chosen
        if action == "all":
            show_all = not show_all
            index = 0
            continue
        issue = issues[index]
        if action == "browse":
            click.launch(jira.issue_url(issue["key"]))
            continue
        try:
            root = issue_workspace(issue, parent)
        except click.ClickException as e:
            click.echo(e.message, err=True)
            continue
        if root is None:
            keys = " or ".join(key for key in (issue["key"], issue.get("parent")) if key)
            click.echo(f"no workspace named {keys}", err=True)
            continue
        open_root(root, window=window)
        return


jira_group.add_command(list_issues, name="ls")
