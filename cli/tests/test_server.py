import os
import re
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from urllib.parse import urlencode

import click
from click.testing import CliRunner
import pytest

from be import config, jira
from be.commands import pr, server, ws
from be.commands.page import (
    MINE_BUTTONS,
    NOT_LOADED,
    PR_FILTERS,
    TABLES,
    render_config,
    render_page,
)

PRS = [
    {"number": 7, "repo": "acme/api", "title": "Fix <login>", "checks": "pass", "approvals": 2, "draft": False, "author": "dev", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
    {"number": 1234, "repo": "acme/web-app", "title": "Add page", "checks": "fail", "approvals": 0, "draft": False, "author": "dev", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
    {"number": 9, "repo": "acme/api", "title": "WIP", "checks": "pass", "approvals": 0, "draft": True, "author": "dev", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
    {"number": 5, "repo": "acme/api", "title": "Bump", "checks": "pass", "approvals": 0, "draft": False, "author": "renovate", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
]


def test_render_page_starts_empty():
    page = render_page({})
    assert page.count(NOT_LOADED) == len(TABLES)
    for table, _ in TABLES:
        assert f'href="/refresh?table={table}"' in page
    assert '<tr class="pr"' not in page



def test_render_page_tables_collapse():
    page = render_page({})
    # every table has a collapse button, remembered per table in the page
    assert page.count('class="collapse" aria-expanded="true"') == len(TABLES)
    assert "be.collapsed." in page

def test_render_page_marks_rows_for_filters():
    page = render_page({"review": PRS, "mine": []})
    # every row is rendered; the checkboxes hide them in the page
    assert page.count('<tr class="pr"') == 4
    # the search box matches the repo and title, lowercased, and the dropdowns each value
    assert '<tr class="pr" data-search="acme/api fix &lt;login&gt;" data-checks="pass" data-draft="no">' in page
    assert 'data-checks="fail" data-draft="no">' in page
    assert 'data-checks="pass" data-draft="yes">' in page
    assert page.count('type="search"') == 3
    assert 'data-hide="renovate"' in page
    # your PRs get no filter checkboxes, as none are by Renovate
    assert page.count('type="checkbox"') == 2 * len(PR_FILTERS)
    assert 'name="renovate"' not in page.split('data-table="mine"')[1].split("</section>")[0]
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


def node(key, type, summary, mine=True, category="indeterminate", parent="", parent_type="", children=()):
    status = {"new": "To Do", "indeterminate": "In Progress"}[category]
    return {
        "key": key, "type": type, "summary": summary, "status": status, "category": category,
        "assignee": "Me" if mine else "Pat", "parent": parent, "parent_type": parent_type,
        "parent_summary": "Big thing" if parent_type else "", "mine": mine, "children": list(children),
    }


ISSUES = [
    node("ACME-1", "Feature", "Big thing", parent="ACME-0", children=[
        node("ACME-12", "Bug", "Fix <login>", parent="ACME-1", parent_type="Feature"),
        node("ACME-13", "Story", "Theirs", mine=False, category="new", parent="ACME-1"),
    ]),
    node("ACME-20", "Story", "Later", category="new"),
]


def panel(page, tab):
    """The HTML of one page's panel."""
    return page.split(f'<div class="tab-panel" data-tab="{tab}">')[1].split('<div class="tab-panel"')[0]


def test_render_page_tabs():
    page = render_page({})
    # my work holds just the issues; your PRs, the review requests, and workspaces each get a page
    tables = {tab: re.findall(r'data-table="(\w+)"', panel(page, tab)) for tab in ("work", "prs", "reviews", "workspaces")}
    assert tables == {"work": ["jira"], "prs": ["mine"], "reviews": ["review", "team"], "workspaces": ["workspaces"]}
    navs = re.findall(r'class="nav" data-tab="(\w+)"', page)
    assert navs == ["work", "prs", "reviews", "workspaces"]
    # the pages live in a sidebar the header button collapses, remembered by the browser
    assert '<nav class="sidebar" aria-label="pages">' in page
    assert 'aria-label="collapse sidebar"' in page and "be.sidebar" in page
    assert 'class="tabs"' not in page and 'class="tab"' not in page


def test_render_page_agent_toggle():
    page = render_page({"review": PRS[:1], "mine": PRS[:1]})
    reviews = panel(page, "reviews")
    # the switch sits above the review tables, and starts on claude
    assert reviews.index('class="agent"') < reviews.index('data-table="review"')
    assert 'class="agent"' not in panel(page, "prs")
    assert 'role="radio" data-agent="claude" aria-checked="true"' in reviews
    assert 'role="radio" data-agent="cursor" aria-checked="false"' in reviews
    # both tabs' review buttons post that choice; the page can remember another
    assert page.count('name="agent" value="claude"') == 2
    assert "be.agent" in page
    page = render_page({"review": PRS[:1]}, agent="Cursor")
    reviews = page.split('<div class="tab-panel" data-tab="reviews">')[1]
    assert 'role="radio" data-agent="cursor" aria-checked="true"' in reviews
    assert 'name="agent" value="cursor"' in reviews
    assert 'name="agent" value="claude"' not in page


def test_render_page_workspaces():
    rows = [{
        "dir": "acme-12",
        "name": "acme-12",
        "description": "Fix <login>",
        "repos": ["api", "web"],
        "extra_dirs": ["/tmp/notes"],
        "issue_name": "Fix login",
    }]
    page = render_page({"workspaces": rows})
    table = panel(page, "workspaces").split('data-table="workspaces"')[1].split("</section>")[0]
    assert "<td>acme-12</td>" in table
    assert "<td>Fix login</td>" in table
    assert "<td>Fix &lt;login&gt;</td>" in table
    assert "<td>api, web</td>" in table
    assert "<td>/tmp/notes</td>" in table
    assert 'action="/open"' in table and 'name="name" value="acme-12"' in table
    assert 'querySelectorAll("tr.ws")' in page and "tr.ws { cursor: pointer; }" in page
    assert 'class="filters"' not in table
    assert "no workspaces" in render_page({"workspaces": []})
    assert "workspaces: ws.dir must be set" in render_page({"workspaces": "ws.dir must be set"})


def test_render_page_issues(isolated_config, monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://x.atlassian.net")
    page = render_page({"jira": ISSUES})
    assert 'href="https://x.atlassian.net/browse/ACME-12"' in page
    assert "Fix &lt;login&gt;" in page
    # a tree, not a table: children nest under their parent
    tree = page.split('data-table="jira"')[1].split("</section>")[0]
    assert '<ul class="tree">' in tree and "<table>" not in tree
    assert tree.count('<li class="issue') == 4
    assert '<li class="issue" data-key="ACME-1" data-project="ACME" data-status="In Progress" data-summary="Big thing">' in tree and '<details class="multi" data-key="project">' in tree
    feature = tree.split('data-key="ACME-1" data-project="ACME" data-status="In Progress" data-summary="Big thing">')[1]
    assert feature.index("ACME-1<") < feature.index("<ul>") < feature.index("ACME-12") < feature.index("ACME-20")
    assert feature.index("</ul>") < feature.index("ACME-20")
    # someone else's child names its assignee; a top-level issue names its parent
    assert '<li class="issue other" data-key="ACME-13"' in tree and '<span class="assignee">Pat</span>' in tree
    # only an issue with children gets a collapse toggle
    assert tree.count('<button type="button" class="twist"') == 1
    assert 'aria-label="collapse ACME-1"' in tree
    assert '<span class="assignee">in ACME-0</span>' in tree
    assert '<span class="status cat-new">To Do</span>' in tree
    assert "no open issues assigned to you" in render_page({"jira": []})
    page = render_page({"jira": "jira.url must be set"})
    assert "jira: jira.url must be set" in page


def test_render_page_issue_projects(isolated_config, monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://x.atlassian.net")
    config.set_value("jira.projects.OPS", "Operations")
    issues = [*ISSUES, node("OPS-3", "Task", "Ops thing", children=[node("ACME-30", "Bug", "Nested", parent="OPS-3")])]
    tree = render_page({"jira": issues}).split('data-table="jira"')[1].split("</section>")[0]
    # one checkbox per project in the tree, described as jira.projects has it
    picker = tree.split('<details class="multi" data-key="project">')[1].split("</details>")[0]
    assert picker.count('type="checkbox"') == 2
    assert picker.index('value="ACME"') < picker.index('value="OPS"')
    assert '<span class="multi-note">Operations</span>' in picker
    assert 'data-key="ACME-30" data-project="ACME" data-status="In Progress"' in tree
    assert 'data-key="OPS-3" data-project="OPS"' in tree
    # and one per status, To Do before In Progress
    statuses = tree.split('<details class="multi" data-key="status">')[1].split("</details>")[0]
    assert statuses.count('type="checkbox"') == 2
    assert statuses.index('value="To Do"') < statuses.index('value="In Progress"')
    # the dropdown is only shown once there are issues
    assert "details class=\"multi" not in render_page({"jira": []})


def test_render_page_issue_workspaces(isolated_config, monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://x.atlassian.net")
    page = render_page({"jira": ISSUES, "workspaces": [{"dir": "acme-20"}]})
    tree = page.split('data-table="jira"')[1].split("</section>")[0]
    # a workspace is found by key, ignoring case, and a double click opens it
    assert 'data-key="ACME-20" data-project="ACME" data-status="To Do" data-workspace="acme-20">' in tree
    assert tree.count('class="ws-badge"') == 1
    # without one, a double click offers to create one, for the issue or its Feature parent
    assert 'data-key="ACME-12" data-project="ACME" data-status="In Progress" data-summary="Fix &lt;login&gt;" data-parent="ACME-1" data-parent-type="Feature"' in tree
    assert 'data-key="ACME-13" data-project="ACME" data-status="To Do" data-summary="Theirs">' in tree
    assert '<dialog class="ws-create"' in tree and 'action="/ws/create"' in tree
    assert 'addEventListener("dblclick"' in page
    # existing workspaces can be linked instead, and a linked issue opens its workspace
    assert '<option value="acme-20">acme-20</option>' in tree and '<div class="ws-mode"' in tree
    page = render_page({"jira": ISSUES, "workspaces": [{"dir": "login", "issues": ["acme-13"]}]})
    assert 'data-key="ACME-13" data-project="ACME" data-status="To Do" data-workspace="login">' in page
    # with no workspaces there's nothing to link
    assert ' aria-label="new or existing workspace" hidden>' in render_page({"jira": ISSUES, "workspaces": []})


def test_render_page_message():
    page = render_page({"mine": PRS}, message="opened x#1")
    assert "no review requests" not in page and NOT_LOADED in page
    assert "opened x#1" in page


@pytest.fixture
def serve(monkeypatch, tmp_path):
    fetched = []
    monkeypatch.setattr(pr, "review_requests", lambda: fetched.append("review") or PRS)
    monkeypatch.setattr(pr, "team_review_requests", lambda: fetched.append("team") or PRS[:2])
    monkeypatch.setattr(pr, "authored_prs", lambda: fetched.append("mine") or [dict(p) for p in PRS[:3]])
    monkeypatch.setattr(jira, "issue_tree", lambda: fetched.append("jira") or [])
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
    # the jira tree and workspaces load with the page; the PR tables wait for refresh
    assert fetched == ["jira"]
    assert page.count(NOT_LOADED) == len(TABLES) - 2
    assert "ws.dir" in page.split('data-table="workspaces"')[1].split("</section>")[0]
    page = get(base + "/refresh?table=review")
    assert fetched == ["jira", "review"]
    assert page.count('<tr class="pr"') == 4 and page.count(NOT_LOADED) == len(TABLES) - 3
    page = get(base + "/refresh?table=team")
    assert fetched == ["jira", "review", "team"]
    assert page.count('<tr class="pr"') == 6 and page.count(NOT_LOADED) == len(TABLES) - 4
    assert "<td>Add page</td>" in page.split('data-table="team"')[1].split("<section")[0]
    # loaded tables are kept, the tree too; its refresh link fetches it again
    get(base + "/")
    get(base + "/refresh?table=jira")
    assert fetched == ["jira", "review", "team", "jira"]
    get(base + "/refresh?table=review")
    assert fetched == ["jira", "review", "team", "jira", "review"]
    with pytest.raises(urllib.error.HTTPError):
        get(base + "/refresh?table=nope")


def test_get_shows_fetch_errors(serve, monkeypatch):
    base, _, _, _ = serve

    def fail():
        raise jira.JiraError("HTTP 401 from x")

    def gh_fail():
        raise click.ClickException("gh not found")

    monkeypatch.setattr(jira, "issue_tree", fail)
    monkeypatch.setattr(pr, "authored_prs", gh_fail)
    get(base + "/refresh?table=jira")
    page = get(base + "/refresh?table=mine")
    assert "jira: HTTP 401 from x" in page and "github: gh not found" in page


def test_workspaces_refresh_and_open(serve, tmp_path, monkeypatch):
    spaces = tmp_path / "spaces"
    root = spaces / "proj"
    (root / "api" / ".git").mkdir(parents=True)
    (root / "workspace.yml").write_text(
        "name: proj\ndescription: the work\nissue_name: Fix login\nextra_dirs:\n- /tmp/notes\n"
    )
    config.set_value("ws.dir", str(spaces))
    opened = []
    monkeypatch.setattr(ws, "open_root", lambda root, model=None, window=None: opened.append((root, model, window)))
    base = serve[0]
    page = get(base + "/")
    assert "<td>proj</td>" in page and "<td>the work</td>" in page
    page = get(base + "/refresh?table=workspaces")
    assert "<td>proj</td>" in page and "<td>Fix login</td>" in page
    assert "<td>the work</td>" in page and "<td>api</td>" in page and "<td>/tmp/notes</td>" in page
    page = get(urllib.request.Request(base + "/open", data=urlencode({"name": "proj"}).encode()))
    assert opened == [(root.resolve(), None, None)]
    assert "opened proj" in page
    page = get(urllib.request.Request(base + "/open", data=urlencode({"name": "missing"}).encode()))
    assert "missing is not a workspace" in page and len(opened) == 1
    with pytest.raises(urllib.error.HTTPError) as err:
        get(urllib.request.Request(base + "/open", data=urlencode({"name": "../nope"}).encode()))
    assert err.value.code == 400


def test_create_workspace(serve, tmp_path, monkeypatch):
    spaces = tmp_path / "spaces"
    (spaces / "taken").mkdir(parents=True)
    config.set_value("ws.dir", str(spaces))
    created = []

    def create(*args):
        os.chdir(spaces)
        created.append(args)

    monkeypatch.setattr(ws, "create_workspace", create)
    base, cwd = serve[0], os.getcwd()
    form = {"name": "ACME-12", "repos": "api, web", "extra_dirs": "", "description": "d", "issue_name": "Fix login"}
    page = get(urllib.request.Request(base + "/ws/create", data=urlencode(form).encode()))
    assert "created ACME-12" in page
    assert created == [("ACME-12", "api, web", "", "d", str(spaces), "claude-opus-5-5", None, None, "Fix login")]
    # the server stays where it was
    assert os.getcwd() == cwd
    page = get(urllib.request.Request(base + "/ws/create", data=urlencode({**form, "name": "taken"}).encode()))
    assert "taken already exists" in page and len(created) == 1
    with pytest.raises(urllib.error.HTTPError) as err:
        get(urllib.request.Request(base + "/ws/create", data=urlencode({**form, "name": "../x"}).encode()))
    assert err.value.code == 400


def test_link_workspace(serve, tmp_path, monkeypatch):
    spaces = tmp_path / "spaces"
    (spaces / "proj").mkdir(parents=True)
    config.set_value("ws.dir", str(spaces))
    opened = []
    monkeypatch.setattr(ws, "open_root", lambda root, model=None, window=None: opened.append(root))
    base = serve[0]
    page = get(urllib.request.Request(base + "/ws/link", data=urlencode({"name": "proj", "key": "acme-12"}).encode()))
    assert "linked ACME-12 to proj; opened proj" in page
    assert ws.read_manifest(spaces / "proj")["issues"] == ["ACME-12"]
    assert opened == [(spaces / "proj").resolve()]
    # the workspaces table now knows the link, so the tree opens it
    monkeypatch.setenv("JIRA_URL", "https://x.atlassian.net")
    monkeypatch.setattr(jira, "issue_tree", lambda: ISSUES)
    page = get(base + "/refresh?table=jira")
    assert 'data-key="ACME-12" data-project="ACME" data-status="In Progress" data-workspace="proj">' in page
    page = get(urllib.request.Request(base + "/ws/link", data=urlencode({"name": "nope", "key": "ACME-12"}).encode()))
    assert "nope is not a workspace" in page
    for bad in ({"name": "proj", "key": "not a key"}, {"name": "../x", "key": "ACME-1"}):
        with pytest.raises(urllib.error.HTTPError) as err:
            get(urllib.request.Request(base + "/ws/link", data=urlencode(bad).encode()))
        assert err.value.code == 400


def test_workspaces_refresh_without_dir(serve):
    page = get(serve[0] + "/refresh?table=workspaces")
    assert "workspaces:" in page and "ws.dir" in page


def test_post_review_opens_and_redirects(serve):
    base, _, reviews, parent = serve
    get(base + "/refresh?table=review")
    data = urlencode({"repo": "acme/api", "number": "7"}).encode()
    page = get(urllib.request.Request(base + "/review", data=data))
    assert reviews == [("acme/api", 7, parent, "claude", None, None)]
    assert "opened acme/api#7" in page
    assert page.count('<tr class="pr"') == 4


def test_post_review_uses_posted_agent(serve):
    base, _, reviews, parent = serve
    data = urlencode({"repo": "acme/api", "number": "7", "agent": "cursor"}).encode()
    get(urllib.request.Request(base + "/review", data=data))
    assert reviews == [("acme/api", 7, parent, "cursor", None, None)]
    data = urlencode({"repo": "acme/api", "number": "8", "agent": "Claude"}).encode()
    get(urllib.request.Request(base + "/review", data=data))
    assert reviews[-1][3] == "claude"
    # an unknown agent falls back to the configured one
    data = urlencode({"repo": "acme/api", "number": "9", "agent": "nope"}).encode()
    get(urllib.request.Request(base + "/review", data=data))
    assert reviews[-1][3] == "claude"


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
    page = render_page({"review": PRS, "mine": PRS[:3]})
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
    page = render_page({"review": PRS, "mine": mine})
    # approved gets merge alongside auto-merge; nothing once auto-merge is on
    assert page.count('action="/merge"') == 1
    assert page.count('action="/automerge"') == 1
    assert 'value="7"><button>merge</button>' in page
    # only the review request tables have an author column
    assert page.count("<th>AUTHOR</th>") == 2
    mine_tab, reviews_tab = panel(page, "prs"), panel(page, "reviews")
    assert "<td>renovate</td>" in reviews_tab
    assert "<td>renovate</td>" not in mine_tab
    assert "<th>AUTHOR</th>" not in render_page({"mine": []}).split('data-table="mine"')[1].split("</section>")[0]


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
    assert fetched == ["mine", "jira"]  # the tree loads with the first page
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
    page = render_page({"review": PRS, "mine": PRS[:3]})
    review, mine = page.split('data-table="mine"')
    # only your PRs get checkboxes and the bulk bar
    assert 'class="pick"' not in review and "form.bulk" not in review.split("<script>")[0]
    assert mine.count('class="pick"') == 3
    assert 'value="acme/api#9" form="bulk-mine"' in mine
    assert '<form id="bulk-mine" class="bulk" method="post" action="/bulk">' in mine
    for action in MINE_BUTTONS:
        assert f'name="action" value="{action}"' in mine
    # each row says which bulk actions apply to it
    assert 'data-draft="yes" data-actions="ready"' in mine
    assert 'data-draft="no" data-actions="automerge"' in mine
    assert 'class="pick"' not in render_page({"mine": []})


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
    assert fetched == ["mine", "jira"]  # the tree loads with the first page
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
    assert '<a class="nav-link" href="/config">config</a>' in render_page({})


def test_render_config(isolated_config, monkeypatch):
    config.set_value("git.name", "<Me>")
    config.set_value("jira.token", "hunter2")
    config.set_value("jira.projects.ACME", "Acme")
    config.set_value("interactive", "yes")
    monkeypatch.setenv("WORK_ORG", "acme")
    page = render_config()
    assert page.count('<tr class="setting">') == len(config.SETTINGS)
    assert '<a class="nav-link" href="/">' in page
    assert 'class="sidebar"' not in page
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
    token = list(config.SETTINGS).index("jira.token")
    assert f'type="password" name="value" form="cfg-{token}" aria-label="jira.token" value="hunter2"' in page
    assert 'class="reveal"' in page
    # dropdowns offer their choices and their default, plus a value the file has outside them
    assert '<option value="">(default: false)</option><option value="true">true</option>' in page
    assert '<option value="yes" selected>yes</option>' in page
    assert '<option value="warning">' in page
    # the map has a row per entry and one to add another
    assert '<td class="key">jira.projects.ACME</td>' in page and "1 entry in the file" in page
    assert '<input type="hidden" name="key" value="jira.projects.ACME">' in page
    projects = list(config.SETTINGS).index("jira.projects")
    assert f'name="name" form="cfg-{projects}-new"' in page and ">add</button>" in page
    # settings given as flags say a save waits for a restart; pr.agent's toggle can still pick
    assert "--parent was given" in render_config(fixed=("pr.dir",))
    assert "its toggle picks the agent" in render_config(fixed=("pr.agent",))
    assert "was given" not in page


def test_render_config_masks_env_secret(monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "s3cret")
    page = render_config()
    assert "JIRA_API_TOKEN overrides the file: ********" in page and "s3cret" not in page


def test_render_config_invalid_file(isolated_config):
    isolated_config.parent.mkdir(parents=True)
    isolated_config.write_text("not = [toml")
    page = render_config()
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
    assert reviews == [("acme/api", 7, str(tmp_path), "claude", None, None)]
    post_config(base, "set", key="pr.agent", value="cursor")
    page = get(base + "/")
    assert 'role="radio" data-agent="cursor" aria-checked="true"' in page
    get(urllib.request.Request(base + "/review", data=b"repo=acme/api&number=8"))
    assert reviews[-1] == ("acme/api", 8, str(tmp_path), "cursor", None, None)
    # the reviews-tab toggle wins over the setting
    data = urlencode({"repo": "acme/api", "number": "8", "agent": "claude"}).encode()
    get(urllib.request.Request(base + "/review", data=data))
    assert reviews[-1][3] == "claude"
    post_config(base, "set", key="cursor.pr.model", value="composer-x")
    post_config(base, "set", key="claude.pr.model", value="opus-x")
    get(urllib.request.Request(base + "/review", data=b"repo=acme/api&number=9"))
    assert reviews[-1] == ("acme/api", 9, str(tmp_path), "cursor", "opus-x", "composer-x")
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
    def capture(parent, fixed, agent, claude_model=None, cursor_model=None):
        made.append(fixed)
        return real(parent, fixed, agent, claude_model, cursor_model)

    monkeypatch.setattr(server, "make_handler", capture)
    logger = server.logging.getLogger("be")
    monkeypatch.setattr(logger, "level", logger.level)
    CliRunner().invoke(server.server, ["--no-open"])
    CliRunner().invoke(server.server, ["--no-open", "--parent", str(tmp_path)], env={"BE_SERVER_LOG_LEVEL": "info"})
    CliRunner().invoke(
        server.server, ["--no-open", "--claude-model", "opus-x", "--cursor-model", "composer-x"]
    )
    # only flags fix a setting; an env var or the file is reread when used
    assert made == [(), ("pr.dir",), ("claude.pr.model", "cursor.pr.model")]
