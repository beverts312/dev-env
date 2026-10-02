"""`be pr`: pull request helpers (replaces scripts/pr_review.py)."""

from __future__ import annotations

import shlex
import shutil
from pathlib import Path

import click

from be import cmux, config
from be.github import clone_or_reuse, repo_slug


@click.group()
def pr() -> None:
    """Pull request helpers."""


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
    """Clone REPO and open Claude in cmux to run /pr-review on PR NUMBER."""
    slug = repo_slug(repo, org)
    root = Path(parent or ".").expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    short = slug.rsplit("/", 1)[-1]
    dest = root / short
    clone_or_reuse(slug, dest)

    binary = cmux.start()
    prompt = f"/pr-review {slug} {number}"
    cmux.new_workspace(
        binary,
        [
            "--name",
            f"pr-{short}-{number}",
            "--cwd",
            str(dest),
            "--command",
            "claude " + shlex.quote(prompt),
            "--focus",
            "true",
        ],
    )


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
