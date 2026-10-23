import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from urllib.parse import urlencode

import click
import pytest

from be import jira
from be.commands import pr, server

PRS = [
    {"number": 7, "repo": "acme/api", "title": "Fix <login>", "checks": "pass", "draft": False, "author": "dev"},
    {"number": 1234, "repo": "acme/web-app", "title": "Add page", "checks": "fail", "draft": False, "author": "dev"},
    {"number": 9, "repo": "acme/api", "title": "WIP", "checks": "pass", "draft": True, "author": "dev"},
    {"number": 5, "repo": "acme/api", "title": "Bump", "checks": "pass", "draft": False, "author": "renovate"},
]


def test_render_page_filters_by_default():
    page = server.render_page({False: PRS, True: []}, show_all=False)
    assert "review requests (3 hidden)" in page
    assert "https://github.com/acme/api/pull/7" in page
    assert "acme/web-app" not in page
    assert "no open PRs by you" in page
    assert 'href="/?all=1"' in page
    # titles are escaped
    assert "Fix &lt;login&gt;" in page and "<login>" not in page


ISSUES = [
    {"key": "ACME-12", "type": "Bug", "summary": "Fix <login>"},
    {"key": "ACME-1", "type": "Feature", "summary": "Big thing"},
]


def test_render_page_issues(isolated_config, monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://x.atlassian.net")
    page = server.render_page({False: [], True: []}, show_all=False, issues=ISSUES)
    assert "jira issues (1 hidden)" in page
    assert 'href="https://x.atlassian.net/browse/ACME-12"' in page
    assert "Fix &lt;login&gt;" in page
    assert "Big thing" not in page
    page = server.render_page({False: [], True: []}, show_all=True, issues=ISSUES)
    assert page.count('<tr class="issue">') == 2
    page = server.render_page({False: [], True: []}, show_all=False, issues="jira.url must be set")
    assert "jira: jira.url must be set" in page


def test_render_page_show_all():
    page = server.render_page({False: [], True: PRS}, show_all=True, message="opened x#1")
    assert page.count('<tr class="pr">') == 4
    assert "no review requests" in page
    assert " hidden)" not in page
    assert 'id="all" href="/"' in page
    assert "opened x#1" in page


@pytest.fixture
def serve(monkeypatch, tmp_path):
    fetched = []
    monkeypatch.setattr(pr, "review_requests", lambda: fetched.append("review") or PRS)
    monkeypatch.setattr(pr, "authored_prs", lambda: fetched.append("mine") or PRS[:3])
    monkeypatch.setattr(jira, "in_progress_issues", lambda: fetched.append("jira") or [])
    reviews = []
    monkeypatch.setattr(pr, "open_review", lambda *args: reviews.append(args))
    httpd = HTTPServer(("127.0.0.1", 0), server.make_handler(str(tmp_path)))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}", fetched, reviews, str(tmp_path)
    httpd.shutdown()
    httpd.server_close()


def get(url):
    with urllib.request.urlopen(url) as resp:
        return resp.read().decode()


def test_get_shows_both_tables_and_caches(serve):
    base, fetched, _, _ = serve
    page = get(base + "/")
    assert "review requests (3 hidden)" in page and "your PRs" in page
    assert get(base + "/?all=1").count('<tr class="pr">') == 7
    assert fetched == ["review", "mine", "jira"]
    get(base + "/refresh")
    assert fetched == ["review", "mine", "jira", "review", "mine", "jira"]


def test_get_shows_jira_errors(serve, monkeypatch):
    base, _, _, _ = serve

    def fail():
        raise jira.JiraError("HTTP 401 from x")

    monkeypatch.setattr(jira, "in_progress_issues", fail)
    get(base + "/refresh")
    page = get(base + "/")
    assert "jira: HTTP 401 from x" in page and "your PRs" in page


def test_post_review_opens_and_redirects(serve):
    base, _, reviews, parent = serve
    data = urlencode({"repo": "acme/api", "number": "7", "all": "1"}).encode()
    page = get(urllib.request.Request(base + "/review", data=data))
    assert reviews == [("acme/api", 7, parent)]
    assert "opened acme/api#7" in page
    assert page.count('<tr class="pr">') == 7


def test_post_review_shows_errors(serve, monkeypatch):
    base, _, _, _ = serve

    def fail(*args):
        raise click.ClickException("clone failed")

    monkeypatch.setattr(pr, "open_review", fail)
    data = urlencode({"repo": "acme/api", "number": "7"}).encode()
    assert "acme/api#7: clone failed" in get(urllib.request.Request(base + "/review", data=data))
    with pytest.raises(urllib.error.HTTPError):
        get(urllib.request.Request(base + "/review", data=b"repo=x&number=abc"))


def test_render_page_mine_buttons():
    page = server.render_page({False: PRS, True: PRS[:3]}, show_all=True)
    # one ready button for the draft, auto-merge for the other two of yours
    assert page.count('action="/ready"') == 1
    assert page.count('action="/automerge"') == 2
    assert page.count('action="/review"') == 7


def test_post_mine_actions(serve, monkeypatch):
    base, fetched, _, _ = serve
    calls = []
    monkeypatch.setattr(pr, "mark_ready", lambda *args: calls.append(("ready", *args)))
    monkeypatch.setattr(pr, "enable_auto_merge", lambda *args: calls.append(("auto", *args)))
    get(base + "/")
    data = urlencode({"repo": "acme/api", "number": "9", "all": "1"}).encode()
    page = get(urllib.request.Request(base + "/ready", data=data))
    assert "marked acme/api#9 ready for review" in page
    data = urlencode({"repo": "acme/api", "number": "7"}).encode()
    assert "enabled auto-merge on acme/api#7" in get(urllib.request.Request(base + "/automerge", data=data))
    assert calls == [("ready", "acme/api", 9), ("auto", "acme/api", 7)]
    # your PRs are refetched after each action
    assert fetched.count("mine") == 3
    # PRs that aren't yours are refused
    data = urlencode({"repo": "acme/api", "number": "5"}).encode()
    page = get(urllib.request.Request(base + "/automerge", data=data))
    assert "acme/api#5 is not one of your open PRs" in page
    assert len(calls) == 2


def test_post_mine_action_shows_errors(serve, monkeypatch):
    base, _, _, _ = serve

    def fail(*args):
        raise click.ClickException("auto-merge is not allowed")

    monkeypatch.setattr(pr, "enable_auto_merge", fail)
    get(base + "/")
    data = urlencode({"repo": "acme/api", "number": "7"}).encode()
    page = get(urllib.request.Request(base + "/automerge", data=data))
    assert "acme/api#7: auto-merge is not allowed" in page
