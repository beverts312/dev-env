"""`be compare`: comparison helpers (replaces scripts/compare_dirs.py)."""

from __future__ import annotations

import os
from pathlib import Path

import click

PROGRESS_EVERY = 500


@click.group()
def compare() -> None:
    """Comparison helpers."""


def relative_files(base: Path) -> set[str]:
    """Return every file under base as a path relative to it. Progress goes to stderr."""
    click.echo(f"Scanning {base}...", err=True)
    files: set[str] = set()
    for root, _, names in os.walk(base):
        rel_root = Path(root).relative_to(base)
        for name in names:
            files.add((rel_root / name).as_posix())
            if len(files) % PROGRESS_EVERY == 0:
                click.echo(f"  Found {len(files)} files so far...\r", err=True, nl=False)
    click.echo(f"  Done. Found {len(files)} files.", err=True)
    return files


DIR = click.Path(exists=True, file_okay=False, resolve_path=True, path_type=Path)


@compare.command()
@click.argument("source", envvar="SOURCE", type=DIR)
@click.argument("target", envvar="TARGET", type=DIR)
@click.option(
    "-m",
    "--matching",
    is_flag=True,
    help="List files in both directories instead of files only in TARGET.",
)
def dirs(source: Path, target: Path, matching: bool) -> None:
    """List files in TARGET but not SOURCE, by path relative to each root.

    SOURCE and TARGET fall back to the SOURCE and TARGET env vars. The file
    list goes to stdout and progress to stderr, so the output can be piped.
    """
    source_files = relative_files(source)
    target_files = relative_files(target)

    if matching:
        result = sorted(target_files & source_files)
        click.echo(f"{len(result)} file(s) exist in both directories:", err=True)
    else:
        result = sorted(target_files - source_files)
        click.echo(f"{len(result)} file(s) exist in TARGET but not SOURCE:", err=True)
    for path in result:
        click.echo(path)
