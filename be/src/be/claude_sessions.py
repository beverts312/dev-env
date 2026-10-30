"""The Claude Code sessions run in a workspace, from the transcripts under ~/.claude/projects."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import click

# lines that hold a session's title and last prompt; the transcript's other lines are skipped unparsed
META = ('{"type":"custom-title"', '{"type":"ai-title"', '{"type":"last-prompt"')


def projects_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def project_key(path: Path | str) -> str:
    """The folder claude keeps a cwd's sessions in: every non-alphanumeric character becomes -."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def first_cwd(file: Path) -> str | None:
    with file.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"cwd"' in line:
                try:
                    cwd = json.loads(line).get("cwd")
                except json.JSONDecodeError:
                    continue
                if cwd:
                    return cwd
    return None


def within(cwd: str, root: Path) -> bool:
    path = Path(cwd)
    return path == root or root in path.parents


def session_files(root: Path) -> list[Path]:
    """root's transcripts, and those of claude runs in folders under it. A folder's key can match a
    sibling workspace's too (ADC-1 and ADC-1-foo), so each transcript's cwd decides."""
    base = projects_dir()
    if not base.is_dir():
        return []
    key = project_key(root)
    files = []
    for folder in base.iterdir():
        if folder.is_dir() and (folder.name == key or folder.name.startswith(key + "-")):
            for file in folder.glob("*.jsonl"):
                cwd = first_cwd(file)
                if cwd and within(cwd, root):
                    files.append(file)
    return files


def read_session(file: Path, root: Path) -> dict:
    titles: dict[str, str] = {}
    last_prompt = ""
    cwd = ""
    with file.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith(META):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = record["type"]
                if kind == "last-prompt":
                    last_prompt = record.get("lastPrompt") or last_prompt
                else:
                    titles[kind] = record.get("customTitle") or record.get("aiTitle") or titles.get(kind, "")
            elif not cwd and '"cwd"' in line:
                try:
                    cwd = json.loads(line).get("cwd") or ""
                except json.JSONDecodeError:
                    pass
    stat = file.stat()
    subdir = str(Path(cwd).relative_to(root)) if cwd and within(cwd, root) else ""
    return {
        "id": file.stem,
        "title": titles.get("custom-title") or titles.get("ai-title") or last_prompt or file.stem,
        "last_prompt": last_prompt,
        "cwd": cwd or str(root),
        "subdir": "" if subdir == "." else subdir,
        "updated": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "size": stat.st_size,
    }


def list_sessions(root: Path) -> list[dict]:
    """root's sessions, the most recently used first."""
    sessions = [read_session(file, root) for file in session_files(root)]
    return sorted(sessions, key=lambda s: s["updated"], reverse=True)


def find_session(root: Path, session_id: str) -> Path:
    try:
        uuid.UUID(session_id)
    except ValueError as e:
        raise click.ClickException(f"{session_id!r} is not a session id") from e
    for file in session_files(root):
        if file.stem == session_id:
            return file
    raise click.ClickException(f"no session {session_id} in {root.name}")


def get_session(root: Path, session_id: str) -> dict:
    return read_session(find_session(root, session_id), root)


def remove(file: Path) -> None:
    """A transcript, and the folder of its subagents and tool results."""
    file.unlink()
    extra = file.with_suffix("")
    if extra.is_dir() and not extra.is_symlink():
        shutil.rmtree(extra)


def delete_session(root: Path, session_id: str) -> dict:
    """Delete one of root's sessions."""
    file = find_session(root, session_id)
    session = read_session(file, root)
    remove(file)
    return session


def delete_all(root: Path) -> int:
    """Delete all of root's sessions, then the project folders they leave empty. A folder's key can be
    a sibling workspace's too, so one with anything else left in it (as memory files) stays."""
    files = session_files(root)
    for file in files:
        remove(file)
    for folder in {file.parent for file in files}:
        memory = folder / "memory"
        if memory.is_dir() and not memory.is_symlink() and not any(memory.iterdir()):
            memory.rmdir()
        if not any(folder.iterdir()):
            folder.rmdir()
    return len(files)
