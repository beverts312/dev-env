import io
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

import pytest
from click.testing import CliRunner

from be import gcal, google
from be.cli import cli
from be.commands import calendar


def configure(*pairs):
    for key, value in pairs:
        assert CliRunner().invoke(cli, ["config", "set", key, value]).exit_code == 0


@pytest.fixture(autouse=True)
def no_cached_token(monkeypatch):
    monkeypatch.setattr(google, "_cached", None)


def event(**fields):
    return {
        "id": "e1",
        "status": "confirmed",
        "summary": "Standup",
        "start": {"dateTime": "2026-10-29T09:00:00-06:00"},
        "end": {"dateTime": "2026-10-29T09:15:00-06:00"},
        "htmlLink": "https://calendar.google.com/event?eid=1",
        **fields,
    }


def me(status):
    return [{"email": "me@x.com", "self": True, "responseStatus": status}, {"email": "pat@x.com"}]


def test_event_row():
    row = gcal.event_row(
        event(
            hangoutLink="https://meet.google.com/abc",
            attachments=[
                {"mimeType": "application/pdf", "fileUrl": "https://drive.google.com/x"},
                {"mimeType": gcal.DOC_TYPE, "fileUrl": "https://docs.google.com/document/d/notes"},
            ],
            attendees=me("tentative"),
        )
    )
    assert row == {
        "id": "e1",
        "title": "Standup",
        "start": "2026-10-29T09:00:00-06:00",
        "end": "2026-10-29T09:15:00-06:00",
        "all_day": False,
        "html_link": "https://calendar.google.com/event?eid=1",
        "meet_url": "https://meet.google.com/abc",
        "doc_url": "https://docs.google.com/document/d/notes",
        "location": "",
        "response": "tentative",
        "attendees": 2,
    }


def test_event_row_doc_from_description_and_video_entry_point():
    row = gcal.event_row(
        event(
            description='Agenda: <a href="https://docs.google.com/document/d/agenda/edit">doc</a>',
            conferenceData={"entryPoints": [{"entryPointType": "phone", "uri": "tel:1"}, {"entryPointType": "video", "uri": "https://zoom.us/j/1"}]},
        )
    )
    assert row["doc_url"] == "https://docs.google.com/document/d/agenda/edit"
    assert row["meet_url"] == "https://zoom.us/j/1"
    # your own event with no guests
    assert row["response"] == "accepted"


def test_event_row_all_day_and_dropped():
    row = gcal.event_row(event(start={"date": "2026-10-29"}, end={"date": "2026-10-30"}, summary=None))
    assert (row["all_day"], row["start"], row["end"], row["title"]) == (True, "2026-10-29", "2026-10-30", "(no title)")
    assert row["doc_url"] is None and row["meet_url"] is None
    assert gcal.event_row(event(status="cancelled")) is None
    assert gcal.event_row(event(attendees=me("declined"))) is None


def test_day_window():
    assert gcal.day_window(date(2026, 10, 29), "America/Denver") == (
        "2026-10-29T00:00:00-06:00",
        "2026-10-30T00:00:00-06:00",
    )
    # the day DST ends is 25 hours long
    assert gcal.day_window(date(2026, 11, 1), "America/Denver")[1] == "2026-11-02T00:00:00-07:00"
    with pytest.raises(gcal.CalendarError, match="unknown time zone"):
        gcal.day_window(date(2026, 10, 29), "Mars/Base")


def respond(routes, seen):
    def urlopen(request, timeout):
        seen.append(request)
        url = request.full_url
        for prefix, answer in routes.items():
            if url.startswith(prefix):
                return io.BytesIO(json.dumps(answer.pop(0) if isinstance(answer, list) else answer).encode())
        raise AssertionError(f"unexpected {url}")

    return urlopen


def test_events(monkeypatch):
    configure(("google.client_id", "cid"), ("google.client_secret", "cs"), ("google.refresh_token", "rt"))
    seen = []
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        respond(
            {
                gcal.TOKEN_URL: {"access_token": "at", "expires_in": 3600},
                f"{gcal.API}/calendars/primary/events": [
                    {"items": [event(), event(id="e2", status="cancelled")], "nextPageToken": "p2"},
                    {"items": [event(id="e3", summary="Retro")]},
                ],
            },
            seen,
        ),
    )
    rows = gcal.events(date(2026, 10, 29), "America/Denver")
    assert [r["title"] for r in rows] == ["Standup", "Retro"]
    token, first, second = seen
    assert dict(urllib.parse.parse_qsl(token.data.decode())) == {
        "client_id": "cid",
        "client_secret": "cs",
        "refresh_token": "rt",
        "grant_type": "refresh_token",
    }
    params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(first.full_url).query))
    assert params["timeMin"] == "2026-10-29T00:00:00-06:00"
    assert params["singleEvents"] == "true"
    assert first.get_header("Authorization") == "Bearer at"
    assert "pageToken=p2" in second.full_url
    # the access token is kept until it expires
    assert gcal.access_token() == "at" and len(seen) == 3


def test_events_errors(monkeypatch):
    with pytest.raises(gcal.CalendarError, match="be calendar login"):
        gcal.events(date(2026, 10, 29), "UTC")
    configure(("google.client_id", "cid"), ("google.client_secret", "cs"), ("google.refresh_token", "rt"))

    def revoked(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(b'{"error": "invalid_grant"}'))

    monkeypatch.setattr(urllib.request, "urlopen", revoked)
    with pytest.raises(gcal.CalendarError, match="expired or was revoked; run `be calendar login`"):
        gcal.events(date(2026, 10, 29), "UTC")


def test_calendar_ls(monkeypatch):
    monkeypatch.setattr(calendar, "local_tz", lambda: "UTC")
    asked = []
    monkeypatch.setattr(
        gcal,
        "events",
        lambda day, tz: asked.append((day, tz))
        or [
            gcal.event_row(event(start={"date": "2026-10-30"}, end={"date": "2026-10-31"}, summary="Offsite")),
            gcal.event_row(event(description="https://docs.google.com/document/d/x")),
        ],
    )
    result = CliRunner().invoke(cli, ["calendar", "ls", "--day", "2026-10-30"])
    assert result.exit_code == 0, result.output
    assert asked == [(date(2026, 10, 30), "UTC")]
    lines = result.output.splitlines()
    assert lines[0] == "all day      Offsite"
    assert lines[1].endswith("  Standup  [doc]")

    monkeypatch.setattr(gcal, "events", lambda day, tz: [])
    assert CliRunner().invoke(cli, ["calendar", "ls"]).output == "nothing on the calendar\n"
