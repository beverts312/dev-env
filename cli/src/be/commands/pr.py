"""`be pr`: pull request helpers (replaces scripts/pr_review.py)."""

from __future__ import annotations

import json
import shlex
import shutil
from pathlib import Path

import click

from be import cmux, config
from be.commands.ws import choose
from be.github import authored_prs, clone_or_reuse, repo_slug, review_requests, same_login

PR_GROUP = "prs"
# GraphQL reports the Renovate app as "renovate"; its PRs are hidden by default
RENOVATE_USER = "renovate"
# what pr ls says when a list is empty, keyed by --mine
EMPTY = {False: "no review requests", True: "no open PRs by you"}


@click.group()
def pr() -> None:
    """Pull request helpers."""


def pr_url(slug: str, number: int) -> str:
    return f"https://github.com/{slug}/pull/{number}"


def review_layout(dest: Path, prompt: str, url: str) -> dict:
    """Claude on the left, the pull request in a browser pane on the right."""
    return {
        "direction": "horizontal",
        "split": 0.5,
        "children": [
            {
                "pane": {
                    "surfaces": [
                        {
                            "type": "terminal",
                            "name": "claude",
                            "cwd": str(dest),
                            "command": "claude " + shlex.quote(prompt),
                            "focus": True,
                        }
                    ]
                }
            },
            {"pane": {"surfaces": [{"type": "browser", "name": "pr", "url": url}]}},
        ],
    }


@pr.command()
@click.argument("repo")
@click.argument("number", type=int)
@config.option(
    "pr.dir",
    "--parent",
    help="Parent folder to clone the repo into (default: current directory).",
)
@config.option("work_org", "--org", help="GitHub org used when REPO has no owner.")
def review(repo: str, number: int, parent: str | None, org: str | None) -> None:
    """Clone REPO and open cmux with Claude running /pr-review and the PR in a browser pane.

    The workspace goes in the `prs` workspace group, created on first use.
    """
    open_review(repo_slug(repo, org), number, parent)


def open_review(slug: str, number: int, parent: str | None) -> None:
    root = Path(parent or ".").expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    short = slug.rsplit("/", 1)[-1]
    dest = root / short
    clone_or_reuse(slug, dest)

    binary = cmux.start()
    prompt = f"/pr-review {slug} {number}"
    group = cmux.find_group(binary, PR_GROUP)
    args = [
        "--name",
        f"pr-{short}-{number}",
        "--cwd",
        str(dest),
        "--focus",
        "true",
        "--layout",
        json.dumps(review_layout(dest, prompt, pr_url(slug, number))),
    ]
    if group:
        args += ["--group", group]
    output = cmux.new_workspace(binary, args)
    if group:
        return
    # no group yet: anchor a new one on this workspace instead of an empty generated one
    ref = cmux.workspace_ref(output)
    if ref is None:
        click.echo(f"warning: could not find the new workspace; not adding it to {PR_GROUP}", err=True)
        return
    cmux.create_group(binary, PR_GROUP, ref)


pr.add_command(review, name="r")


PR_HEADER = ("PR", "REPO", "AUTHOR", "CHECKS", "TITLE")


def pr_rows(prs: list[dict], header: bool = False) -> list[str]:
    """One aligned line per PR: number, repo, author, checks, title."""
    cells = [
        (f"#{p['number']}", p["repo"], p["author"], p["checks"], p["title"]) for p in prs
    ]
    if header:
        cells.insert(0, PR_HEADER)
    # the title is last and left ragged
    widths = [max(len(row[i]) for row in cells) for i in range(len(PR_HEADER) - 1)]
    return [
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths)) + "  " + row[-1]
        for row in cells
    ]


def filter_prs(prs: list[dict], show_all: bool) -> tuple[list[dict], int]:
    """Ready PRs with passing checks, not by Renovate, unless show_all; returns (prs, hidden)."""
    if show_all:
        return prs, 0
    shown = [
        p
        for p in prs
        if p["checks"] == "pass" and not p["draft"] and not same_login(p["author"], RENOVATE_USER)
    ]
    return shown, len(prs) - len(shown)


def fetch_prs(mine: bool) -> list[dict]:
    return authored_prs() if mine else review_requests()


def hidden_note(hidden: int) -> str:
    return f"{hidden} hidden (draft, not passing, or by {RENOVATE_USER}); --all shows them"


@pr.command(name="list")
@config.option(
    "pr.dir",
    "--parent",
    help="Parent folder to clone into when reviewing (default: current directory).",
)
@click.option(
    "-i",
    "--interactive",
    is_flag=True,
    help="Select a PR; enter opens pr review, o opens it on GitHub, m toggles mine,"
    " a toggles --all.",
)
@click.option(
    "-a",
    "--all",
    "show_all",
    is_flag=True,
    help="Include drafts, PRs whose checks don't pass, and Renovate's PRs.",
)
@click.option("-m", "--mine", is_flag=True, help="List PRs you opened instead.")
def list_prs(parent: str | None, interactive: bool, show_all: bool, mine: bool) -> None:
    """List open PRs that request your review. Also available as ls.

    Only ready PRs with passing checks, not by Renovate, are shown unless you
    pass --all; the same applies with --mine.
    """
    if not interactive:
        prs, hidden = filter_prs(fetch_prs(mine), show_all)
        if hidden:
            click.echo(hidden_note(hidden), err=True)
        if not prs:
            click.echo(EMPTY[mine])
            return
        for row in pr_rows(prs, header=True):
            click.echo(row)
        return
    # each list is fetched once, so toggling back is instant
    fetched: dict[bool, list[dict]] = {}
    index = 0
    while True:
        if mine not in fetched:
            fetched[mine] = fetch_prs(mine)
        prs, hidden = filter_prs(fetched[mine], show_all)
        title = "your PRs" if mine else "review requests"
        if hidden:
            title += f" ({hidden} hidden)"
        keys = (
            f"m {'review requests' if mine else 'mine'},"
            f" a {'filter' if show_all else 'show all'}"
        )
        if prs:
            rows = pr_rows(prs)
            hint = f"{title} · enter review, o open on GitHub, {keys}, q quit"
            actions = ("open", "browse", "toggle", "all")
        else:
            rows = [EMPTY[mine]]
            hint = f"{title} · {keys}, q quit"
            actions = ("toggle", "all")
        chosen = choose(rows, min(index, len(rows) - 1), hint=hint, actions=actions)
        if chosen is None:
            return
        action, index = chosen
        if action == "toggle":
            mine = not mine
            index = 0
            continue
        if action == "all":
            show_all = not show_all
            index = 0
            continue
        if action == "browse":
            click.launch(pr_url(prs[index]["repo"], prs[index]["number"]))
            continue
        if action == "open":
            open_review(prs[index]["repo"], prs[index]["number"], parent)
            return


pr.add_command(list_prs, name="ls")


def guard_clean_target(parent: str | None) -> Path:
    """Resolve the PR directory, refusing anything that isn't clearly it."""
    if not parent:
        raise click.UsageError(
            "no PR directory configured; set pr.dir, PRS_DIR, or pass --parent"
        )
    root = Path(parent).expanduser().resolve()
    if not root.is_dir():
        raise click.ClickException(f"{root} is not a directory")
    if root in {Path("/"), Path.home().resolve()} or root in Path.home().resolve().parents:
        raise click.ClickException(f"refusing to clean {root}")
    return root


@pr.command()
@config.option("pr.dir", "--parent", help="PR directory to empty.")
@click.option("--dry-run", is_flag=True, help="List what would be deleted and stop.")
@click.option("-y", "--yes", is_flag=True, help="Delete without asking for confirmation.")
def clean(parent: str | None, dry_run: bool, yes: bool) -> None:
    """Delete everything inside the PR directory (the directory itself is kept)."""
    root = guard_clean_target(parent)
    entries = sorted(root.iterdir())
    if not entries:
        click.echo(f"{root} is already empty")
        return

    click.echo(f"{len(entries)} item(s) in {root}:")
    for entry in entries:
        click.echo(f"  {entry.name}{'/' if entry.is_dir() and not entry.is_symlink() else ''}")
    if dry_run:
        return
    if not yes:
        click.confirm(f"Permanently delete everything in {root}?", abort=True)

    for entry in entries:
        # symlinks are removed, never followed
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    click.echo(f"deleted {len(entries)} item(s) from {root}")
