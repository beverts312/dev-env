"""`be convert`: file format helpers (replaces scripts/json_to_csv.py and scripts/to_base64.py)."""

from __future__ import annotations

import base64
import csv
import json
from pathlib import Path

import click


@click.group()
def convert() -> None:
    """File format helpers."""


@convert.command("json-csv")
@click.argument("src", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, allow_dash=True),
    help="Output file, or - for stdout (default: SRC with a .csv suffix).",
)
def json_csv(src: Path, output: str | None) -> None:
    """Convert SRC, a JSON array of objects, to CSV with a header row.

    Columns are the union of every object's keys, in first-seen order.
    """
    try:
        rows = json.loads(src.read_text())
    except json.JSONDecodeError as e:
        raise click.ClickException(f"invalid JSON in {src}: {e}") from None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise click.ClickException(f"{src} must contain a JSON array of objects")

    fields = list(dict.fromkeys(key for row in rows for key in row))
    dest = output or str(src.with_suffix(".csv"))
    with click.open_file(dest, "w") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    if dest != "-":
        click.echo(f"Wrote {len(rows)} row(s) to {dest}", err=True)


@convert.command("base64")
@click.argument("src", type=click.File("rb"))
@click.option("-d", "--decode", is_flag=True, help="Decode SRC instead of encoding it.")
def to_base64(src, decode: bool) -> None:
    """Base64-encode SRC (a file, or - for stdin) and print it; -d decodes."""
    data = src.read()
    if decode:
        try:
            click.echo(base64.b64decode(data, validate=False), nl=False)
        except ValueError as e:
            raise click.ClickException(f"invalid base64: {e}") from None
    else:
        click.echo(base64.b64encode(data).decode())
