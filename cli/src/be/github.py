"""Resolving and cloning GitHub repos."""

from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path

import click

log = logging.getLogger(__name__)


def repo_slug(name: str, org: str | None) -> str:
    if "/" in name:
        return name
    if not org:
        raise click.UsageError(f"{name!r} has no owner and WORK_ORG is not set")
    return f"{org}/{name}"


def clone(slug: str, dest: Path | str | None = None) -> int:
    cmd = ["git", "clone", "--recurse-submodules", f"git@github.com:{slug}.git"]
    if dest:
        cmd.append(str(dest))
    return subprocess.run(cmd).returncode


def remote_matches(dest: Path, slug: str) -> bool:
    """Whether dest's origin is slug. GitHub owner and name ignore case."""
    result = subprocess.run(
        ["git", "-C", str(dest), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    url = result.stdout.strip().lower().removesuffix(".git")
    slug = slug.lower()
    return url.endswith(f":{slug}") or url.endswith(f"/{slug}")


def clone_or_reuse(slug: str, dest: Path) -> None:
    if dest.exists():
        if remote_matches(dest, slug):
            click.echo(f"using existing checkout {dest}")
            return
        raise click.ClickException(f"{dest} exists and is not {slug}")
    code = clone(slug, dest)
    if code != 0:
        raise click.exceptions.Exit(code)


# seconds to wait before each retry of a gh call GitHub rate-limited or failed with a 5xx
RETRY_DELAYS = (2, 4, 8, 16)

# rate limits, and the gateway errors and cut-off responses GitHub gives when a query times out
RETRYABLE = (
    "rate limit",
    "too quickly",
    "http 502",
    "http 503",
    "http 504",
    "unexpected end of json input",
)


def retryable(result: subprocess.CompletedProcess) -> bool:
    output = f"{result.stderr or ''} {result.stdout or ''}".lower()
    return any(marker in output for marker in RETRYABLE)


def run_gh(*args: str) -> subprocess.CompletedProcess:
    """Run gh, waiting and retrying while GitHub reports a rate limit or a gateway error."""
    for delay in (*RETRY_DELAYS, None):
        log.debug("running gh %s", " ".join(args[:2]))
        try:
            result = subprocess.run(["gh", *args], capture_output=True, text=True)
        except FileNotFoundError:
            raise click.ClickException("gh not found; install the GitHub CLI") from None
        if result.returncode == 0 or delay is None or not retryable(result):
            return result
        log.warning("GitHub: %s; retrying in %ss", result.stderr.strip(), delay)
        time.sleep(delay)


PR_SEARCH = """
query($q: String!, $after: String) {
  search(query: $q, type: ISSUE, first: 25, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number
        title
        isDraft
        reviewDecision
        autoMergeRequest { enabledAt }
        author { login }
        repository { nameWithOwner squashMergeAllowed mergeCommitAllowed rebaseMergeAllowed }
        commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
        latestOpinionatedReviews(first: 20) { nodes { state } }
      }
    }
  }
}
"""

CHECK_STATES = {
    "SUCCESS": "pass",
    "FAILURE": "fail",
    "ERROR": "fail",
    "PENDING": "pending",
    "EXPECTED": "pending",
}


def review_requests() -> list[dict]:
    """Open PRs that request your review by name."""
    return search_prs("user-review-requested:@me")


def team_review_requests() -> list[dict]:
    """Open PRs that request your review only through a team."""
    return search_prs("review-requested:@me -user-review-requested:@me")


def authored_prs() -> list[dict]:
    """Open PRs you opened."""
    return search_prs("author:@me")


def search_prs(qualifier: str) -> list[dict]:
    """Open PRs matching qualifier: number, repo, title, checks, approvals, draft, author,
    whether it's approved, whether auto-merge is enabled, and the repo's merge flag."""
    query = f"is:pr is:open archived:false {qualifier}"
    nodes = []
    after = None
    # small pages, so no one request is heavy enough for GitHub to time out
    while True:
        cursor = ["-f", f"after={after}"] if after else []
        result = run_gh("api", "graphql", "-f", f"query={PR_SEARCH}", *cursor, "-f", f"q={query}")
        if result.returncode != 0:
            raise click.ClickException(f"gh api graphql failed: {result.stderr.strip()}")
        try:
            search = json.loads(result.stdout)["data"]["search"]
            nodes += search["nodes"]
        except (json.JSONDecodeError, KeyError, TypeError):
            raise click.ClickException("gh returned unreadable search results") from None
        page = search.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = page["endCursor"]
    prs = []
    for node in nodes:
        if not node:
            continue
        commits = node["commits"]["nodes"]
        rollup = commits[0]["commit"]["statusCheckRollup"] if commits else None
        state = rollup["state"] if rollup else None
        # each reviewer's latest approve or request-changes review, so a retracted approval doesn't count
        reviews = (node.get("latestOpinionatedReviews") or {}).get("nodes") or []
        prs.append(
            {
                "number": node["number"],
                "repo": node["repository"]["nameWithOwner"],
                "title": node["title"],
                "checks": CHECK_STATES.get(state, "none"),
                "approvals": sum(1 for r in reviews if r and r["state"] == "APPROVED"),
                "draft": bool(node.get("isDraft")),
                "author": (node.get("author") or {}).get("login", ""),
                "approved": node.get("reviewDecision") == "APPROVED",
                "auto_merge": bool(node.get("autoMergeRequest")),
                "merge_flag": merge_flag(node["repository"]),
            }
        )
    return sorted(prs, key=lambda pr: (pr["repo"], pr["number"]))


def gh(*args: str) -> str:
    """Run gh and return its stdout, raising ClickException on failure."""
    result = run_gh(*args)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise click.ClickException(f"gh {args[0]} {args[1]} failed: {message}")
    return result.stdout


def mark_ready(slug: str, number: int) -> None:
    """Mark a draft PR ready for review."""
    gh("pr", "ready", str(number), "--repo", slug)


# merge methods in order of preference, keyed by the repo setting that allows each
MERGE_METHODS = (
    ("squashMergeAllowed", "--squash"),
    ("mergeCommitAllowed", "--merge"),
    ("rebaseMergeAllowed", "--rebase"),
)


def merge_flag(repo: dict) -> str | None:
    """The gh pr merge flag for the repo's preferred allowed merge method, from its search
    result, so merging needs no extra lookup."""
    for field, flag in MERGE_METHODS:
        if repo.get(field):
            return flag
    return None


def require_flag(slug: str, flag: str | None) -> str:
    if not flag:
        raise click.ClickException(f"{slug} allows no merge method")
    return flag


def enable_auto_merge(slug: str, number: int, flag: str | None) -> None:
    """Merge the PR once its requirements pass, with the merge flag from merge_flag."""
    gh("pr", "merge", str(number), "--repo", slug, "--auto", require_flag(slug, flag))


def merge(slug: str, number: int, flag: str | None) -> None:
    """Merge the PR now, with the merge flag from merge_flag."""
    gh("pr", "merge", str(number), "--repo", slug, require_flag(slug, flag))


def same_login(a: str, b: str) -> bool:
    """Compare logins, ignoring case and the [bot] suffix REST adds to apps."""
    return a.lower().removesuffix("[bot]") == b.lower().removesuffix("[bot]")
