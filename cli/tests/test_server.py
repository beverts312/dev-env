import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from urllib.parse import urlencode

import click
from click.testing import CliRunner
import pytest

from be import config, jira
from be.commands import pr, server

PRS = [
    {"number": 7, "repo": "acme/api", "title": "Fix <login>", "checks": "pass", "approvals": 2, "draft": False, "author": "dev", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
    {"number": 1234, "repo": "acme/web-app", "title": "Add page", "checks": "fail", "approvals": 0, "draft": False, "author": "dev", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
    {"number": 9, "repo": "acme/api", "title": "WIP", "checks": "pass", "approvals": 0, "draft": True, "author": "dev", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
    {"number": 5, "repo": "acme/api", "title": "Bump", "checks": "pass", "approvals": 0, "draft": False, "author": "renovate", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
]


def test_render_page_starts_empty():
    page = server.render_page({})
    assert page.count(server.NOT_LOADED) == 4
    for table in ("review", "team", "mine", "jira"):
        assert f'href="/refresh?table={table}"' in page
    assert '<tr class="pr"' not in page



def test_render_page_tables_collapse():
    page = server.render_page({})
    # every table has a collapse button, remembered per table in the page
    assert page.count('class="collapse" aria-expanded="true"') == len(server.TABLES)
    assert "be.collapsed." in page

def test_render_page_marks_rows_for_filters():
    page = server.render_page({"review": PRS, "mine": []})
    # every row is rendered; the checkboxes hide them in the page
    assert page.count('<tr class="pr"') == 4
    # the search box matches the repo and title, lowercased, and the dropdowns each value
    assert '<tr class="pr" data-search="acme/api fix &lt;login&gt;" data-checks="pass" data-draft="no">' in page
    assert 'data-checks="fail" data-draft="no">' in page
    assert 'data-checks="pass" data-draft="yes">' in page
    assert page.count('type="search"') == 3
    assert 'data-hide="renovate"' in page
    # your PRs get no filter checkboxes, as none are by Renovate
    assert page.count('type="checkbox"') == 2 * len(server.PR_FILTERS) + len(server.ISSUE_FILTERS)
    assert 'name="renovate"' not in page.split('data-table="mine"')[1].split('data-table="jira"')[0]
    # dropdowns default to what pr ls shows
    assert page.count('<select name="checks" data-default="pass">') == 3
    assert page.count('<select name="draft" data-default="no">') == 3
    assert page.count('<option value="pass" selected>') == 3
    assert page.count('<option value="all">') == 6
    # their columns can be hidden, and the CSS hides them
    assert page.count('<th class="col-checks">CHECKS</th>') == 3
    assert ".hide-checks .col-checks { display: none; }" in page
    assert "no open PRs by you" in page
    # titles are escaped
    assert "Fix &lt;login&gt;" in page and "<login>" not in page
    # the draft column is always rendered; the page hides it while the dropdown picks one value
    assert page.count('<th class="col-draft">DRAFT</th>') == 3
    assert page.count('<td class="col-draft">yes</td>') == 1
    assert page.count('<td class="col-draft">no</td>') == 3


ISSUES = [
    {"key": "ACME-12", "type": "Bug", "summary": "Fix <login>"},
    {"key": "ACME-1", "type": "Feature", "summary": "Big thing"},
]


def test_render_page_tabs():
    page = server.render_page({})
    # my work holds your PRs and the issues, reviews the review requests
    work, reviews = page.split('<div class="tab-panel" data-tab="work">')[1].split(
        '<div class="tab-panel" data-tab="reviews">'
    )
    assert work.index('data-table="mine"') < work.index('data-table="jira"')
    assert 'data-table="review"' not in work and 'data-table="team"' not in work
    assert reviews.index('data-table="review"') < reviews.index('data-table="team"')
    assert 'data-table="mine"' not in reviews and 'data-table="jira"' not in reviews
    assert page.index('class="tab" data-tab="work"') < page.index('class="tab" data-tab="reviews"')


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
    monkeypatch.setattr(pr, "team_review_requests", lambda: fetched.append("team") or PRS[:2])
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
    assert page.count(server.NOT_LOADED) == 4
    page = get(base + "/refresh?table=review")
    assert fetched == ["review"]
    assert page.count('<tr class="pr"') == 4 and page.count(server.NOT_LOADED) == 3
    page = get(base + "/refresh?table=team")
    assert fetched == ["review", "team"]
    assert page.count('<tr class="pr"') == 6 and page.count(server.NOT_LOADED) == 2
    assert "<td>Add page</td>" in page.split('data-table="team"')[1].split("<section")[0]
    # loaded tables are kept
    get(base + "/")
    get(base + "/refresh?table=jira")
    assert fetched == ["review", "team", "jira"]
    get(base + "/refresh?table=review")
    assert fetched == ["review", "team", "jira", "review"]
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
    # only the review request tables have an author column
    assert page.count("<th>AUTHOR</th>") == 2
    mine_tab, reviews_tab = page.split('class="tab-panel" data-tab="reviews"')
    assert "<td>renovate</td>" in reviews_tab
    assert "<td>renovate</td>" not in mine_tab
    assert "<th>AUTHOR</th>" not in server.render_page({"mine": []}).split('data-table="mine"')[1].split("</section>")[0]


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


def test_requests_and_fetches_are_logged(serve, caplog):
    base, _, _, _ = serve
    caplog.set_level("INFO", logger="be")
    get(base + "/refresh?table=review")
    messages = [r.getMessage() for r in caplog.records]
    assert "fetched 4 rows for review" in messages
    assert any("GET /refresh?table=review" in m for m in messages)


def test_failed_fetch_is_logged_as_warning(monkeypatch, caplog):
    def fail(mine):
        raise click.ClickException("gh api graphql failed: boom")

    monkeypatch.setattr(pr, "fetch_prs", fail)
    assert server.fetch_table("mine") == "gh api graphql failed: boom"
    assert [(r.levelname, r.getMessage()) for r in caplog.records] == [
        ("WARNING", "fetching mine failed: gh api graphql failed: boom")
    ]


@pytest.mark.parametrize(
    "args, env, level",
    [([], {}, "WARNING"), (["--log-level", "DEBUG"], {}, "DEBUG"), ([], {"BE_SERVER_LOG_LEVEL": "info"}, "INFO")],
)
def test_log_level_option(monkeypatch, args, env, level):

    for key, value in env.items():
        monkeypatch.setenv(key, value)

    class Stopped(Exception):
        pass

    def stop(*a, **kw):
        raise Stopped

    monkeypatch.setattr(server, "HTTPServer", stop)
    logger = server.logging.getLogger("be")
    monkeypatch.setattr(logger, "level", logger.level)
    result = CliRunner().invoke(server.server, ["--no-open", *args])
    assert isinstance(result.exception, Stopped)
    assert server.logging.getLevelName(logger.level) == level


def test_log_level_rejects_unknown_levels():

    result = CliRunner().invoke(server.server, ["--no-open", "--log-level", "loud"])
    assert result.exit_code == 2 and "loud" in result.output


def test_render_page_links_config():
    assert '<a class="nav-link" href="/config">config</a>' in server.render_page({})


def test_render_config(isolated_config, monkeypatch):
    config.set_value("git.name", "<Me>")
    config.set_value("jira.token", "hunter2")
    config.set_value("jira.projects.ACME", "Acme")
    config.set_value("interactive", "yes")
    monkeypatch.setenv("WORK_ORG", "acme")
    page = server.render_config()
    assert page.count('<tr class="setting">') == len(config.SETTINGS)
    assert '<a class="nav-link" href="/">' in page
    assert str(isolated_config) in page
    # each setting is its own form, prefilled from the file and escaped
    assert 'name="value" form="cfg-3" aria-label="git.name" value="&lt;Me&gt;"' in page
    assert '<input type="hidden" name="key" value="git.name">' in page
    # every setting but the map can be unset, as can the map's one entry
    assert page.count('formaction="/config/unset"') == len(config.SETTINGS)
    # a default shows as the placeholder
    assert 'aria-label="claude.model" value="" placeholder="claude-opus-5-5"' in page
    # the env var's value wins, and says so
    assert "WORK_ORG overrides the file: acme" in page and "<td class=\"source\">env:WORK_ORG</td>" in page
    # the token is a password box with a show button
    assert 'type="password" name="value" form="cfg-13" aria-label="jira.token" value="hunter2"' in page
    assert 'class="reveal"' in page
    # dropdowns offer their choices and their default, plus a value the file has outside them
    assert '<option value="">(default: false)</option><option value="true">true</option>' in page
    assert '<option value="yes" selected>yes</option>' in page
    assert '<option value="warning">' in page
    # the map has a row per entry and one to add another
    assert '<td class="key">jira.projects.ACME</td>' in page and "1 entry in the file" in page
    assert '<input type="hidden" name="key" value="jira.projects.ACME">' in page
    assert 'name="name" form="cfg-14-new"' in page and ">add</button>" in page
    # settings given as flags say a save waits for a restart
    assert "--parent was given" in server.render_config(fixed=("pr.dir",))
    assert "was given" not in page


def test_render_config_masks_env_secret(monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "s3cret")
    page = server.render_config()
    assert "JIRA_API_TOKEN overrides the file: ********" in page and "s3cret" not in page


def test_render_config_invalid_file(isolated_config):
    isolated_config.parent.mkdir(parents=True)
    isolated_config.write_text("not = [toml")
    page = server.render_config()
    assert "invalid config file" in page and '<tr class="setting">' not in page


def post_config(base, action, **fields):
    return get(urllib.request.Request(f"{base}/config/{action}", data=urlencode(fields).encode()))


def test_post_config(serve):
    base, _, _, _ = serve
    page = post_config(base, "set", key="git.email", value=" me@example.com ")
    assert "saved git.email" in page and 'value="me@example.com"' in page
    assert config.file_value("git.email") == "me@example.com"
    assert "removed git.email" in post_config(base, "unset", key="git.email", value="me@example.com")
    assert config.file_value("git.email") is None
    # saving an empty value removes it too
    post_config(base, "set", key="git.name", value="Me")
    assert "removed git.name" in post_config(base, "set", key="git.name", value="")
    assert config.load_file() == {}


def test_post_config_map_entries(serve):
    base, _, _, _ = serve
    page = post_config(base, "set", key="jira.projects", name="OPS", value="Operations")
    assert "saved jira.projects.OPS" in page and '<td class="key">jira.projects.OPS</td>' in page
    post_config(base, "set", key="jira.projects.OPS", value="Ops")
    assert config.file_value("jira.projects") == {"OPS": "Ops"}
    assert "give the new entry a name" in post_config(base, "set", key="jira.projects", name="", value="x")
    assert "give the new entry a name" in post_config(base, "set", key="jira.projects", name="a.b", value="x")
    assert "removed jira.projects.OPS" in post_config(base, "unset", key="jira.projects.OPS")
    assert config.load_file() == {}


def test_post_config_errors(serve, monkeypatch):
    base, _, _, _ = serve
    assert "server.log_level must be one of debug, info, warning, error, not &#x27;loud&#x27;" in post_config(
        base, "set", key="server.log_level", value="loud"
    )
    assert "nope: unknown key" in post_config(base, "set", key="nope", value="x")
    monkeypatch.setenv("WORK_ORG", "acme")
    assert "saved work_org; WORK_ORG is set and overrides it" in post_config(base, "set", key="work_org", value="x")
    with pytest.raises(urllib.error.HTTPError):
        get(base + "/config/set")


@pytest.fixture
def serve_live(monkeypatch):
    """The server with no flags given, so pr.dir and server.log_level are reread."""
    reviews = []
    monkeypatch.setattr(pr, "open_review", lambda *args: reviews.append(args))
    logger = server.logging.getLogger("be")
    monkeypatch.setattr(logger, "level", logger.level)
    httpd = HTTPServer(("127.0.0.1", 0), server.make_handler(None, fixed=()))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", reviews, logger
    httpd.shutdown()
    httpd.server_close()


def test_config_applies_live(serve_live, tmp_path):
    base, reviews, logger = serve_live
    post_config(base, "set", key="pr.dir", value=str(tmp_path))
    get(urllib.request.Request(base + "/review", data=b"repo=acme/api&number=7"))
    assert reviews == [("acme/api", 7, str(tmp_path))]
    post_config(base, "set", key="server.log_level", value="debug")
    assert logger.level == server.logging.DEBUG
    post_config(base, "unset", key="server.log_level")
    assert logger.level == server.logging.WARNING


def test_flags_fix_settings(monkeypatch, tmp_path):
    class Stopped(Exception):
        pass

    def stop(*a, **kw):
        raise Stopped

    monkeypatch.setattr(server, "HTTPServer", stop)
    made = []
    real = server.make_handler
    monkeypatch.setattr(server, "make_handler", lambda parent, fixed: made.append(fixed) or real(parent, fixed))
    logger = server.logging.getLogger("be")
    monkeypatch.setattr(logger, "level", logger.level)
    CliRunner().invoke(server.server, ["--no-open"])
    CliRunner().invoke(server.server, ["--no-open", "--parent", str(tmp_path)], env={"BE_SERVER_LOG_LEVEL": "info"})
    # only flags fix a setting; an env var or the file is reread when used
    assert made == [(), ("pr.dir",)]
