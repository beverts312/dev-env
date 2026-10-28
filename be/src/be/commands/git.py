"""`be git`: git helpers (replaces wclone and gauthor in aliases/git.sh)."""

from __future__ import annotations

import subprocess

import click

from be import config
from be.github import clone as clone_repo
from be.github import repo_slug


@click.group()
def git() -> None:
    """Git helpers."""


@git.command()
@click.argument("repo")
@click.argument("dest", required=False)
@config.option("work_org", "--org", help="GitHub org used when REPO has no owner.")
def clone(repo: str, dest: str | None, org: str | None) -> None:
    """Clone REPO (name or owner/repo) with submodules, optionally into DEST."""
    code = clone_repo(repo_slug(repo, org), dest)
    if code != 0:
        raise click.exceptions.Exit(code)


@git.command()
@config.option("git.email", "--email", required=True)
@config.option("git.name", "--name", required=True)
@click.option(
    "--local",
    is_flag=True,
    help="Write to the current repo's config instead of the global config.",
)
def author(email: str, name: str, local: bool) -> None:
    """Set git user.email and user.name."""
    scope = "--local" if local else "--global"
    for key, value in (("user.email", email), ("user.name", name)):
        subprocess.run(["git", "config", scope, key, value], check=True)
    click.echo(f"git author ({scope.lstrip('-')}): {name} <{email}>")
