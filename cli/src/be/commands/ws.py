"""`be ws`: workspace helpers (replaces scripts/workspace_setup.py)."""

from __future__ import annotations

import json
import os
import select
import shlex
import subprocess
import sys
import termios
import tty
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


def workspace_root(work_dir: str, parent: str | None) -> Path:
    """Resolve WORK_DIR. Absolute paths win; relative ones sit under the parent."""
    path = Path(work_dir).expanduser()
    base = Path(parent).expanduser() if parent else Path(".")
    return (base / path).resolve()


def workspace_parent(parent: str | None) -> Path:
    if not parent:
        raise click.UsageError(
            "no workspace directory configured; set ws.dir, WS_DIR, or pass --dir"
        )
    root = Path(parent).expanduser().resolve()
    if not root.is_dir():
        raise click.ClickException(f"{root} is not a directory")
    return root


def workspace_entries(parent: str | None) -> list[Path]:
    root = workspace_parent(parent)
    entries = (
        path for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")
    )
    return sorted(entries, key=lambda path: path.name)


def selection_action(index: int, count: int, key: str) -> tuple[int, str]:
    """Return (index, action) for one key in the interactive list."""
    if key in ("\r", "\n"):
        return index, "open"
    if key in ("q", "Q", "esc"):
        return index, "quit"
    if key == "\x03":
        return index, "abort"
    if key == "up":
        return (index - 1) % count, "stay"
    if key == "down":
        return (index + 1) % count, "stay"
    return index, "stay"


def read_key(fd: int) -> str:
    ch = os.read(fd, 1)
    if ch != b"\x1b":
        return ch.decode(errors="replace")
    if not select.select([fd], [], [], 0.05)[0]:
        return "esc"
    nxt = os.read(fd, 1)
    if nxt not in (b"[", b"O") or not select.select([fd], [], [], 0.05)[0]:
        return "esc"
    last = os.read(fd, 1)
    return {b"A": "up", b"B": "down"}.get(last, "esc")


def paint_list(names: list[str], index: int, *, redraw: bool) -> None:
    if redraw:
        sys.stdout.write(f"\x1b[{len(names) + 1}A")
    for i, name in enumerate(names):
        mark = ">" if i == index else " "
        sys.stdout.write(f"\x1b[2K{mark} {name}\r\n")
    sys.stdout.write("\x1b[2Kenter open, q quit\r\n")
    sys.stdout.flush()


def choose(names: list[str]) -> str | None:
    """Let the user move through names. Enter returns the selected one."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise click.ClickException("-i needs a terminal")
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    index = 0
    painted = False
    try:
        tty.setraw(fd)
        sys.stdout.write("\x1b[?25l")
        paint_list(names, index, redraw=False)
        painted = True
        while True:
            index, action = selection_action(index, len(names), read_key(fd))
            if action == "open":
                return names[index]
            if action == "quit":
                return None
            if action == "abort":
                raise click.Abort()
            if action == "stay":
                paint_list(names, index, redraw=True)
    finally:
        sys.stdout.write("\x1b[?25h")
        if painted:
            sys.stdout.write(f"\x1b[{len(names) + 1}A\x1b[J")
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.flush()


def terminal_surfaces(node: object) -> list[dict]:
    found: list[dict] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "terminal":
                found.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return found


def stamp_claude(layout: dict, command: str, cwd: str) -> None:
    """Set the startup command on the main pane, the one named claude."""
    surfaces = terminal_surfaces(layout)
    named = [surface for surface in surfaces if surface.get("name") == "claude"]
    if named:
        target = named[0]
    elif len(surfaces) == 1:
        target = surfaces[0]
    else:
        raise click.ClickException("saved layout has no claude pane")
    target["command"] = command
    target["cwd"] = cwd
    target["focus"] = True


def open_root(root: Path, model: str | None = None) -> None:
    if not root.is_dir():
        raise click.ClickException(f"{root} is not a directory")
    if not model:
        model, _ = config.resolve("claude.model")
    binary = cmux.start()
    layout = cmux.get_layout(binary, root.name)
    stamp_claude(layout, claude_command([], model or ""), str(root))
    cmux.new_workspace(
        binary,
        [
            "--name",
            root.name,
            "--cwd",
            str(root),
            "--focus",
            "true",
            "--layout",
            json.dumps(layout),
        ],
    )


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
@config.option(
    "ws.dir",
    "--dir",
    "parent",
    help="Parent directory for a relative WORK_DIR (default: current directory).",
)
@config.option("claude.model", "--model", help="Claude model, passed as claude --model.")
@config.option("work_org", "--org", help="GitHub org for the repos.")
def create(
    work_dir: str, repos: str, extra_dirs: str, parent: str | None, model: str, org: str | None
) -> None:
    """Clone REPOS (comma separated) into WORK_DIR and open a cmux workspace."""
    repo_names = parse_csv(repos)
    dirs = extra_dir_paths(extra_dirs)

    root = workspace_root(work_dir, parent)
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


@ws.command(name="open")
@click.argument("name")
@config.option(
    "ws.dir",
    "--dir",
    "parent",
    help="Parent directory for a relative NAME (default: current directory).",
)
@config.option("claude.model", "--model", help="Claude model, passed as claude --model.")
def open_workspace(name: str, parent: str | None, model: str) -> None:
    """Open the cmux layout that `ws create` saved for NAME, with Claude in the main pane."""
    open_root(workspace_root(name, parent), model)


@ws.command(name="list")
@config.option(
    "ws.dir",
    "--dir",
    "parent",
    help="Directory that holds the workspaces.",
)
@click.option("-i", "--interactive", is_flag=True, help="Select a workspace; enter opens it.")
def list_workspaces(parent: str | None, interactive: bool) -> None:
    """List workspaces. Also available as ls."""
    entries = workspace_entries(parent)
    if not interactive:
        for entry in entries:
            click.echo(entry.name)
        return
    if not entries:
        click.echo("no workspaces")
        return
    chosen = choose([entry.name for entry in entries])
    if chosen is None:
        return
    open_root(next(entry for entry in entries if entry.name == chosen))


ws.add_command(list_workspaces, name="ls")
