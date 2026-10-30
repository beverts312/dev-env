"""Reading a day of Google Calendar events with your own OAuth desktop client.

`be calendar login` signs in once through the browser and saves a refresh token; reads trade it
for an access token, kept until it expires."""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, datetime, time as clock, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import click

from be import config

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/calendar/v3"
SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
LOGIN = "run `be calendar login`"
DOC_TYPE = "application/vnd.google-apps.document"
DOC_LINK = re.compile(r"https://docs\.google\.com/document/[^\s\"'<>]+")

# (refresh token, access token, expires at)
_cached: tuple[str, str, float] | None = None


class CalendarError(Exception):
    pass


def client() -> tuple[str, str]:
    client_id, _ = config.resolve("google.client_id")
    client_secret, _ = config.resolve("google.client_secret")
    if not client_id or not client_secret:
        raise CalendarError("google.client_id and google.client_secret must be set")
    return client_id, client_secret


def post_token(fields: dict) -> dict:
    """POST fields to Google's token endpoint; its JSON answer."""
    request = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode(fields).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        try:
            error = json.load(e).get("error", "")
        except (ValueError, AttributeError):
            error = ""
        if error == "invalid_grant":
            raise CalendarError(f"the Google sign-in expired or was revoked; {LOGIN}") from None
        raise CalendarError(f"HTTP {e.code} from Google's token endpoint{f' ({error})' if error else ''}") from None
    except urllib.error.URLError as e:
        raise CalendarError(f"could not reach Google: {e.reason}") from None
    except (json.JSONDecodeError, TimeoutError) as e:
        raise CalendarError(str(e)) from None


def login(open_browser=webbrowser.open) -> None:
    """Sign in through the browser, with a loopback redirect and PKCE, and save the refresh token."""
    client_id, client_secret = client()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    got: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            if "code" in query or "error" in query:
                got.update(query)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Signed in to be; you can close this tab." if "code" in query else b"Sign-in failed.")

        def log_message(self, *args):
            pass

    with http.server.HTTPServer(("127.0.0.1", 0), Handler) as server:
        redirect = f"http://127.0.0.1:{server.server_port}"
        url = AUTH_URL + "?" + urllib.parse.urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect,
                "response_type": "code",
                "scope": SCOPE,
                "access_type": "offline",
                # without consent, Google only sends a refresh token the first time
                "prompt": "consent",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
            }
        )
        click.echo(f"Opening the browser to sign in; if it doesn't open, visit:\n{url}")
        open_browser(url)
        server.timeout = 5
        deadline = time.monotonic() + 300
        # the browser may ask for a favicon first
        while not got:
            if time.monotonic() > deadline:
                raise CalendarError("timed out waiting for the sign-in")
            server.handle_request()
    if got.get("error"):
        raise CalendarError(f"sign-in failed: {got['error']}")
    if got.get("state") != state:
        raise CalendarError("sign-in failed: the state didn't match")
    tokens = post_token(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": got["code"],
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect,
        }
    )
    if not tokens.get("refresh_token"):
        raise CalendarError("Google sent no refresh token")
    config.set_value("google.refresh_token", tokens["refresh_token"])


def access_token() -> str:
    global _cached
    refresh, _ = config.resolve("google.refresh_token")
    if not refresh:
        raise CalendarError(f"not signed in to Google; {LOGIN}")
    if _cached and _cached[0] == refresh and _cached[2] > time.time() + 60:
        return _cached[1]
    client_id, client_secret = client()
    tokens = post_token(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        }
    )
    if not tokens.get("access_token"):
        raise CalendarError("Google sent no access token")
    _cached = (refresh, tokens["access_token"], time.time() + float(tokens.get("expires_in", 3600)))
    return tokens["access_token"]


def get_json(path: str, params: dict) -> dict:
    request = urllib.request.Request(
        f"{API}{path}?{urllib.parse.urlencode(params)}",
        headers={"Authorization": f"Bearer {access_token()}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
    except urllib.error.HTTPError as e:
        hint = f"; {LOGIN}" if e.code in (401, 403) else "; check calendar.id" if e.code == 404 else ""
        raise CalendarError(f"HTTP {e.code} from Google Calendar{hint}") from None
    except urllib.error.URLError as e:
        raise CalendarError(f"could not reach Google Calendar: {e.reason}") from None
    except (json.JSONDecodeError, TimeoutError) as e:
        raise CalendarError(str(e)) from None
    if not isinstance(data, dict):
        raise CalendarError("unexpected response from Google Calendar")
    return data


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
