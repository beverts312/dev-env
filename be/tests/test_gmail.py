import base64
import json
import os
import urllib.parse
import urllib.request

import pytest
from click.testing import CliRunner

from be import gmail, google
from be.cli import cli
from tests.test_gcal import respond


@pytest.fixture(autouse=True)
def signed_in(monkeypatch):
    monkeypatch.setattr(google, "_cached", None)
    for key, value in (("google.client_id", "cid"), ("google.client_secret", "cs"), ("google.refresh_token", "rt")):
        assert CliRunner().invoke(cli, ["config", "set", key, value]).exit_code == 0


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def hdrs(**values):
    return [{"name": name.title(), "value": value} for name, value in values.items()]


def raw(id, labels=(), payload=None, **headers):
    return {
        "id": id,
        "labelIds": list(labels),
        "snippet": "Can you &amp; Pat look?",
        "internalDate": "1761700000000",
        "payload": {"headers": hdrs(**headers), **(payload or {})},
    }


def test_list_threads(monkeypatch):
    seen = []
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        respond(
            {
                google.TOKEN_URL: {"access_token": "at", "expires_in": 3600},
                f"{gmail.API}/threads?": {"threads": [{"id": "t1"}], "nextPageToken": "p2"},
                f"{gmail.API}/threads/t1": {
                    "id": "t1",
                    "messages": [
                        raw("m1", ["INBOX"], subject="Budget", **{"from": "pat@x.com"}),
                        raw("m2", ["INBOX", "UNREAD"], subject="Re: Budget", **{"from": "sam@x.com"}),
                    ],
                },
            },
            seen,
        ),
    )
    threads, page = gmail.list_threads("from:pat", "p1")
    assert page == "p2"
    assert threads == [
        {
            "id": "t1",
            "from": "sam@x.com",
            "subject": "Budget",
            "snippet": "Can you & Pat look?",
            "date": "1761700000000",
            "unread": True,
            "labels": ["INBOX", "UNREAD"],
            "count": 2,
        }
    ]
    params = urllib.parse.parse_qs(urllib.parse.urlparse(seen[1].full_url).query)
    assert params == {"q": ["from:pat"], "maxResults": ["50"], "pageToken": ["p1"]}
    params = urllib.parse.parse_qs(urllib.parse.urlparse(seen[2].full_url).query)
    assert params["format"] == ["metadata"] and "Subject" in params["metadataHeaders"]


def test_get_thread_decodes_nested_parts(monkeypatch):
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": b64("Hi — numbers attached")}},
                    {"mimeType": "text/html", "body": {"data": b64("<p>Hi</p>")}},
                ],
            },
            {"mimeType": "text/plain", "filename": "notes.txt", "body": {"attachmentId": "a1"}},
        ],
    }
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        respond(
            {
                google.TOKEN_URL: {"access_token": "at"},
                f"{gmail.API}/threads/t1": {"id": "t1", "messages": [raw("m1", ["UNREAD"], payload, subject="Budget", to="me@x.com")]},
            },
            [],
        ),
    )
    thread = gmail.get_thread("t1")
    assert thread["subject"] == "Budget"
    (m,) = thread["messages"]
    assert (m["text"], m["html"], m["to"], m["unread"]) == ("Hi — numbers attached", "<p>Hi</p>", "me@x.com", True)


def test_modify(monkeypatch):
    seen = []
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        respond({google.TOKEN_URL: {"access_token": "at"}, f"{gmail.API}/threads/t1/modify": {"id": "t1"}}, seen),
    )
    gmail.modify("t1", remove=["INBOX"])
    assert seen[1].get_method() == "POST"
    assert json.loads(seen[1].data) == {"addLabelIds": [], "removeLabelIds": ["INBOX"]}


def test_trash(monkeypatch):
    seen = []
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        respond({google.TOKEN_URL: {"access_token": "at"}, f"{gmail.API}/threads/t1/trash": {"id": "t1"}}, seen),
    )
    gmail.trash("t1")
    assert seen[1].get_method() == "POST" and seen[1].full_url == f"{gmail.API}/threads/t1/trash"


def test_thread_markdown_and_save(isolated_config):
    thread = {
        "id": "t1",
        "subject": "Budget",
        "messages": [
            {"id": "m1", "from": "pat@x.com", "to": "me@x.com", "cc": "", "date": "Wed", "text": "", "html": "<p>Q4 &amp; Q1</p><style>p{}</style>"}
        ],
    }
    text = gmail.thread_markdown(thread)
    assert "Gmail thread id: t1" in text and "Message id: m1" in text and "Q4 & Q1" in text
    path = gmail.save_thread(thread)
    assert path == isolated_config.parent / "mail" / "t1.md"
    assert path.read_text() == text
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
