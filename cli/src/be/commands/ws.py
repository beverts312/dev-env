"""`be ws`: workspace helpers (replaces scripts/workspace_setup.py)."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

import click

from be import cmux, config
from be.github import clone, repo_slug


@click.group()
def ws() -> None:
    """Workspace helpers."""


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def extra_dir_paths(value: str) -> list[Path]:
    dirs = []
    for raw in parse_csv(value):
        path = Path(raw).expanduser().resolve()
        if not path.is_dir():
            click.echo(f"extra dir does not exist: {path}", err=True)
        dirs.append(path)
    return dirs


def terminal_pane(name: str, cwd: Path, command: str | None = None, focus: bool = False) -> dict:
    surface: dict = {"type": "terminal", "name": name, "cwd": str(cwd)}
    if command:
        surface["command"] = command
    if focus:
        surface["focus"] = True
    return {"pane": {"surfaces": [surface]}}


def claude_command(extra_dirs: list[Path], model: str = "") -> str:
    parts = ["claude"]
    if model:
        parts += ["--model", shlex.quote(model)]
    for directory in extra_dirs:
        parts += ["--add-dir", shlex.quote(str(directory))]
    return " ".join(parts)


def pane_name(name: str, used: set[str]) -> str:
    candidate = name
    suffix = 2
    while candidate in used:
        candidate = f"{name}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def build_layout(root: Path, repos: list[str], extra_dirs: list[Path], model: str = "") -> dict:
    used: set[str] = set()
    panes = [terminal_pane(pane_name(repo, used), root / repo) for repo in repos]
    panes += [terminal_pane(pane_name(directory.name, used), directory) for directory in extra_dirs]
    right = panes[-1]
    for pane in reversed(panes[:-1]):
        right = {"direction": "vertical", "children": [pane, right]}
    return {
        "direction": "horizontal",
        "split": 0.5,
        "children": [
            terminal_pane("claude", root, command=claude_command(extra_dirs, model), focus=True),
            right,
        ],
    }


@ws.command()
@click.argument("work_dir")
@click.argument("repos", required=False, default="")
@click.option(
    "--extra-dirs",
    default="",
    help="Comma separated directories to add as panes and to Claude's context.",
)
@config.option("claude.model", "--model", help="Claude model, passed as claude --model.")
@config.option("work_org", "--org", help="GitHub org for the repos.")
def setup(work_dir: str, repos: str, extra_dirs: str, model: str, org: str | None) -> None:
    """Clone REPOS (comma separated) into WORK_DIR and open a cmux workspace."""
    repo_names = parse_csv(repos)
    dirs = extra_dir_paths(extra_dirs)

    root = Path(work_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.chdir(root)

    for repo in repo_names:
        if clone(repo_slug(repo, org)) != 0:
            click.echo(f"clone of {repo} failed; continuing", err=True)
    # owner/repo clones into a directory named after the repo
    checkouts = [repo.rsplit("/", 1)[-1] for repo in repo_names]

    binary = cmux.start()
    args = ["--name", root.name, "--cwd", str(root), "--focus", "true"]
    if repo_names or dirs:
        args += ["--layout", json.dumps(build_layout(root, checkouts, dirs, model))]
    else:
        args += ["--command", claude_command([], model)]
    output = cmux.new_workspace(binary, args)

    ref = cmux.workspace_ref(output)
    if ref is None:
        raise click.ClickException("cmux did not report the new workspace")
    code = subprocess.run(
        [binary, "layout", "save", root.name, "--workspace", ref, "--overwrite"]
    ).returncode
    if code != 0:
        raise click.exceptions.Exit(code)
