import json
import subprocess

import click
import pytest

from click.testing import CliRunner

from be import github
from be.cli import cli
from be.commands import pr

PRS = [
    {"number": 7, "repo": "acme/api", "title": "Fix login", "checks": "pass", "approvals": 2, "draft": False, "author": "dev", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
    {"number": 1234, "repo": "acme/web-app", "title": "Add page", "checks": "fail", "approvals": 0, "draft": False, "author": "dev", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
    {"number": 9, "repo": "acme/api", "title": "WIP", "checks": "pass", "approvals": 0, "draft": True, "author": "dev", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
    {"number": 5, "repo": "acme/api", "title": "Bump", "checks": "pass", "approvals": 0, "draft": False, "author": "renovate", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
]


def test_review_requests_parses_graphql(monkeypatch):
    def node(repo, number, state):
        commits = [{"commit": {"statusCheckRollup": {"state": state} if state else None}}]
        return {
            "isDraft": number == 9,
            "reviewDecision": "APPROVED" if number == 3 else None,
            "autoMergeRequest": {"enabledAt": "2026-01-01T00:00:00Z"} if number == 2 else None,
            "author": {"login": "renovate"} if number == 2 else None,
            "number": number,
            "title": f"t{number}",
            "repository": {"nameWithOwner": repo, "squashMergeAllowed": repo == "b/x", "rebaseMergeAllowed": True},
            "commits": {"nodes": commits},
            "latestOpinionatedReviews": {"nodes": [{"state": "APPROVED"}] * (number % 3) + [{"state": "CHANGES_REQUESTED"}]},
        }

    nodes = [node("b/x", 2, "FAILURE"), node("a/y", 9, None), {}, node("a/y", 3, "PENDING")]
    out = json.dumps({"data": {"search": {"nodes": nodes}}})
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout=out)
    )
    assert [
        (p["repo"], p["number"], p["checks"], p["approvals"], p["draft"], p["author"], p["approved"], p["auto_merge"], p["merge_flag"])
        for p in github.review_requests()
    ] == [
        ("a/y", 3, "pending", 0, False, "", True, False, "--rebase"),
        ("a/y", 9, "none", 0, True, "", False, False, "--rebase"),
        ("b/x", 2, "fail", 2, False, "renovate", False, True, "--squash"),
    ]


def test_pr_ls_table(monkeypatch):
    monkeypatch.setattr(pr, "review_requests", lambda: PRS)
    result = CliRunner().invoke(cli, ["pr", "ls", "--all"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "PR     REPO          AUTHOR    CHECKS  APPROVALS  DRAFT  TITLE",
        "#7     acme/api      dev       pass    2          no     Fix login",
        "#1234  acme/web-app  dev       fail    0          no     Add page",
        "#9     acme/api      dev       pass    0          yes    WIP",
        "#5     acme/api      renovate  pass    0          no     Bump",
    ]


def test_pr_ls_defaults_to_ready_and_passing(monkeypatch):
    monkeypatch.setattr(pr, "review_requests", lambda: PRS)
    result = CliRunner().invoke(cli, ["pr", "ls"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "3 hidden (draft, not passing, or by renovate); --all shows them",
        "PR  REPO      AUTHOR  CHECKS  APPROVALS  TITLE",
        "#7  acme/api  dev     pass    2          Fix login",
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


LIMITED = subprocess.CompletedProcess([], 1, stdout="", stderr="GraphQL: API rate limit exceeded for user")


def fake_gh(monkeypatch, results):
    """Make subprocess.run return results in turn and record the sleeps between them."""
    slept = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: results.pop(0))
    monkeypatch.setattr(github.time, "sleep", slept.append)
    return slept


def test_search_prs_retries_rate_limits_and_gateway_errors(monkeypatch):
    out = json.dumps({"data": {"search": {"nodes": []}}})
    bad_gateway = subprocess.CompletedProcess([], 1, stdout="", stderr="HTTP 502: Bad Gateway (https://api.github.com/graphql)")
    slept = fake_gh(monkeypatch, [LIMITED, bad_gateway, subprocess.CompletedProcess([], 0, stdout=out)])
    assert github.review_requests() == []
    assert slept == [2, 4]


def test_search_prs_gives_up_after_retries(monkeypatch):
    slept = fake_gh(monkeypatch, [LIMITED] * 5)
    with pytest.raises(click.ClickException, match="rate limit"):
        github.review_requests()
    assert slept == [2, 4, 8, 16]


def test_gh_does_not_retry_other_failures(monkeypatch):
    failed = subprocess.CompletedProcess([], 1, stdout="", stderr="HTTP 401: Bad credentials")
    slept = fake_gh(monkeypatch, [failed])
    with pytest.raises(click.ClickException, match="Bad credentials"):
        github.mark_ready("acme/api", 7)
    assert slept == []


def test_pr_ls_mine_is_filtered(monkeypatch):
    monkeypatch.setattr(pr, "authored_prs", lambda: PRS)
    monkeypatch.setattr(pr, "review_requests", lambda: 1 / 0)
    result = CliRunner().invoke(cli, ["pr", "ls", "-m"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "3 hidden (draft, not passing, or by renovate); --all shows them",
        "PR  REPO      AUTHOR  CHECKS  APPROVALS  TITLE",
        "#7  acme/api  dev     pass    2          Fix login",
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


def test_mark_ready_and_auto_merge_call_gh(monkeypatch):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    github.mark_ready("acme/api", 9)
    github.enable_auto_merge("acme/api", 7, "--merge")
    github.merge("acme/api", 8, "--rebase")
    # the merge flag comes from the search, so no repo lookup is made
    assert calls == [
        ["gh", "pr", "ready", "9", "--repo", "acme/api"],
        ["gh", "pr", "merge", "7", "--repo", "acme/api", "--auto", "--merge"],
        ["gh", "pr", "merge", "8", "--repo", "acme/api", "--rebase"],
    ]


def test_merge_flag():
    assert github.merge_flag({"squashMergeAllowed": True, "mergeCommitAllowed": True}) == "--squash"
    assert github.merge_flag({"squashMergeAllowed": False, "rebaseMergeAllowed": True}) == "--rebase"
    assert github.merge_flag({"nameWithOwner": "acme/api"}) is None


def test_merge_without_allowed_method_raises(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: 1 / 0)
    with pytest.raises(click.ClickException, match="allows no merge method"):
        github.merge("acme/api", 8, None)
    with pytest.raises(click.ClickException, match="allows no merge method"):
        github.enable_auto_merge("acme/api", 8, None)


def test_gh_failure_raises(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="auto-merge is not allowed"),
    )
    with pytest.raises(click.ClickException, match="auto-merge is not allowed"):
        github.enable_auto_merge("acme/api", 7, "--squash")


def test_run_mine_action(monkeypatch):
    calls = []
    monkeypatch.setattr(pr, "mark_ready", lambda *args: calls.append(("ready", *args)))
    monkeypatch.setattr(pr, "enable_auto_merge", lambda *args: calls.append(("auto", *args)))
    draft, ready = dict(PRS[2]), dict(PRS[0])
    assert pr.run_mine_action("automerge", draft) == "acme/api#9 is a draft; mark it ready first"
    assert pr.run_mine_action("ready", draft) == "marked acme/api#9 ready for review"
    # the row is updated in place
    assert not draft["draft"]
    assert pr.run_mine_action("ready", ready) == "acme/api#7 is not a draft"
    assert pr.run_mine_action("automerge", ready) == "enabled auto-merge on acme/api#7"
    assert ready["auto_merge"]
    assert calls == [("ready", "acme/api", 9), ("auto", "acme/api", 7, "--squash")]
    assert pr.run_mine_action("automerge", ready) == "auto-merge is already enabled on acme/api#7"
    assert len(calls) == 2


def test_run_mine_action_merge(monkeypatch):
    calls = []
    monkeypatch.setattr(pr, "merge", lambda *args: calls.append(args))
    ready = PRS[0]
    assert pr.run_mine_action("merge", ready) == "acme/api#7 is not approved"
    assert pr.run_mine_action("merge", {**PRS[2], "approved": True}) == (
        "acme/api#9 is a draft; mark it ready first"
    )
    assert pr.run_mine_action("merge", {**ready, "approved": True}) == "merged acme/api#7"
    assert calls == [("acme/api", 7, "--squash")]


def test_pr_ls_interactive_mine_actions(monkeypatch):
    fetched = []
    rows = [dict(p) for p in PRS]
    monkeypatch.setattr(pr, "authored_prs", lambda: fetched.append("mine") or rows)
    picks = [("ready", 2), ("automerge", 2), ("automerge", 0), None]
    shown = []

    def choose(rows, index=0, hint="", actions=()):
        shown.append((hint, actions))
        return picks.pop(0)

    monkeypatch.setattr(pr, "choose", choose)
    calls = []
    monkeypatch.setattr(pr, "mark_ready", lambda *args: calls.append(("ready", *args)))

    def auto(slug, number, flag):
        if number == 7:
            raise click.ClickException("auto-merge is not allowed")
        calls.append(("auto", slug, number, flag))

    monkeypatch.setattr(pr, "enable_auto_merge", auto)
    result = CliRunner().invoke(cli, ["pr", "ls", "-i", "-m", "-a"])
    assert result.exit_code == 0, result.output
    # the draft marked ready can be set to auto-merge without a refetch
    assert calls == [("ready", "acme/api", 9), ("auto", "acme/api", 9, "--squash")]
    assert "marked acme/api#9 ready for review" in result.output
    assert "enabled auto-merge on acme/api#9" in result.output
    assert "error: auto-merge is not allowed" in result.output
    # successful actions update the row in place; only the failure refetches
    assert fetched == ["mine", "mine"]
    assert "r ready, u auto-merge" in shown[0][0]
    assert shown[0][1][-2:] == ("ready", "automerge")


def test_pr_ls_interactive_merge_drops_row(monkeypatch):
    rows = [{**PRS[0], "approved": True}]
    monkeypatch.setattr(pr, "authored_prs", lambda: rows)
    monkeypatch.setattr(pr, "merge", lambda *args: None)
    picks = [(pr.MERGE_ACTION, 0), None]
    shown = []

    def choose(rows, index=0, hint="", actions=()):
        shown.append(rows)
        return picks.pop(0)

    monkeypatch.setattr(pr, "choose", choose)
    monkeypatch.setattr(pr, "MINE_ACTIONS", pr.MINE_ACTIONS + (pr.MERGE_ACTION,))
    result = CliRunner().invoke(cli, ["pr", "ls", "-i", "-m", "-a"])
    assert result.exit_code == 0, result.output
    assert "merged acme/api#7" in result.output
    assert rows == [] and shown[-1] == [pr.EMPTY[True]]


def test_pr_ls_interactive_review_requests_have_no_mine_actions(monkeypatch):
    monkeypatch.setattr(pr, "review_requests", lambda: PRS)
    shown = []
    monkeypatch.setattr(
        pr, "choose", lambda rows, index=0, hint="", actions=(): shown.append((hint, actions))
    )
    CliRunner().invoke(cli, ["pr", "ls", "-i"])
    assert "ready" not in shown[0][1] and "u auto-merge" not in shown[0][0]
