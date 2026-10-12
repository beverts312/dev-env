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
    raise click.ClickException("cmux did not become ready")


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


def workspace_ref(output: str) -> str | None:
    match = re.search(r"workspace:\d+", output)
    if match is None:
        return None
    return match.group(0)
