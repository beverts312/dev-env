"""`be calendar`: your Google Calendar."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import click

from be import gcal

EMPTY = "nothing on the calendar"


@click.group(name="calendar")
def calendar_group() -> None:
    """Your Google Calendar."""


@calendar_group.command(name="login")
def login() -> None:
    """Sign in to Google through the browser and save the refresh token."""
    try:
        gcal.login()
    except gcal.CalendarError as e:
        raise click.ClickException(str(e)) from None
    click.echo("signed in; saved google.refresh_token")


def local_tz() -> str:
    """This machine's IANA time zone, e.g. America/Denver; UTC when it can't tell."""
    zone = datetime.now().astimezone().tzinfo
    key = getattr(zone, "key", None)
    if key:
        return key
    try:
        return str(Path("/etc/localtime").resolve()).split("zoneinfo/", 1)[1]
    except (OSError, IndexError):
        return "UTC"


def event_rows(events: list[dict]) -> list[str]:
    """One line per event: its time range (or "all day"), title, then [doc] when it has one."""
    rows = []
    for e in events:
        if e["all_day"]:
            when = "all day".ljust(11)
        else:
            start, end = (datetime.fromisoformat(e[k]).astimezone() for k in ("start", "end"))
            when = f"{start:%H:%M}–{end:%H:%M}"
        rows.append(f"{when}  {e['title']}{'  [doc]' if e['doc_url'] else ''}")
    return rows


@calendar_group.command(name="ls")
@click.option(
    "--day",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Day to list, as YYYY-MM-DD; today by default.",
)
def list_events(day: datetime | None) -> None:
    """List a day's events."""
    try:
        events = gcal.events(day.date() if day else date.today(), local_tz())
    except gcal.CalendarError as e:
        raise click.ClickException(str(e)) from None
    for row in event_rows(events) or [EMPTY]:
        click.echo(row)
