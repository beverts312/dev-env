#!/usr/bin/env python3
"""Clone repos into a work directory and open a cmux workspace for them."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from shutil import which

CMUX_APP_BIN = "/Applications/cmux.app/Contents/Resources/bin/cmux"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", help="Directory to make things in")
    parser.add_argument(
        "repos",
        nargs="?",
        default="",
        help="Comma separated list of repos to clone",
    )
    parser.add_argument(
        "--extra-dirs",
        default="",
        help="Comma separated directories to add as panes and to Claude's context",
    )
    parser.add_argument(
        "--model",
        default="claude-opus-5-5",
        help="Default Claude model, passed as claude --model",
    )
    return parser.parse_args()


def wclone(org: str, repo: str) -> None:
    result = subprocess.run(
        ["git", "clone", "--recurse-submodules", f"git@github.com:{org}/{repo}.git"]
    )
    if result.returncode != 0:
        print(f"clone of {repo} failed; continuing", file=sys.stderr)


def find_cmux() -> str:
    found = which("cmux")
    if found:
        return found
    if os.access(CMUX_APP_BIN, os.X_OK):
        return CMUX_APP_BIN
    sys.exit("cmux not found")


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
    sys.exit("cmux did not become ready")


def terminal_pane(name: str, cwd: Path, command: str | None = None, focus: bool = False) -> dict:
    surface: dict = {"type": "terminal", "name": name, "cwd": str(cwd)}
    if command:
        surface["command"] = command
    if focus:
        surface["focus"] = True
    return {"pane": {"surfaces": [surface]}}


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def extra_dir_paths(value: str) -> list[Path]:
    dirs = []
    for raw in parse_csv(value):
        path = Path(raw).expanduser().resolve()
        if not path.is_dir():
            print(f"extra dir does not exist: {path}", file=sys.stderr)
        dirs.append(path)
    return dirs


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


def main() -> None:
    args = parse_args()
    repos = parse_csv(args.repos)
    extra_dirs = extra_dir_paths(args.extra_dirs)

    root = Path(args.work_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.chdir(root)

    org = os.environ.get("WORK_ORG", "")
    for repo in repos:
        wclone(org, repo)

    cmux = find_cmux()
    ensure_cmux_running(cmux)

    cmd = [cmux, "new-workspace", "--name", root.name, "--cwd", str(root), "--focus", "true"]
    if repos or extra_dirs:
        cmd += ["--layout", json.dumps(build_layout(root, repos, extra_dirs, args.model))]
    else:
        cmd += ["--command", claude_command([], args.model)]
    created = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(created.stdout)
    sys.stderr.write(created.stderr)
    if created.returncode != 0:
        sys.exit(created.returncode)

    ref = workspace_ref(created.stdout)
    if ref is None:
        sys.exit("cmux did not report the new workspace")
    sys.exit(
        subprocess.run(
            [cmux, "layout", "save", root.name, "--workspace", ref, "--overwrite"]
        ).returncode
    )


def workspace_ref(output: str) -> str | None:
    match = re.search(r"workspace:\d+", output)
    if match is None:
        return None
    return match.group(0)


if __name__ == "__main__":
    main()
