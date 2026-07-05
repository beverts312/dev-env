#!/usr/bin/env python3
"""Configure the local machine for use with this dev-env repository."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from shutil import which

MARKER = "# dev-env configure.py"
SCRIPT_DIR = Path(__file__).resolve().parent


def detect_shell() -> str:
    shell = os.environ.get("SHELL", "")
    if shell:
        name = Path(shell).name
        if name:
            return name
    return "zsh"


def expand_path(path: str) -> Path:
    return Path(os.path.expanduser(path)).resolve()


def shell_config_path(shell_name: str) -> Path:
    return Path.home() / f".{shell_name}rc"


def prompt_notes_dir(default: str) -> Path:
    try:
        response = input(f"Notes directory [{default}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        sys.exit(1)
    if not response:
        response = default
    return expand_path(response)


def write_benvrc(
    notes_dir: Path,
    dev_env_home: Path,
    git_remote: str,
    work_registry: str,
) -> Path:
    notes_dir.mkdir(parents=True, exist_ok=True)
    benvrc_path = notes_dir / ".benvrc"
    benvrc_path.write_text(
        "\n".join(
            [
                MARKER,
                f'export DEFAULT_GIT_REMOTE="{git_remote}"',
                f'export DEV_ENV_HOME="{dev_env_home}"',
                f'export WORK_REGISTRY="{work_registry}"',
                'source "${DEV_ENV_HOME}/.bash_profile"',
                "",
            ]
        )
    )
    return benvrc_path


def update_shell_config(shell_config: Path, benvrc_path: Path) -> None:
    source_line = f'source "{benvrc_path}"'
    block = f"{MARKER}\n{source_line}\n"
    pattern = re.compile(
        rf"{re.escape(MARKER)}\nsource \".*?\"\n?",
        re.MULTILINE,
    )

    if shell_config.exists():
        content = shell_config.read_text()
        if pattern.search(content):
            content = pattern.sub(block, content)
        elif MARKER in content:
            content = content.rstrip() + "\n\n" + block
        else:
            if content and not content.endswith("\n"):
                content += "\n"
            content += "\n" + block
    else:
        content = block

    shell_config.parent.mkdir(parents=True, exist_ok=True)
    shell_config.write_text(content)


def configure_git(name: str, email: str) -> None:
    if not which("git"):
        print("git not found; skipping global user.name and user.email.", file=sys.stderr)
        return

    subprocess.run(
        ["git", "config", "--global", "user.name", name],
        check=True,
    )
    subprocess.run(
        ["git", "config", "--global", "user.email", email],
        check=True,
    )
    print(f"Set global git user.name to {name!r}")
    print(f"Set global git user.email to {email!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Configure your machine for use with this dev-env repository.",
    )
    parser.add_argument(
        "--notes",
        help="Notes directory for .benvrc (prompted if omitted, default: ~/notes)",
    )
    parser.add_argument(
        "--default-git-remote",
        default="origin",
        help="Value for DEFAULT_GIT_REMOTE (default: origin)",
    )
    parser.add_argument(
        "--work-registry",
        default="beverts312",
        help="Value for WORK_REGISTRY (default: beverts312)",
    )
    parser.add_argument(
        "--dev-env-home",
        default=str(SCRIPT_DIR),
        help="Value for DEV_ENV_HOME (default: directory containing this script)",
    )
    parser.add_argument(
        "--default-shell",
        default=None,
        help="Shell whose rc file to update (default: invoker's shell, else zsh)",
    )
    parser.add_argument(
        "--git-name",
        default="beverts312",
        help="Global git user.name (default: beverts312)",
    )
    parser.add_argument(
        "--git-email",
        default="texas312@gmail.com",
        help="Global git user.email (default: texas312@gmail.com)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    notes_dir = expand_path(args.notes) if args.notes else prompt_notes_dir("~/notes")
    dev_env_home = expand_path(args.dev_env_home)
    shell_name = args.default_shell or detect_shell()
    shell_config = shell_config_path(shell_name)

    benvrc_path = write_benvrc(
        notes_dir,
        dev_env_home,
        args.default_git_remote,
        args.work_registry,
    )
    update_shell_config(shell_config, benvrc_path)
    configure_git(args.git_name, args.git_email)

    print(f"Wrote {benvrc_path}")
    print(f"Updated {shell_config}")
    print()
    print("Restart your shell or run:")
    print(f'  source "{benvrc_path}"')


if __name__ == "__main__":
    main()
