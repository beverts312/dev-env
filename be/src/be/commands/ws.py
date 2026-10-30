"""`be ws`: workspace helpers (replaces scripts/workspace_setup.py)."""

from __future__ import annotations

import json
import os
import select
import shlex
import shutil
import subprocess
import sys
import termios
import tty
from pathlib import Path

import click
import yaml

from be import cmux, config, jira
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


def claude_command(extra_dirs: list[Path], model: str = "", extra: list[str] = ()) -> str:
    """claude with its model and dirs, then extra, already quoted."""
    parts = ["claude"]
    if model:
        parts += ["--model", shlex.quote(model)]
    for directory in extra_dirs:
        parts += ["--add-dir", shlex.quote(str(directory))]
    parts += extra
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
    if key in ("d", "D"):
        return index, "delete"
    if key in ("g", "G"):
        return index, "get"
    if key in ("j", "J"):
        return index, "jira"
    if key in ("o", "O"):
        return index, "browse"
    if key == "\t":
        return index, "toggle"
    if key in ("m", "M"):
        return index, "merge"
    if key in ("a", "A"):
        return index, "all"
    if key in ("r", "R"):
        return index, "ready"
    if key in ("u", "U"):
        return index, "automerge"
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


LIST_HINT = "enter open, g get, j refresh Jira, d delete, q quit"
WINDOW_HINT = "enter select, q quit"


def paint_list(names: list[str], index: int, *, redraw: bool, hint: str = LIST_HINT) -> None:
    if redraw:
        sys.stdout.write(f"\x1b[{len(names) + 1}A")
    # rows must not wrap, or the redraw above moves up too few lines
    width = max(shutil.get_terminal_size().columns - 3, 10)
    for i, name in enumerate(names):
        mark = ">" if i == index else " "
        sys.stdout.write(f"\x1b[2K{mark} {name[:width]}\r\n")
    sys.stdout.write(f"\x1b[2K{hint}\r\n")
    sys.stdout.flush()


def choose(
    names: list[str],
    index: int = 0,
    hint: str = LIST_HINT,
    actions: tuple[str, ...] = ("open", "get", "jira", "delete"),
) -> tuple[str, int] | None:
    """Let the user move through names, starting at index.

    Returns (action, index) for any action in actions, or None on quit; other
    keys are ignored.
    """
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise click.ClickException("choosing from a list needs a terminal")
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    painted = False
    try:
        tty.setraw(fd)
        sys.stdout.write("\x1b[?25l")
        paint_list(names, index, redraw=False, hint=hint)
        painted = True
        while True:
            index, action = selection_action(index, len(names), read_key(fd))
            if action in actions:
                return action, index
            if action == "quit":
                return None
            if action == "abort":
                raise click.Abort()
            paint_list(names, index, redraw=True, hint=hint)
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


def window_labels(binary: str, windows: list[dict]) -> list[str]:
    """Label each window by its selected workspace, since windows have no titles."""
    # outside cmux, current-window is just the frontmost window, not ours
    here = cmux.current_window(binary) if cmux.inside() else None
    labels = []
    for window in windows:
        label = (
            f"{window.get('index')}: {cmux.window_title(binary, window['id'])}"
            f" ({window.get('workspace_count', 0)} workspaces)"
        )
        labels.append(label + (" - this window" if window["id"] == here else ""))
    return labels


def target_window(binary: str, value: str | None) -> str | None:
    """Resolve the --window value: pick asks, anything else goes to cmux as is.

    Unset means the caller's window inside cmux, and pick outside it.
    """
    if not value:
        if cmux.inside():
            return None
        value = "pick"
    if value != "pick":
        return value
    windows = cmux.list_windows(binary)
    if len(windows) <= 1:
        return None
    labels = window_labels(binary, windows)
    index = 0
    while True:
        chosen = choose(labels, index, hint=WINDOW_HINT)
        if chosen is None:
            raise click.Abort()
        action, index = chosen
        if action == "open":
            return windows[index]["id"]


def window_args(window: str | None) -> list[str]:
    return ["--window", window] if window else []


def open_root(root: Path, model: str | None = None, window: str | None = None) -> None:
    """Open root's saved layout in cmux, or switch to it if it is already open."""
    if not root.is_dir():
        raise click.ClickException(f"{root} is not a directory")
    if not model:
        model, _ = config.resolve("claude.model")
    binary = cmux.start()
    name = read_manifest(root).get("issue_name") or root.name
    if cmux.focus_existing(binary, name):
        return
    layout = cmux.get_layout(binary, root.name)
    stamp_claude(layout, claude_command([], model or ""), str(root))
    target = target_window(binary, window)
    cmux.new_workspace(
        binary,
        [
            "--name",
            name,
            "--cwd",
            str(root),
            "--focus",
            "true",
            "--layout",
            json.dumps(layout),
            *window_args(target),
        ],
    )


def start_work(root: Path, key: str, model: str | None = None, window: str | None = None) -> None:
    """Open root's workspace and start claude in plan mode on key, in a new pane beside the others."""
    if not model:
        model, _ = config.resolve("claude.model")
    open_root(root, model, window)
    binary = cmux.start()
    name = read_manifest(root).get("issue_name") or root.name
    found = cmux.find_workspace(binary, name)
    if found is None:
        raise click.ClickException(f"could not find the open cmux workspace {name}")
    prompt = shlex.quote(f"lets get started on {key}")
    command = claude_command([], model or "", ["--permission-mode", "plan", prompt])
    # new-pane has no --cwd
    cmux.new_pane(binary, *found, f"cd {shlex.quote(str(root))} && {command}")


def cloud_issue(text: str, model: str | None = None, window: str | None = None) -> None:
    """Open a cmux workspace running claude's /cloud-issue on text, in ws.dir or home."""
    if not model:
        model, _ = config.resolve("claude.model")
    parent, _ = config.resolve("ws.dir")
    cwd = Path(parent).expanduser() if parent else Path.home()
    binary = cmux.start()
    command = claude_command([], model or "", [shlex.quote(f"/cloud-issue {text}")])
    cmux.new_workspace(
        binary,
        [
            "--name",
            "cloud issue",
            "--cwd",
            str(cwd),
            "--focus",
            "true",
            "--command",
            command,
            *window_args(target_window(binary, window)),
        ],
    )


MANIFEST = "workspace.yml"


def write_manifest(
    root: Path, description: str, extra_dirs: list[Path], issue_name: str | None = None
) -> Path:
    manifest = {
        "name": root.name,
        "description": description,
        "extra_dirs": [str(directory) for directory in extra_dirs],
    }
    if issue_name:
        manifest["issue_name"] = issue_name
    path = root / MANIFEST
    path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    return path


def read_manifest(root: Path) -> dict:
    path = root / MANIFEST
    manifest = yaml.safe_load(path.read_text()) if path.is_file() else None
    return manifest if isinstance(manifest, dict) else {}


def workspace_details(root: Path) -> dict:
    """Read the manifest and find the repo checkouts directly under root."""
    manifest = read_manifest(root)
    repos = sorted(
        entry.name for entry in root.iterdir() if entry.is_dir() and (entry / ".git").exists()
    )
    details = {
        "name": manifest.get("name") or root.name,
        "description": manifest.get("description") or "",
        "repos": repos,
        "extra_dirs": manifest.get("extra_dirs") or [],
    }
    if manifest.get("issue_name"):
        details["issue_name"] = manifest["issue_name"]
    if manifest.get("issues"):
        details["issues"] = manifest["issues"]
    return details


def link_issue(root: Path, key: str) -> None:
    """Save key in root's manifest, so the issue finds this workspace though it isn't named after it."""
    manifest = read_manifest(root) or {"name": root.name, "description": "", "extra_dirs": []}
    issues = manifest.get("issues") if isinstance(manifest.get("issues"), list) else []
    if key not in issues:
        manifest["issues"] = [*issues, key]
    (root / MANIFEST).write_text(yaml.safe_dump(manifest, sort_keys=False))


def issue_workspaces(workspaces: list[tuple[str, object]]) -> dict[str, str]:
    """Map each upper-cased key a workspace answers to, its directory name and the issues linked to
    it, to that name; workspaces is (name, the manifest's issues) pairs. A name beats a link."""
    found = {}
    for name, issues in workspaces:
        for key in issues if isinstance(issues, list) else []:
            found.setdefault(str(key).upper(), name)
    found.update({name.upper(): name for name, _ in workspaces})
    return found


def issue_key(name: str) -> str | None:
    projects, _ = config.resolve("jira.projects")
    return jira.issue_key(name, projects or {})


def fetch_issue_name(name: str) -> str | None:
    """The Jira summary for a name that starts with a configured project key."""
    key = issue_key(name)
    if not key:
        return None
    try:
        return jira.issue_summary(key)
    except jira.JiraError as e:
        click.echo(f"could not fetch Jira issue {key}: {e}; continuing", err=True)
        return None


def refresh_issue_name(root: Path) -> None:
    """Look up root's Jira issue again and save its summary in the manifest."""
    if not issue_key(root.name):
        click.echo(f"{root.name} does not start with a key in jira.projects", err=True)
        return
    issue_name = fetch_issue_name(root.name)
    if not issue_name:
        return
    manifest = read_manifest(root) or {"name": root.name, "description": "", "extra_dirs": []}
    manifest["issue_name"] = issue_name
    (root / MANIFEST).write_text(yaml.safe_dump(manifest, sort_keys=False))
    click.echo(f"{root.name}: {issue_name}")


def workspace_labels(entries: list[Path]) -> list[str]:
    """One line per workspace: its name, then its issue name and description."""
    width = max((len(entry.name) for entry in entries), default=0)
    labels = []
    for entry in entries:
        manifest = read_manifest(entry)
        details = [manifest.get("issue_name"), manifest.get("description")]
        labels.append(f"{entry.name:<{width}}  {' - '.join(d for d in details if d)}".rstrip())
    return labels


def show_workspace(root: Path) -> None:
    click.echo(yaml.safe_dump(workspace_details(root), sort_keys=False), nl=False)


def prompt_create(
    work_dir: str | None, repos: str, extra_dirs: str, description: str
) -> tuple[str, str, str, str]:
    """Ask for each create input, offering any value already given as the default."""
    work_dir = click.prompt("Workspace name", default=work_dir)
    repos = click.prompt("Repos (comma separated)", default=repos, show_default=bool(repos))
    extra_dirs = click.prompt(
        "Extra dirs (comma separated)", default=extra_dirs, show_default=bool(extra_dirs)
    )
    description = click.prompt("Description", default=description, show_default=bool(description))
    return work_dir, repos, extra_dirs, description


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
@click.argument("work_dir", required=False)
@click.argument("repos", required=False, default="")
@click.option(
    "--extra-dirs",
    default="",
    help="Comma separated directories to add as panes and to Claude's context.",
)
@click.option(
    "-d", "--description", default="", help=f"Description saved in {MANIFEST}."
)
@config.option(
    "ws.dir",
    "--dir",
    "parent",
    help="Parent directory for a relative WORK_DIR (default: current directory).",
)
@config.option("claude.model", "--model", help="Claude model, passed as claude --model.")
@config.option("work_org", "--org", help="GitHub org for the repos.")
@config.option(
    "cmux.window", "--window", help="cmux window to open in: pick, or an index, ref or UUID."
)
@config.interactive_option(
    "Prompt for the name, repos, extra dirs and description; by default only without WORK_DIR."
)
def create(
    work_dir: str | None,
    repos: str,
    extra_dirs: str,
    description: str,
    parent: str | None,
    model: str,
    org: str | None,
    window: str | None,
    interactive: bool | None,
) -> None:
    """Clone REPOS (comma separated) into WORK_DIR and open a cmux workspace."""
    # the setting only fills in a missing WORK_DIR, so scripted creates don't prompt
    if interactive is None and work_dir:
        interactive = False
    interactive = config.interactive(interactive)
    if interactive:
        work_dir, repos, extra_dirs, description = prompt_create(
            work_dir, repos, extra_dirs, description
        )
    elif not work_dir:
        raise click.UsageError("missing WORK_DIR; pass it or use -i")
    create_workspace(work_dir, repos, extra_dirs, description, parent, model, org, window)


def create_workspace(
    work_dir: str,
    repos: str,
    extra_dirs: str,
    description: str,
    parent: str | None,
    model: str,
    org: str | None,
    window: str | None,
    issue_name: str | None = None,
) -> None:
    """Clone repos into work_dir, open it in cmux, and save its layout.

    Without issue_name, it is looked up in Jira when work_dir starts with an issue key.
    """
    repo_names = parse_csv(repos)
    dirs = extra_dir_paths(extra_dirs)

    root = workspace_root(work_dir, parent)
    root.mkdir(parents=True, exist_ok=True)
    if issue_name is None:
        issue_name = fetch_issue_name(root.name)
    write_manifest(root, description, dirs, issue_name)
    os.chdir(root)

    for repo in repo_names:
        if clone(repo_slug(repo, org)) != 0:
            click.echo(f"clone of {repo} failed; continuing", err=True)
    # owner/repo clones into a directory named after the repo
    checkouts = [repo.rsplit("/", 1)[-1] for repo in repo_names]

    binary = cmux.start()
    args = ["--name", issue_name or root.name, "--cwd", str(root), "--focus", "true"]
    args += window_args(target_window(binary, window))
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
@config.option(
    "cmux.window", "--window", help="cmux window to open in: pick, or an index, ref or UUID."
)
def open_workspace(name: str, parent: str | None, model: str, window: str | None) -> None:
    """Open the cmux layout that `ws create` saved for NAME, with Claude in the main pane."""
    open_root(workspace_root(name, parent), model, window)


@ws.command(name="get")
@click.argument("name")
@config.option(
    "ws.dir",
    "--dir",
    "parent",
    help="Parent directory for a relative NAME (default: current directory).",
)
def get_workspace(name: str, parent: str | None) -> None:
    """Show workspace NAME: its name, description, repos and extra dirs."""
    root = workspace_root(name, parent)
    if not root.is_dir():
        raise click.ClickException(f"{root} is not a directory")
    show_workspace(root)


@ws.command(name="list")
@config.option(
    "ws.dir",
    "--dir",
    "parent",
    help="Directory that holds the workspaces.",
)
@config.interactive_option("Select a workspace; enter opens it, g shows it.")
@config.option(
    "cmux.window", "--window", help="cmux window to open in: pick, or an index, ref or UUID."
)
def list_workspaces(parent: str | None, interactive: bool | None, window: str | None) -> None:
    """List workspaces. Also available as ls."""
    interactive = config.interactive(interactive)
    entries = workspace_entries(parent)
    if not interactive:
        for entry in entries:
            click.echo(entry.name)
        return
    index = 0
    while entries:
        chosen = choose(workspace_labels(entries), index)
        if chosen is None:
            return
        action, index = chosen
        if action == "open":
            open_root(entries[index], window=window)
            return
        if action == "get":
            show_workspace(entries[index])
            continue
        if action == "jira":
            refresh_issue_name(entries[index])
            continue
        name = entries[index].name
        try:
            root = delete_target(name, parent)
        except click.ClickException as e:
            click.echo(e.message, err=True)
            continue
        if click.confirm(f"Permanently delete workspace {name} and its cmux layout?"):
            remove_workspace(root)
            entries = workspace_entries(parent)
            index = min(index, max(len(entries) - 1, 0))
    click.echo("no workspaces")


ws.add_command(list_workspaces, name="ls")


def delete_target(name: str, parent: str | None) -> Path:
    """Resolve NAME to a workspace directory that is safe to remove."""
    base = Path(parent).expanduser() if parent else Path(".")
    # check before resolving, which would follow a symlinked NAME to its target
    if (base / Path(name).expanduser()).is_symlink():
        raise click.ClickException(f"{name} is a symlink, not a workspace directory")
    root = workspace_root(name, parent)
    home = Path.home().resolve()
    protected = {Path("/"), home, *home.parents}
    if parent:
        protected.add(Path(parent).expanduser().resolve())
    if root in protected:
        raise click.ClickException(f"refusing to delete {root}")
    if not root.is_dir():
        raise click.ClickException(f"{root} is not a workspace directory")
    return root


@ws.command()
@click.argument("name")
@config.option(
    "ws.dir",
    "--dir",
    "parent",
    help="Parent directory for a relative NAME (default: current directory).",
)
@click.option("--keep-layout", is_flag=True, help="Keep the saved cmux layout.")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted and stop.")
@click.option("-y", "--yes", is_flag=True, help="Delete without asking for confirmation.")
def delete(name: str, parent: str | None, keep_layout: bool, dry_run: bool, yes: bool) -> None:
    """Delete workspace NAME: its directory and its saved cmux layout. Also available as rm."""
    root = delete_target(name, parent)
    click.echo(f"directory: {root}")
    if not keep_layout:
        click.echo(f"cmux layout: {root.name}")
    if dry_run:
        return
    if not yes:
        click.confirm(f"Permanently delete workspace {root.name}?", abort=True)
    remove_workspace(root, keep_layout)


def remove_workspace(root: Path, keep_layout: bool = False) -> None:
    """Delete root and, unless keep_layout, the cmux layout saved under its name."""
    shutil.rmtree(root)
    click.echo(f"deleted {root}")
    if keep_layout:
        return
    try:
        binary = cmux.find_cmux()
    except click.ClickException as e:
        click.echo(f"{e.message}; layout {root.name} not deleted", err=True)
        return
    if cmux.delete_layout(binary, root.name):
        click.echo(f"deleted cmux layout {root.name}")
    else:
        click.echo(f"could not delete cmux layout {root.name}", err=True)


ws.add_command(delete, name="rm")
