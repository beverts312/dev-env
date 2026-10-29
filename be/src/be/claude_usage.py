"""Your Claude plan's usage against its limits, as Claude Code's /usage reports it."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile

import click

# /usage runs locally in print mode: no turn, no tokens
CMD = ["claude", "-p", "/usage", "--output-format", "json"]

# e.g. "Current week (all models): 18% used · resets Oct 30 at 10:59am (America/Denver)"
LIMIT = re.compile(r"^(.+?): (\d+)% used · resets (.+)$")


def fetch() -> str:
    """The text /usage prints."""
    try:
        # from a temp dir, so the run's session isn't saved under the repo it's started from
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run(CMD, capture_output=True, text=True, timeout=30, cwd=cwd)
    except FileNotFoundError as e:
        raise click.ClickException("claude is not installed or not on PATH") from e
    except subprocess.TimeoutExpired as e:
        raise click.ClickException("claude /usage timed out") from e
    if result.returncode != 0:
        raise click.ClickException(f"claude /usage failed: {(result.stderr or result.stdout).strip()}")
    try:
        out = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise click.ClickException(f"claude /usage printed no JSON: {result.stdout.strip()[:200]}") from e
    if out.get("is_error"):
        raise click.ClickException(f"claude /usage failed: {out.get('result', '')}")
    return out.get("result", "")


def parse(text: str) -> dict:
    """Each limit line as {label, percent, resets}; the first line as the plan note; what follows
    the limits as details. raw keeps it all, for text with no limits, as when signed in with an API key."""
    lines = text.splitlines()
    limits = []
    last = -1
    for i, line in enumerate(lines):
        m = LIMIT.match(line.strip())
        if m:
            limits.append({"label": m[1], "percent": int(m[2]), "resets": m[3]})
            last = i
    note = lines[0].strip() if lines and not LIMIT.match(lines[0].strip()) else ""
    return {
        "limits": limits,
        "plan_note": note,
        "details": "\n".join(lines[last + 1 :]).strip() if limits else "",
        "raw": text,
    }
