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
    {"number": 7, "repo": "acme/api", "title": "Fix <login>", "checks": "pass", "approvals": 2, "draft": False, "author": "dev", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
    {"number": 1234, "repo": "acme/web-app", "title": "Add page", "checks": "fail", "approvals": 0, "draft": False, "author": "dev", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
    {"number": 9, "repo": "acme/api", "title": "WIP", "checks": "pass", "approvals": 0, "draft": True, "author": "dev", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
    {"number": 5, "repo": "acme/api", "title": "Bump", "checks": "pass", "approvals": 0, "draft": False, "author": "renovate", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
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
    # the search box matches the repo and title, lowercased, and the dropdowns each value
    assert '<tr class="pr" data-search="acme/api fix &lt;login&gt;" data-checks="pass" data-draft="no">' in page
    assert 'data-checks="fail" data-draft="no">' in page
    assert 'data-checks="pass" data-draft="yes">' in page
    assert page.count('type="search"') == 2
    assert 'data-hide="renovate"' in page
    assert page.count('type="checkbox"') == 2 * len(server.PR_FILTERS) + len(server.ISSUE_FILTERS)
    # dropdowns default to what pr ls shows
    assert page.count('<select name="checks" data-default="pass">') == 2
    assert page.count('<select name="draft" data-default="no">') == 2
    assert page.count('<option value="pass" selected>') == 2
    assert page.count('<option value="all">') == 4
    # their columns can be hidden, and the CSS hides them
    assert page.count('<th class="col-checks">CHECKS</th>') == 2
    assert ".hide-checks .col-checks { display: none; }" in page
    assert "no open PRs by you" in page
    # titles are escaped
    assert "Fix &lt;login&gt;" in page and "<login>" not in page
    # the draft column is always rendered; the page hides it while the dropdown picks one value
    assert page.count('<th class="col-draft">DRAFT</th>') == 2
    assert page.count('<td class="col-draft">yes</td>') == 1
    assert page.count('<td class="col-draft">no</td>') == 3


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
    assert 'action="/merge"' not in page


def test_render_page_mine_merge_and_author():
    mine = [
        {**PRS[0], "approved": True},
        {**PRS[1], "approved": True, "auto_merge": True},
        {**PRS[3], "auto_merge": True},
    ]
    page = server.render_page({"review": PRS, "mine": mine})
    # approved gets merge alongside auto-merge; nothing once auto-merge is on
    assert page.count('action="/merge"') == 1
    assert page.count('action="/automerge"') == 1
    assert 'value="7"><button>merge</button>' in page
    # only the review requests table has an author column
    assert page.count("<th>AUTHOR</th>") == 1
    assert "<td>renovate</td>" in page.split('data-table="mine"')[0]
    assert "<td>renovate</td>" not in page.split('data-table="mine"')[1]
    assert "<th>AUTHOR</th>" not in server.render_page({"mine": []}).split('data-table="mine"')[1]


def test_post_merge(serve, monkeypatch):
    base, _, _, _ = serve
    calls = []
    monkeypatch.setattr(pr, "merge", lambda *args: calls.append(args))
    monkeypatch.setattr(pr, "enable_auto_merge", lambda *args: calls.append(("auto", *args)))
    data = urlencode({"repo": "acme/api", "number": "7"}).encode()
    page = get(urllib.request.Request(base + "/merge", data=data))
    assert "acme/api#7 is not approved" in page and calls == []
    # auto-merge hides the PR's buttons but keeps the row
    page = get(urllib.request.Request(base + "/automerge", data=data))
    assert 'value="7"><button>auto-merge</button>' not in page
    assert page.count('<tr class="pr"') == 3


def test_post_merge_removes_row(serve, monkeypatch):
    base, _, _, _ = serve
    monkeypatch.setattr(pr, "authored_prs", lambda: [{**PRS[0], "approved": True}])
    calls = []
    monkeypatch.setattr(pr, "merge", lambda *args: calls.append(args))
    page = get(base + "/refresh?table=mine")
    assert 'value="7"><button>merge</button>' in page
    data = urlencode({"repo": "acme/api", "number": "7"}).encode()
    page = get(urllib.request.Request(base + "/merge", data=data))
    assert "merged acme/api#7" in page and calls == [("acme/api", 7, "--squash")]
    assert "no open PRs by you" in page


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
    assert calls == [("ready", "acme/api", 9), ("auto", "acme/api", 7, "--squash")]
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


def test_render_page_bulk_bar():
    page = server.render_page({"review": PRS, "mine": PRS[:3]})
    review, mine = page.split('data-table="mine"')
    # only your PRs get checkboxes and the bulk bar
    assert 'class="pick"' not in review and "form.bulk" not in review.split("<script>")[0]
    assert mine.count('class="pick"') == 3
    assert 'value="acme/api#9" form="bulk-mine"' in mine
    assert '<form id="bulk-mine" class="bulk" method="post" action="/bulk">' in mine
    for action in server.MINE_BUTTONS:
        assert f'name="action" value="{action}"' in mine
    # each row says which bulk actions apply to it
    assert 'data-draft="yes" data-actions="ready"' in mine
    assert 'data-draft="no" data-actions="automerge"' in mine
    assert 'class="pick"' not in server.render_page({"mine": []})


def post_bulk(base, action, *prs):
    data = urlencode([("action", action), *(("pr", p) for p in prs)]).encode()
    return get(urllib.request.Request(base + "/bulk", data=data))


def test_post_bulk(serve, monkeypatch):
    base, fetched, _, _ = serve
    calls = []
    monkeypatch.setattr(pr, "mark_ready", lambda *args: calls.append(("ready", *args)))
    monkeypatch.setattr(pr, "enable_auto_merge", lambda *args: calls.append(("auto", *args)))
    page = post_bulk(base, "automerge", "acme/api#7", "acme/web-app#1234", "acme/api#9", "acme/api#5")
    # the draft is skipped, and PRs that aren't yours are refused
    assert calls == [("auto", "acme/api", 7, "--squash"), ("auto", "acme/web-app", 1234, "--squash")]
    assert "enabled auto-merge on acme/api#7; enabled auto-merge on acme/web-app#1234" in page
    assert "skipped acme/api#9: no auto-merge on it" in page
    assert "acme/api#5 is not one of your open PRs" in page
    assert fetched == ["mine"]
    page = post_bulk(base, "ready", "acme/api#9")
    assert calls[-1] == ("ready", "acme/api", 9)
    assert 'data-draft="no" data-actions="automerge"' in page


def test_post_bulk_merge_keeps_going(serve, monkeypatch):
    base, _, _, _ = serve
    monkeypatch.setattr(
        pr, "authored_prs", lambda: [{**PRS[0], "approved": True}, {**PRS[1], "approved": True}]
    )
    merged = []

    def merge(repo, number, flag):
        if number == 7:
            raise click.ClickException("not mergeable")
        merged.append(number)

    monkeypatch.setattr(pr, "merge", merge)
    page = post_bulk(base, "merge", "acme/api#7", "acme/web-app#1234")
    assert merged == [1234]
    assert "acme/api#7: not mergeable; merged acme/web-app#1234" in page
    # the merged PR is dropped, the failed one stays
    assert page.count('<tr class="pr"') == 1


def test_post_bulk_bad_input(serve):
    base, _, _, _ = serve
    assert "no PRs selected" in post_bulk(base, "ready")
    for action, prs in (("nope", ["acme/api#7"]), ("ready", ["acme/api#x"]), ("ready", ["#7"])):
        with pytest.raises(urllib.error.HTTPError):
            post_bulk(base, action, *prs)
