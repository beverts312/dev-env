"""Reading and filing Gmail threads, through google's sign-in; be never sends mail."""

from __future__ import annotations

import base64
import html as markup
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from be import config, google

API = "https://gmail.googleapis.com/gmail/v1/users/me"
NAME = "Gmail"
HEADERS = ("From", "To", "Cc", "Subject", "Date")
MailError = google.GoogleError

# the actions the mail page offers; prompt is what claude is asked, before the email
ACTIONS = [
    {"key": "summarize", "label": "Summarize", "prompt": "Summarize this email thread and list anything it asks of me."},
    {"key": "reply", "label": "Draft reply", "prompt": "/email-reply this thread; leave it as a draft."},
    {"key": "todo", "label": "Create todo", "prompt": "Create a be todo for what this email thread asks of me."},
    {"key": "cloud-issue", "label": "Cloud issue", "prompt": "/cloud-issue from this email thread:"},
]


def thread_url(id: str) -> str:
    return f"{API}/threads/{urllib.parse.quote(id, safe='')}"


def headers(message: dict) -> dict[str, str]:
    found = {h.get("name", "").lower(): h.get("value", "") for h in (message.get("payload") or {}).get("headers") or []}
    return {name.lower(): found.get(name.lower(), "") for name in HEADERS}


def summary(thread: dict) -> dict:
    """The list's row for a thread fetched with format=metadata."""
    messages = thread.get("messages") or [{}]
    first, last = headers(messages[0]), messages[-1]
    labels = sorted({label for m in messages for label in m.get("labelIds") or []})
    return {
        "id": thread.get("id", ""),
        "from": headers(last)["from"],
        "subject": first["subject"] or "(no subject)",
        "snippet": markup.unescape(last.get("snippet", "")),
        "date": last.get("internalDate", ""),
        "unread": "UNREAD" in labels,
        "labels": labels,
        "count": len(messages),
    }


def list_threads(q: str = "in:inbox", page: str | None = None, limit: int = 50) -> tuple[list[dict], str | None]:
    """The threads q finds, newest first, and the token for the next page."""
    params = {"q": q, "maxResults": str(limit)}
    if page:
        params["pageToken"] = page
    data = google.get_json(f"{API}/threads", params, NAME)
    ids = [t["id"] for t in data.get("threads") or [] if t.get("id")]
    meta = {"format": "metadata", "metadataHeaders": list(HEADERS)}
    with ThreadPoolExecutor(8) as pool:
        threads = list(pool.map(lambda id: google.get_json(thread_url(id), meta, NAME), ids))
    return [summary(t) for t in threads], data.get("nextPageToken")


def decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def bodies(part: dict, found: dict[str, str]) -> dict[str, str]:
    """The first text/plain and text/html bodies under part, by type; attachments are skipped."""
    kind = part.get("mimeType", "")
    data = (part.get("body") or {}).get("data")
    if kind in ("text/plain", "text/html") and data and not part.get("filename") and kind not in found:
        found[kind] = decode(data)
    for child in part.get("parts") or []:
        bodies(child, found)
    return found


def message(raw: dict) -> dict:
    found = bodies(raw.get("payload") or {}, {})
    return {
        "id": raw.get("id", ""),
        **headers(raw),
        "date_ms": raw.get("internalDate", ""),
        "unread": "UNREAD" in (raw.get("labelIds") or []),
        "text": found.get("text/plain", ""),
        "html": found.get("text/html", ""),
    }


def get_thread(id: str) -> dict:
    data = google.get_json(thread_url(id), {"format": "full"}, NAME)
    messages = [message(m) for m in data.get("messages") or []]
    return {
        "id": data.get("id", id),
        "subject": (messages[0]["subject"] if messages else "") or "(no subject)",
        "messages": messages,
    }


def modify(id: str, add: list[str] = (), remove: list[str] = ()) -> None:
    google.post_json(f"{thread_url(id)}/modify", {"addLabelIds": list(add), "removeLabelIds": list(remove)}, NAME)


def trash(id: str) -> None:
    """Move the thread to Trash, which Gmail empties after 30 days."""
    google.post_json(f"{thread_url(id)}/trash", {}, NAME)


def text_of(html: str) -> str:
    """Rough plain text of an HTML body, for a message that has no text/plain part."""
    html = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", html)
    return markup.unescape(re.sub(r"<[^>]+>", "", html)).strip()


def thread_markdown(thread: dict) -> str:
    """The thread as markdown for claude, with the ids its Gmail tools need."""
    lines = [f"# {thread['subject']}", "", f"Gmail thread id: {thread['id']}", ""]
    for m in thread["messages"]:
        lines += [f"## From {m['from']} on {m['date']}", "", f"Message id: {m['id']}"]
        lines += [f"To: {m['to']}"] + ([f"Cc: {m['cc']}"] if m["cc"] else [])
        lines += ["", (m["text"] or text_of(m["html"])).strip(), ""]
    return "\n".join(lines)


def save_thread(thread: dict) -> Path:
    """Write the thread's markdown beside be's config, readable only by you; its path."""
    folder = config.config_path().parent / "mail"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = folder / f"{re.sub(r'[^A-Za-z0-9_-]', '', thread['id']) or 'thread'}.md"
    path.touch(mode=0o600)
    path.write_text(thread_markdown(thread))
    return path
