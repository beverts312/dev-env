"""Resolving and cloning GitHub repos."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click


def repo_slug(name: str, org: str | None) -> str:
    if "/" in name:
        return name
    if not org:
        raise click.UsageError(f"{name!r} has no owner and WORK_ORG is not set")
    return f"{org}/{name}"


def clone(slug: str, dest: Path | str | None = None) -> int:
    cmd = ["git", "clone", "--recurse-submodules", f"git@github.com:{slug}.git"]
    if dest:
        cmd.append(str(dest))
    return subprocess.run(cmd).returncode


def remote_matches(dest: Path, slug: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(dest), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    url = result.stdout.strip().removesuffix(".git")
    return url.endswith(f":{slug}") or url.endswith(f"/{slug}")


def clone_or_reuse(slug: str, dest: Path) -> None:
    if dest.exists():
        if remote_matches(dest, slug):
            click.echo(f"using existing checkout {dest}")
            return
        raise click.ClickException(f"{dest} exists and is not {slug}")
    code = clone(slug, dest)
    if code != 0:
        raise click.exceptions.Exit(code)
