"""Resolving and cloning GitHub repos."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import click


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
    result = subprocess.run(
        ["git", "-C", str(dest), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    url = result.stdout.strip().removesuffix(".git")
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


PR_SEARCH = """
query($q: String!) {
  search(query: $q, type: ISSUE, first: 100) {
    nodes {
      ... on PullRequest {
        number
        title
        isDraft
        author { login }
        repository { nameWithOwner }
        commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
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
    """Open PRs that request your review."""
    return search_prs("review-requested:@me")


def authored_prs() -> list[dict]:
    """Open PRs you opened."""
    return search_prs("author:@me")


def search_prs(qualifier: str) -> list[dict]:
    """Open PRs matching qualifier: number, repo, title, checks, draft and author."""
    query = f"is:pr is:open archived:false {qualifier}"
    try:
        result = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={PR_SEARCH}", "-f", f"q={query}"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise click.ClickException("gh not found; install the GitHub CLI") from None
    if result.returncode != 0:
        raise click.ClickException(f"gh api graphql failed: {result.stderr.strip()}")
    try:
        nodes = json.loads(result.stdout)["data"]["search"]["nodes"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise click.ClickException("gh returned unreadable search results") from None
    prs = []
    for node in nodes:
        if not node:
            continue
        commits = node["commits"]["nodes"]
        rollup = commits[0]["commit"]["statusCheckRollup"] if commits else None
        state = rollup["state"] if rollup else None
        prs.append(
            {
                "number": node["number"],
                "repo": node["repository"]["nameWithOwner"],
                "title": node["title"],
                "checks": CHECK_STATES.get(state, "none"),
                "draft": bool(node.get("isDraft")),
                "author": (node.get("author") or {}).get("login", ""),
            }
        )
    return sorted(prs, key=lambda pr: (pr["repo"], pr["number"]))


def same_login(a: str, b: str) -> bool:
    """Compare logins, ignoring case and the [bot] suffix REST adds to apps."""
    return a.lower().removesuffix("[bot]") == b.lower().removesuffix("[bot]")
