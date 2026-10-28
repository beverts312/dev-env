"""Looking up Jira issues with an Atlassian API token."""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from be import config

ISSUE_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)-(\d+)")


class JiraError(Exception):
    pass


def issue_key(name: str, projects: dict) -> str | None:
    """Return KEY-123 if name starts with an issue in a configured project."""
    match = ISSUE_KEY.match(name)
    if not match:
        return None
    project = match.group(1).upper()
    if project not in {key.upper() for key in projects}:
        return None
    return f"{project}-{match.group(2)}"


def site_url() -> str:
    url, _ = config.resolve("jira.url")
    if not url:
        raise JiraError("jira.url must be set")
    return url.rstrip("/")


def issue_url(key: str) -> str:
    return f"{site_url()}/browse/{key}"


def get_json(path: str, not_found: str = "") -> object:
    """GET path from the Jira REST API; not_found is appended to a 404 error."""
    url, _ = config.resolve("jira.url")
    email, _ = config.resolve("jira.email")
    token, _ = config.resolve("jira.token")
    if not url or not email or not token:
        raise JiraError("jira.url, jira.email and jira.token must be set")
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    request = urllib.request.Request(
        f"{url.rstrip('/')}{path}",
        headers={"Authorization": f"Basic {auth}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        hint = f"; {not_found}" if e.code == 404 and not_found else ""
        raise JiraError(f"HTTP {e.code} from {url}{hint}") from None
    except urllib.error.URLError as e:
        raise JiraError(f"could not reach {url}: {e.reason}") from None
    except (json.JSONDecodeError, TimeoutError) as e:
        raise JiraError(str(e)) from None


def issue_summary(key: str) -> str:
    data = get_json(
        f"/rest/api/3/issue/{urllib.parse.quote(key)}?fields=summary",
        # Jira answers 404, not 401, when it rejects the credentials
        not_found="the issue is missing or the token was rejected",
    )
    summary = data.get("fields", {}).get("summary") if isinstance(data, dict) else None
    if not isinstance(summary, str) or not summary:
        raise JiraError(f"no summary in the response for {key}")
    return summary


IN_PROGRESS_JQL = 'assignee = currentUser() AND statusCategory = "In Progress" ORDER BY updated DESC'
# everything assigned to you that isn't done, for the page's tree
ASSIGNED_JQL = "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"
SEARCH_FIELDS = "summary,issuetype,parent,status,assignee"
# Jira's status category keys: To Do is "new", In Progress is "indeterminate"
IN_PROGRESS = "indeterminate"


def search(jql: str) -> list[dict]:
    """Every issue jql matches, in its order.

    Each is {"key", "type", "summary", "status", "category", "assignee", "parent",
    "parent_type", "parent_summary"}; category is the status category's key, assignee
    is a display name, and the parent fields are "" when there is no parent.
    """
    issues: list[dict] = []
    token = None
    while True:
        params = {"jql": jql, "fields": SEARCH_FIELDS, "maxResults": "100"}
        if token:
            params["nextPageToken"] = token
        data = get_json(f"/rest/api/3/search/jql?{urllib.parse.urlencode(params)}")
        if not isinstance(data, dict):
            raise JiraError("unexpected response from the Jira search")
        for issue in data.get("issues") or []:
            fields = issue.get("fields") or {}
            parent = fields.get("parent") or {}
            parent_fields = parent.get("fields") or {}
            status = fields.get("status") or {}
            issues.append(
                {
                    "key": issue.get("key", ""),
                    "type": (fields.get("issuetype") or {}).get("name") or "",
                    "summary": fields.get("summary") or "",
                    "status": status.get("name") or "",
                    "category": (status.get("statusCategory") or {}).get("key") or "",
                    "assignee": (fields.get("assignee") or {}).get("displayName") or "",
                    "parent": parent.get("key") or "",
                    "parent_type": (parent_fields.get("issuetype") or {}).get("name") or "",
                    "parent_summary": parent_fields.get("summary") or "",
                }
            )
        token = data.get("nextPageToken")
        if not token or data.get("isLast", True):
            return issues


def in_progress_issues() -> list[dict]:
    """Issues assigned to you in an In Progress status, newest first, as search returns them."""
    return search(IN_PROGRESS_JQL)


def issue_tree() -> list[dict]:
    """Issues assigned to you that aren't done, each nested under its parent when that's shown too.

    Under each of yours that's in progress are its children that aren't done, whoever they're
    assigned to. Each issue is as search returns it, plus "mine" (assigned to you) and
    "children"; the top level is in progress first, then newest first, as are children.
    """
    assigned = search(ASSIGNED_JQL)
    for issue in assigned:
        issue["mine"] = True
    keys = {issue["key"] for issue in assigned}
    active = [issue["key"] for issue in assigned if issue["category"] == IN_PROGRESS]
    others: list[dict] = []
    if active:
        # the JQL is only built from keys Jira returned, which never need quoting
        jql = f"parent in ({', '.join(active)}) AND statusCategory != Done ORDER BY updated DESC"
        others = [issue for issue in search(jql) if issue["key"] not in keys]
        for issue in others:
            issue["mine"] = False
    issues = sorted(assigned + others, key=lambda i: i["category"] != IN_PROGRESS)
    by_key = {issue["key"]: {**issue, "children": []} for issue in issues}
    roots = []
    for node in by_key.values():
        parent = by_key.get(node["parent"])
        (parent["children"] if parent else roots).append(node)
    return roots
