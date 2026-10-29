"""Todos kept as markdown files in todo.dir: YAML frontmatter for the fields, the body for notes.

Open todos are todo.dir/<id>.md; done ones move to todo.dir/done/<id>.md. A todo's id is its file's stem."""

from __future__ import annotations

import datetime as dt
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import click
import yaml

from be import config, jira

DONE_DIR = "done"
PRIORITIES = ("high", "med", "low")
# the fields a todo always has, in the order they're written; any others in a file are kept after them
FIELDS = ("title", "status", "priority", "due", "jira", "tags", "created", "completed")
DATES = ("due", "created", "completed")
EDITABLE = ("title", "priority", "due", "jira", "tags", "notes")
DUE_OFFSET = re.compile(r"^\+(\d+)([dw])$")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)


def todo_dir(given: str | None = None) -> Path:
    value = given or config.resolve("todo.dir")[0]
    return Path(value).expanduser()


def today() -> dt.date:
    return dt.date.today()


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60].strip("-") or "todo"


def parse_due(text: str | None) -> str | None:
    """An ISO date from YYYY-MM-DD, today, tomorrow, +Nd or +Nw; None for empty."""
    text = (text or "").strip().lower()
    if not text:
        return None
    if text == "today":
        return today().isoformat()
    if text == "tomorrow":
        return (today() + dt.timedelta(days=1)).isoformat()
    match = DUE_OFFSET.match(text)
    if match:
        days = int(match.group(1)) * (7 if match.group(2) == "w" else 1)
        return (today() + dt.timedelta(days=days)).isoformat()
    try:
        return dt.date.fromisoformat(text).isoformat()
    except ValueError:
        raise click.ClickException(f"bad due date {text!r}: use YYYY-MM-DD, today, tomorrow, +Nd or +Nw") from None


def parse_priority(text: str | None) -> str | None:
    text = (text or "").strip().lower()
    if not text:
        return None
    if text not in PRIORITIES:
        raise click.ClickException(f"priority must be one of {', '.join(PRIORITIES)}, not {text!r}")
    return text


def parse_jira(text: str | None) -> str | None:
    text = (text or "").strip().upper()
    if not text:
        return None
    if not jira.ISSUE_KEY.fullmatch(text):
        raise click.ClickException(f"{text!r} is not an issue key")
    return text


def parse_tags(tags: Any) -> list[str]:
    """Tags from a list or a comma-separated string, trimmed, without blanks or repeats."""
    if isinstance(tags, str):
        tags = tags.split(",")
    out: list[str] = []
    for tag in tags or ():
        tag = str(tag).strip()
        if tag and tag not in out:
            out.append(tag)
    return out


def as_text(value: Any) -> str | None:
    """A frontmatter value as text; yaml reads 2026-11-03 as a date."""
    if value is None or value == "":
        return None
    return value.isoformat() if isinstance(value, dt.date) else str(value)


def load(path: Path) -> dict:
    """The todo in path. A file without frontmatter is all notes, and its title is its stem."""
    text = path.read_text()
    meta: Any = {}
    notes = text
    match = FRONTMATTER.match(text)
    if match:
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        if isinstance(meta, dict):
            notes = match.group(2)
        else:
            meta = {}
    done = path.parent.name == DONE_DIR
    due = as_text(meta.get("due"))
    todo = {
        **{key: value for key, value in meta.items() if key not in FIELDS},
        "id": path.stem,
        "title": as_text(meta.get("title")) or path.stem,
        "status": "done" if done else "open",
        "priority": as_text(meta.get("priority")),
        "due": due,
        "jira": as_text(meta.get("jira")),
        "tags": parse_tags(meta.get("tags")),
        "created": as_text(meta.get("created")),
        "completed": as_text(meta.get("completed")),
        "notes": notes.strip("\n"),
    }
    todo["overdue"] = not done and due is not None and due < today().isoformat()
    return todo


def dump(todo: dict, path: Path) -> None:
    """Write todo to path, atomically; empty fields are left out."""
    meta = {key: todo.get(key) for key in FIELDS}
    meta |= {key: value for key, value in todo.items() if key not in (*FIELDS, "id", "notes", "overdue")}
    meta = {key: value for key, value in meta.items() if value not in (None, "", [])}
    for key in DATES:
        # written as dates rather than quoted strings, as a hand-written file would have them
        if isinstance(meta.get(key), str):
            meta[key] = dt.date.fromisoformat(meta[key])
    text = "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, default_flow_style=None) + "---\n"
    if todo.get("notes"):
        text += "\n" + todo["notes"].strip("\n") + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".todo-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def paths(root: Path, include_done: bool) -> list[Path]:
    folders = [root, root / DONE_DIR] if include_done else [root]
    return [path for folder in folders if folder.is_dir() for path in sorted(folder.glob("*.md"))]


def sort_key(todo: dict) -> tuple:
    """Open before done; overdue first, then by due date (none last), priority, and created."""
    rank = PRIORITIES.index(todo["priority"]) if todo["priority"] in PRIORITIES else len(PRIORITIES)
    return (
        todo["status"] == "done",
        not todo["overdue"],
        todo["due"] or "9999",
        rank,
        todo["created"] or "",
        todo["id"],
    )


def list_todos(
    root: Path, include_done: bool = False, only_done: bool = False, tag: str | None = None, key: str | None = None
) -> list[dict]:
    todos = [load(path) for path in paths(root, include_done or only_done)]
    if only_done:
        todos = [t for t in todos if t["status"] == "done"]
    if tag:
        todos = [t for t in todos if tag in t["tags"]]
    if key:
        todos = [t for t in todos if (t["jira"] or "").upper() == key.upper()]
    return sorted(todos, key=sort_key)


def find(root: Path, ref: str) -> Path:
    """The file of the todo whose id is ref, else the only one it starts."""
    ref = ref.strip()
    if not ref or "/" in ref or ref in (".", ".."):
        raise click.ClickException(f"{ref!r} is not a todo id")
    every = paths(root, include_done=True)
    exact = [path for path in every if path.stem == ref]
    if exact:
        return exact[0]
    found = [path for path in every if path.stem.startswith(ref)]
    if not found:
        raise click.ClickException(f"no todo {ref}")
    if len(found) > 1:
        raise click.ClickException(f"{ref} matches {', '.join(path.stem for path in found)}")
    return found[0]


def new_id(root: Path, title: str) -> str:
    base = slugify(title)
    taken = {path.stem for path in paths(root, include_done=True)}
    name, n = base, 2
    while name in taken:
        name, n = f"{base}-{n}", n + 1
    return name


def add(
    root: Path,
    title: str,
    due: str | None = None,
    priority: str | None = None,
    tags: Any = (),
    key: str | None = None,
    notes: str = "",
) -> dict:
    title = title.strip()
    if not title:
        raise click.ClickException("a todo needs a title")
    todo = {
        "id": new_id(root, title),
        "title": title,
        "status": "open",
        "priority": parse_priority(priority),
        "due": parse_due(due),
        "jira": parse_jira(key),
        "tags": parse_tags(tags),
        "created": today().isoformat(),
        "completed": None,
        "notes": notes or "",
    }
    path = root / f"{todo['id']}.md"
    dump(todo, path)
    return load(path)


def update(root: Path, ref: str, **fields: Any) -> dict:
    """Change the EDITABLE fields given; None leaves one as it is."""
    path = find(root, ref)
    todo = load(path)
    parsers = {"priority": parse_priority, "due": parse_due, "jira": parse_jira, "tags": parse_tags}
    for name, value in fields.items():
        if name not in EDITABLE:
            raise click.ClickException(f"can't change {name}")
        if value is None:
            continue
        if name == "title":
            value = value.strip()
            if not value:
                raise click.ClickException("a todo needs a title")
        todo[name] = parsers[name](value) if name in parsers else value
    dump(todo, path)
    return load(path)


def set_done(root: Path, ref: str, done: bool = True) -> dict:
    """Mark the todo done, moving it to done/, or open again, moving it back."""
    path = find(root, ref)
    todo = load(path)
    todo["completed"] = today().isoformat() if done else None
    todo["status"] = "done" if done else "open"
    target = (root / DONE_DIR if done else root) / path.name
    dump(todo, target)
    if target != path:
        path.unlink()
    return load(target)


def remove(root: Path, ref: str) -> str:
    path = find(root, ref)
    path.unlink()
    return path.stem
