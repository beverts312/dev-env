"""Helpers for driving the cmux terminal app."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from shutil import which

import click

from be import config

CMUX_APP_BIN = "/Applications/cmux.app/Contents/Resources/bin/cmux"


def find_cmux() -> str:
    override, _ = config.resolve("cmux.bin")
    if override:
        return override
    found = which("cmux")
    if found:
        return found
    if os.access(CMUX_APP_BIN, os.X_OK):
        return CMUX_APP_BIN
    raise click.ClickException("cmux not found")


def cmux_ready(cmux: str) -> bool:
    return (
        subprocess.run(
            [cmux, "ping"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode
        == 0
    )


def ensure_cmux_running(cmux: str) -> None:
    if cmux_ready(cmux):
        return
    subprocess.run(["open", "-a", "cmux"], check=True)
    for _ in range(10):
        if cmux_ready(cmux):
            return
        time.sleep(0.5)
    hint = ""
    if not inside():
        # the default socket mode, cmuxOnly, refuses processes started outside cmux
        hint = (
            "; if cmux is running, its socket may refuse processes outside cmux:"
            " check `cmux socket-status` and set automation.socketControlMode"
        )
    raise click.ClickException(f"cmux did not become ready{hint}")


def start() -> str:
    """Find cmux and make sure it is running; return its path."""
    cmux = find_cmux()
    ensure_cmux_running(cmux)
    return cmux


def new_workspace(cmux: str, args: list[str]) -> str:
    """Run `cmux new-workspace` with args, echo its output, and return stdout."""
    created = subprocess.run(
        [cmux, "new-workspace", *args], capture_output=True, text=True
    )
    sys.stdout.write(created.stdout)
    sys.stderr.write(created.stderr)
    if created.returncode != 0:
        raise click.exceptions.Exit(created.returncode)
    return created.stdout


def inside() -> bool:
    """Whether this process runs in a cmux terminal."""
    return bool(os.environ.get("CMUX_WORKSPACE_ID"))


def list_windows(cmux: str) -> list[dict]:
    """Return the cmux windows: id, index, workspace_count and more."""
    result = subprocess.run([cmux, "list-windows", "--json"], capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise click.ClickException("could not list cmux windows")
    try:
        windows = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise click.ClickException("cmux returned unreadable windows") from None
    if not isinstance(windows, list):
        raise click.ClickException("cmux returned unreadable windows")
    return windows


def current_window(cmux: str) -> str | None:
    """Return the id of the window the caller is in, if cmux knows it."""
    result = subprocess.run([cmux, "current-window"], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def list_workspaces(cmux: str, window: str) -> list[dict]:
    """Return window's workspaces (ref, id, title, selected and more), or [] if unreadable."""
    result = subprocess.run(
        [cmux, "workspace", "list", "--window", window, "--json"],
        capture_output=True,
        text=True,
        env={**os.environ, "CMUX_QUIET": "1"},
    )
    try:
        workspaces = json.loads(result.stdout)["workspaces"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []
    return workspaces if isinstance(workspaces, list) else []


def window_title(cmux: str, window: str) -> str:
    """Return the title of the selected workspace in window, or ""."""
    for workspace in list_workspaces(cmux, window):
        if workspace.get("selected"):
            return workspace.get("title") or ""
    return ""


def find_workspace(cmux: str, title: str) -> tuple[str, str] | None:
    """Return (window id, workspace id) of the first open workspace titled title."""
    for window in list_windows(cmux):
        for workspace in list_workspaces(cmux, window["id"]):
            if workspace.get("title") == title and workspace.get("id"):
                return window["id"], workspace["id"]
    return None


def show_workspace(cmux: str, window: str, workspace: str) -> None:
    """Bring window to the front with workspace selected in it."""
    for args in (
        ["focus-window", "--window", window],
        ["select-workspace", "--workspace", workspace, "--window", window],
    ):
        result = subprocess.run([cmux, *args], capture_output=True, text=True)
        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            raise click.ClickException(f"could not switch to cmux workspace {workspace}")
    # focusing a window doesn't raise cmux over the app we were run from
    if not inside():
        subprocess.run(["open", "-a", "cmux"])


def focus_existing(cmux: str, title: str) -> bool:
    """Switch to the open workspace titled title; False if there is none."""
    found = find_workspace(cmux, title)
    if found is None:
        return False
    show_workspace(cmux, *found)
    click.echo(f"switched to open workspace {title}")
    return True


def find_group(cmux: str, name: str) -> str | None:
    """Return the ref of the workspace group called name, if there is one."""
    result = subprocess.run(
        [cmux, "workspace-group", "list", "--json"], capture_output=True, text=True
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise click.ClickException("could not list cmux workspace groups")
    try:
        groups = json.loads(result.stdout)["groups"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise click.ClickException("cmux returned unreadable workspace groups") from None
    for group in groups:
        if group.get("name") == name:
            return group.get("ref")
    return None


def create_group(cmux: str, name: str, workspace: str) -> None:
    """Create a workspace group called name, anchored on workspace."""
    result = subprocess.run(
        [cmux, "workspace-group", "create", "--name", name, "--from", workspace],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise click.ClickException(f"could not create cmux workspace group {name}")


def get_layout(cmux: str, name: str) -> dict:
    """Return the layout tree saved by `cmux layout save`."""
    result = subprocess.run(
        [cmux, "layout", "get", name], capture_output=True, text=True
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise click.ClickException(f"no saved layout named {name}")
    try:
        layout = json.loads(result.stdout)["workspace"]["layout"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise click.ClickException(f"cmux returned an unreadable layout for {name}") from None
    if not isinstance(layout, dict):
        raise click.ClickException(f"cmux returned an unreadable layout for {name}")
    return layout


def delete_layout(cmux: str, name: str) -> bool:
    """Delete the layout saved as name; return whether cmux succeeded."""
    result = subprocess.run(
        [cmux, "layout", "delete", name], capture_output=True, text=True
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
    return result.returncode == 0


def workspace_ref(output: str) -> str | None:
    match = re.search(r"workspace:\d+", output)
    if match is None:
        return None
    return match.group(0)
