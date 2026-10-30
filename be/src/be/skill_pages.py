"""`be server`'s skill pages: each shows the newest file a skill wrote, and reruns the skill to refresh it."""

from __future__ import annotations

import glob
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import click

from be import config

log = logging.getLogger(__name__)

# each page's run log, and where its skill runs unless it sets cwd
PAGES_DIR = Path("~/.be/pages")
DEFAULT_ICON = "file-text"
# the lines of a failed run's log the page shows, when it has no result
TAIL = 40
# a claude.ai artifact the run published
ARTIFACT = re.compile(r"https://claude\.ai/(?:code/)?artifact/[A-Za-z0-9_-]+")


def page_dir(name: str) -> Path:
    return PAGES_DIR.expanduser() / name


def pages() -> dict[str, dict]:
    """The pages setting's pages, each with its icon and cwd filled in; one without a skill or an
    output is skipped."""
    found, _ = config.resolve("pages")
    out = {}
    for name, page in (found or {}).items():
        if not page.get("skill") or not page.get("output"):
            log.warning("skipping page %s: it needs a skill and an output", name)
            continue
        out[name] = {
            "name": name,
            "skill": page["skill"].lstrip("/"),
            "output": page["output"],
            "icon": page.get("icon") or DEFAULT_ICON,
            "prompt": page.get("prompt", ""),
            "cwd": str(Path(page["cwd"]).expanduser()) if page.get("cwd") else str(page_dir(name)),
        }
    return out


def latest(output: str) -> Path | None:
    """The newest file the output glob matches, if any."""
    files = [Path(p) for p in glob.glob(os.path.expanduser(output)) if os.path.isfile(p)]
    return max(files, key=lambda p: p.stat().st_mtime, default=None)


@dataclass
class Run:
    proc: subprocess.Popen
    started: float
    log: Path


def start(page: dict, model: str | None) -> Run:
    """Run the page's skill with claude -p in the background, from its cwd, logging to its page dir."""
    cwd = Path(page["cwd"])
    if cwd == page_dir(page["name"]):
        cwd.mkdir(parents=True, exist_ok=True)
    elif not cwd.is_dir():
        raise click.ClickException(f"{page['name']}'s cwd {cwd} is not a directory")
    logfile = page_dir(page["name"]) / "last-run.log"
    logfile.parent.mkdir(parents=True, exist_ok=True)
    # stream-json logs every tool result, so the artifacts the skill publishes can be found in it
    prompt = f"/{page['skill']} {page['prompt']}".strip()
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose"]
    if model:
        cmd += ["--model", model]
    with logfile.open("wb") as out:
        try:
            proc = subprocess.Popen(
                cmd, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True
            )
        except FileNotFoundError as e:
            raise click.ClickException("claude is not installed or not on PATH") from e
    log.info("started /%s for page %s in %s", page["skill"], page["name"], cwd)
    return Run(proc, time.time(), logfile)


def read_log(path: Path) -> dict:
    """The claude.ai artifacts a run's stream-json log links, in the order first seen; its final
    result's text and whether that was an error; and its last lines."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        text = ""
    out = {"links": list(dict.fromkeys(ARTIFACT.findall(text))), "result": None, "is_error": False}
    lines = text.splitlines()
    out["tail"] = lines[-TAIL:]
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            out["result"] = str(event.get("result") or "") or None
            out["is_error"] = bool(event.get("is_error"))
            break
    return out


def status(run: Run | None) -> dict:
    """Whether the page's last run is going, and when it ended badly, why: its result, or else
    the end of its log."""
    out = {"running": False, "started_at": None, "exit_code": None, "error": None}
    if run is None:
        return out
    code = run.proc.poll()
    out.update(running=code is None, started_at=run.started, exit_code=code)
    if code is None:
        return out
    found = read_log(run.log)
    if code or found["is_error"]:
        detail = [found["result"]] if found["result"] else found["tail"]
        out["error"] = "\n".join([f"claude exited {code}", *detail])
    return out
