"""Reading a day of Google Calendar events with your own OAuth desktop client.

Signing in is google's: `be calendar login`."""

from __future__ import annotations

import re
import urllib.parse
from datetime import date, datetime, time as clock, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from be import config, google

API = "https://www.googleapis.com/calendar/v3"
DOC_TYPE = "application/vnd.google-apps.document"
DOC_LINK = re.compile(r"https://docs\.google\.com/document/[^\s\"'<>]+")

CalendarError = google.GoogleError
TOKEN_URL = google.TOKEN_URL
login = google.login
access_token = google.access_token


def get_json(path: str, params: dict) -> dict:
    try:
        return google.get_json(f"{API}{path}", params, "Google Calendar")
    except CalendarError as e:
        if e.status == 404:
            raise CalendarError(f"{e}; check calendar.id", e.status) from None
        raise


def day_window(day: date, tz: str) -> tuple[str, str]:
    """RFC 3339 bounds of day in tz: its midnight and the next."""
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise CalendarError(f"unknown time zone {tz!r}") from None
    start = datetime.combine(day, clock(), zone)
    end = datetime.combine(day + timedelta(days=1), clock(), zone)
    return start.isoformat(), end.isoformat()


def doc_url(event: dict) -> str | None:
    """The first attached Google Doc (as Gemini attaches its notes), else one linked in the description."""
    for attachment in event.get("attachments") or []:
        if attachment.get("mimeType") == DOC_TYPE and attachment.get("fileUrl"):
            return attachment["fileUrl"]
    found = DOC_LINK.search(event.get("description") or "")
    return found.group(0) if found else None


def meet_url(event: dict) -> str | None:
    if event.get("hangoutLink"):
        return event["hangoutLink"]
    for entry in (event.get("conferenceData") or {}).get("entryPoints") or []:
        if entry.get("entryPointType") == "video" and entry.get("uri"):
            return entry["uri"]
    return None


def event_row(event: dict) -> dict | None:
    """The page's row for an event, or None for one cancelled or declined."""
    if event.get("status") == "cancelled":
        return None
    attendees = event.get("attendees") or []
    me = next((a for a in attendees if a.get("self")), None)
    response = me.get("responseStatus", "needsAction") if me else "accepted"
    if response == "declined":
        return None
    start, end = event.get("start") or {}, event.get("end") or {}
    all_day = "date" in start
    return {
        "id": event.get("id", ""),
        "title": event.get("summary") or "(no title)",
        "start": start.get("date") if all_day else start.get("dateTime"),
        "end": end.get("date") if all_day else end.get("dateTime"),
        "all_day": all_day,
        "html_link": event.get("htmlLink"),
        "meet_url": meet_url(event),
        "doc_url": doc_url(event),
        "location": event.get("location") or "",
        "response": response,
        "attendees": len(attendees),
    }


def events(day: date, tz: str) -> list[dict]:
    """Your events on day, in tz, in start order, without those cancelled or declined."""
    calendar, _ = config.resolve("calendar.id")
    time_min, time_max = day_window(day, tz)
    rows: list[dict] = []
    token = None
    while True:
        params = {
            "timeMin": time_min,
            "timeMax": time_max,
            "timeZone": tz,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": "250",
        }
        if token:
            params["pageToken"] = token
        data = get_json(f"/calendars/{urllib.parse.quote(calendar or 'primary', safe='')}/events", params)
        rows += [row for row in map(event_row, data.get("items") or []) if row]
        token = data.get("nextPageToken")
        if not token:
            return rows
