import json
import subprocess

from click.testing import CliRunner

from be import github
from be.cli import cli
from be.commands import pr

PRS = [
    {"number": 7, "repo": "acme/api", "title": "Fix login", "checks": "pass", "draft": False, "author": "dev"},
    {"number": 1234, "repo": "acme/web-app", "title": "Add page", "checks": "fail", "draft": False, "author": "dev"},
    {"number": 9, "repo": "acme/api", "title": "WIP", "checks": "pass", "draft": True, "author": "dev"},
    {"number": 5, "repo": "acme/api", "title": "Bump", "checks": "pass", "draft": False, "author": "renovate"},
]


def test_review_requests_parses_graphql(monkeypatch):
    def node(repo, number, state):
        commits = [{"commit": {"statusCheckRollup": {"state": state} if state else None}}]
        return {
            "isDraft": number == 9,
            "author": {"login": "renovate"} if number == 2 else None,
            "number": number,
            "title": f"t{number}",
            "repository": {"nameWithOwner": repo},
            "commits": {"nodes": commits},
        }

    nodes = [node("b/x", 2, "FAILURE"), node("a/y", 9, None), {}, node("a/y", 3, "PENDING")]
    out = json.dumps({"data": {"search": {"nodes": nodes}}})
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout=out)
    )
    assert [
        (p["repo"], p["number"], p["checks"], p["draft"], p["author"])
        for p in github.review_requests()
    ] == [
        ("a/y", 3, "pending", False, ""),
        ("a/y", 9, "none", True, ""),
        ("b/x", 2, "fail", False, "renovate"),
    ]


def test_pr_ls_table(monkeypatch):
    monkeypatch.setattr(pr, "review_requests", lambda: PRS)
    result = CliRunner().invoke(cli, ["pr", "ls", "--all"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "PR     REPO          AUTHOR    CHECKS  TITLE",
        "#7     acme/api      dev       pass    Fix login",
        "#1234  acme/web-app  dev       fail    Add page",
        "#9     acme/api      dev       pass    WIP",
        "#5     acme/api      renovate  pass    Bump",
    ]


def test_pr_ls_defaults_to_ready_and_passing(monkeypatch):
    monkeypatch.setattr(pr, "review_requests", lambda: PRS)
    result = CliRunner().invoke(cli, ["pr", "ls"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "3 hidden (draft, not passing, or by renovate); --all shows them",
        "PR  REPO      AUTHOR  CHECKS  TITLE",
        "#7  acme/api  dev     pass    Fix login",
    ]


def test_pr_ls_empty(monkeypatch):
    monkeypatch.setattr(pr, "review_requests", lambda: [])
    assert CliRunner().invoke(cli, ["pr", "ls"]).output == "no review requests\n"


def test_pr_ls_interactive_reviews_selection(monkeypatch, tmp_path):
    monkeypatch.setattr(pr, "review_requests", lambda: PRS)
    picks = [("get", 0), ("open", 1)]
    shown = []
    monkeypatch.setattr(
        pr, "choose", lambda rows, index=0, hint="", actions=(): shown.append(rows) or picks.pop(0)
    )
    reviews = []
    monkeypatch.setattr(pr, "open_review", lambda *args: reviews.append(args))
    result = CliRunner().invoke(cli, ["pr", "ls", "-i", "--all", "--parent", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert reviews == [("acme/web-app", 1234, str(tmp_path))]
    assert shown[0][0].startswith("#7 ")


def test_pr_ls_interactive_opens_in_browser(monkeypatch):
    monkeypatch.setattr(pr, "review_requests", lambda: PRS)
    picks = [("browse", 0), None]
    monkeypatch.setattr(pr, "choose", lambda rows, index=0, hint="", actions=(): picks.pop(0))
    launched = []
    monkeypatch.setattr(pr.click, "launch", lambda url: launched.append(url))
    result = CliRunner().invoke(cli, ["pr", "ls", "-i"])
    assert result.exit_code == 0, result.output
    assert launched == ["https://github.com/acme/api/pull/7"]


def test_search_prs_passes_qualifier(monkeypatch):
    calls = []
    out = json.dumps({"data": {"search": {"nodes": []}}})

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=out)

    monkeypatch.setattr(subprocess, "run", run)
    github.authored_prs()
    github.review_requests()
    assert [cmd[-1] for cmd in calls] == [
        "q=is:pr is:open archived:false author:@me",
        "q=is:pr is:open archived:false review-requested:@me",
    ]


def test_pr_ls_mine_is_filtered(monkeypatch):
    monkeypatch.setattr(pr, "authored_prs", lambda: PRS)
    monkeypatch.setattr(pr, "review_requests", lambda: 1 / 0)
    result = CliRunner().invoke(cli, ["pr", "ls", "-m"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "3 hidden (draft, not passing, or by renovate); --all shows them",
        "PR  REPO      AUTHOR  CHECKS  TITLE",
        "#7  acme/api  dev     pass    Fix login",
    ]
    result = CliRunner().invoke(cli, ["pr", "ls", "-m", "-a"])
    assert len(result.output.splitlines()) == 5


def test_pr_ls_mine_empty(monkeypatch):
    monkeypatch.setattr(pr, "authored_prs", lambda: [])
    assert CliRunner().invoke(cli, ["pr", "ls", "--mine"]).output == "no open PRs by you\n"


def test_pr_ls_interactive_toggles_mine(monkeypatch):
    fetched = []
    monkeypatch.setattr(pr, "review_requests", lambda: fetched.append("review") or PRS)
    monkeypatch.setattr(pr, "authored_prs", lambda: fetched.append("mine") or [])
    picks = [("toggle", 0), ("toggle", 0), ("browse", 0), None]
    shown = []

    def choose(rows, index=0, hint="", actions=()):
        shown.append((rows, actions))
        return picks.pop(0)

    monkeypatch.setattr(pr, "choose", choose)
    launched = []
    monkeypatch.setattr(pr.click, "launch", lambda url: launched.append(url))
    result = CliRunner().invoke(cli, ["pr", "ls", "-i"])
    assert result.exit_code == 0, result.output
    assert fetched == ["review", "mine"]
    assert shown[1] == (["no open PRs by you"], ("toggle", "all"))
    assert shown[2][0] == shown[0][0]
    assert launched == ["https://github.com/acme/api/pull/7"]


def test_pr_ls_interactive_toggles_filters(monkeypatch):
    fetched = []
    monkeypatch.setattr(pr, "review_requests", lambda: fetched.append("review") or PRS)
    picks = [("all", 0), ("all", 0), None]
    shown = []

    def choose(rows, index=0, hint="", actions=()):
        shown.append((len(rows), hint))
        return picks.pop(0)

    monkeypatch.setattr(pr, "choose", choose)
    result = CliRunner().invoke(cli, ["pr", "ls", "-i"])
    assert result.exit_code == 0, result.output
    assert fetched == ["review"]
    assert [count for count, _ in shown] == [1, 4, 1]
    assert shown[0][1].startswith("review requests (3 hidden) ·")
    assert "a show all" in shown[0][1] and "a filter" in shown[1][1]


def test_same_login():
    assert github.same_login("renovate", "Renovate[bot]")
    assert not github.same_login("renovate", "renovate-approve")
