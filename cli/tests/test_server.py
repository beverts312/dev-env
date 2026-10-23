import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from urllib.parse import urlencode

import click
import pytest

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
    monkeypatch.setattr(pr, "authored_prs", lambda: fetched.append("mine") or PRS[:1])
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
    assert get(base + "/?all=1").count('<tr class="pr">') == 5
    assert fetched == ["review", "mine"]
    get(base + "/refresh")
    assert fetched == ["review", "mine", "review", "mine"]


def test_post_review_opens_and_redirects(serve):
    base, _, reviews, parent = serve
    data = urlencode({"repo": "acme/api", "number": "7", "all": "1"}).encode()
    page = get(urllib.request.Request(base + "/review", data=data))
    assert reviews == [("acme/api", 7, parent)]
    assert "opened acme/api#7" in page
    assert page.count('<tr class="pr">') == 5


def test_post_review_shows_errors(serve, monkeypatch):
    base, _, _, _ = serve

    def fail(*args):
        raise click.ClickException("clone failed")

    monkeypatch.setattr(pr, "open_review", fail)
    data = urlencode({"repo": "acme/api", "number": "7"}).encode()
    assert "acme/api#7: clone failed" in get(urllib.request.Request(base + "/review", data=data))
    with pytest.raises(urllib.error.HTTPError):
        get(urllib.request.Request(base + "/review", data=b"repo=x&number=abc"))
