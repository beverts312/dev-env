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
    {"number": 7, "repo": "acme/api", "title": "Fix <login>", "checks": "pass", "approvals": 2, "draft": False, "author": "dev"},
    {"number": 1234, "repo": "acme/web-app", "title": "Add page", "checks": "fail", "approvals": 0, "draft": False, "author": "dev"},
    {"number": 9, "repo": "acme/api", "title": "WIP", "checks": "pass", "approvals": 0, "draft": True, "author": "dev"},
    {"number": 5, "repo": "acme/api", "title": "Bump", "checks": "pass", "approvals": 0, "draft": False, "author": "renovate"},
]


def test_render_page_starts_empty():
    page = server.render_page({})
    assert page.count(server.NOT_LOADED) == 3
    for table in ("review", "mine", "jira"):
        assert f'href="/refresh?table={table}"' in page
    assert '<tr class="pr"' not in page


def test_render_page_marks_rows_for_filters():
    page = server.render_page({"review": PRS, "mine": []})
    # every row is rendered; the checkboxes hide them in the page
    assert page.count('<tr class="pr"') == 4
    # #7 passes every filter, and the search box matches its repo and title, lowercased
    assert '<tr class="pr" data-search="acme/api fix &lt;login&gt;">' in page
    assert page.count('type="search"') == 2
    assert 'data-hide="checks"' in page
    assert 'data-hide="draft"' in page
    assert 'data-hide="renovate"' in page
    assert page.count('type="checkbox"') == 2 * len(server.PR_FILTERS) + len(server.ISSUE_FILTERS)
    assert "no open PRs by you" in page
    # titles are escaped
    assert "Fix &lt;login&gt;" in page and "<login>" not in page
    # the draft column is always rendered; the page hides it while "not drafts" is checked
    assert '<th class="draft-col">DRAFT</th>' in page
    assert page.count('<td class="draft-col">yes</td>') == 1
    assert page.count('<td class="draft-col">no</td>') == 3
    assert 'toggle("no-drafts"' in page


ISSUES = [
    {"key": "ACME-12", "type": "Bug", "summary": "Fix <login>"},
    {"key": "ACME-1", "type": "Feature", "summary": "Big thing"},
]


def test_render_page_issues(isolated_config, monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://x.atlassian.net")
    page = server.render_page({"jira": ISSUES})
    assert 'href="https://x.atlassian.net/browse/ACME-12"' in page
    assert "Fix &lt;login&gt;" in page
    assert page.count('<tr class="issue"') == 2
    assert '<tr class="issue" data-hide="feature">' in page
    page = server.render_page({"jira": "jira.url must be set"})
    assert "jira: jira.url must be set" in page


def test_render_page_message():
    page = server.render_page({"mine": PRS}, message="opened x#1")
    assert "no review requests" not in page and server.NOT_LOADED in page
    assert "opened x#1" in page


@pytest.fixture
def serve(monkeypatch, tmp_path):
    fetched = []
    monkeypatch.setattr(pr, "review_requests", lambda: fetched.append("review") or PRS)
    monkeypatch.setattr(pr, "authored_prs", lambda: fetched.append("mine") or [dict(p) for p in PRS[:3]])
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


def test_get_loads_only_refreshed_tables(serve):
    base, fetched, _, _ = serve
    page = get(base + "/")
    assert fetched == []
    assert page.count(server.NOT_LOADED) == 3
    page = get(base + "/refresh?table=review")
    assert fetched == ["review"]
    assert page.count('<tr class="pr"') == 4 and page.count(server.NOT_LOADED) == 2
    # loaded tables are kept
    get(base + "/")
    get(base + "/refresh?table=jira")
    assert fetched == ["review", "jira"]
    get(base + "/refresh?table=review")
    assert fetched == ["review", "jira", "review"]
    with pytest.raises(urllib.error.HTTPError):
        get(base + "/refresh?table=nope")


def test_get_shows_fetch_errors(serve, monkeypatch):
    base, _, _, _ = serve

    def fail():
        raise jira.JiraError("HTTP 401 from x")

    def gh_fail():
        raise click.ClickException("gh not found")

    monkeypatch.setattr(jira, "in_progress_issues", fail)
    monkeypatch.setattr(pr, "authored_prs", gh_fail)
    get(base + "/refresh?table=jira")
    page = get(base + "/refresh?table=mine")
    assert "jira: HTTP 401 from x" in page and "github: gh not found" in page


def test_post_review_opens_and_redirects(serve):
    base, _, reviews, parent = serve
    get(base + "/refresh?table=review")
    data = urlencode({"repo": "acme/api", "number": "7"}).encode()
    page = get(urllib.request.Request(base + "/review", data=data))
    assert reviews == [("acme/api", 7, parent)]
    assert "opened acme/api#7" in page
    assert page.count('<tr class="pr"') == 4


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
    page = server.render_page({"review": PRS, "mine": PRS[:3]})
    # one ready button for the draft, auto-merge for the other two of yours
    assert page.count('action="/ready"') == 1
    assert page.count('action="/automerge"') == 2
    assert page.count('action="/review"') == 7


def test_post_mine_actions(serve, monkeypatch):
    base, fetched, _, _ = serve
    calls = []
    monkeypatch.setattr(pr, "mark_ready", lambda *args: calls.append(("ready", *args)))
    monkeypatch.setattr(pr, "enable_auto_merge", lambda *args: calls.append(("auto", *args)))
    data = urlencode({"repo": "acme/api", "number": "9"}).encode()
    page = get(urllib.request.Request(base + "/ready", data=data))
    assert "marked acme/api#9 ready for review" in page
    data = urlencode({"repo": "acme/api", "number": "7"}).encode()
    page = get(urllib.request.Request(base + "/automerge", data=data))
    assert "enabled auto-merge on acme/api#7" in page
    assert calls == [("ready", "acme/api", 9), ("auto", "acme/api", 7)]
    # your PRs are fetched once if needed, then updated in place
    assert fetched == ["mine"]
    # the PR marked ready now offers auto-merge
    assert 'value="9"><button>auto-merge</button>' in page
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
