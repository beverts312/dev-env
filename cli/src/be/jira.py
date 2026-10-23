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


def in_progress_issues() -> list[dict]:
    """Issues assigned to you in an In Progress status, newest first.

    Each is {"key", "type", "summary", "parent", "parent_type", "parent_summary"}; the
    parent fields describe the parent issue, and are "" when there is none.
    """
    issues: list[dict] = []
    token = None
    while True:
        params = {"jql": IN_PROGRESS_JQL, "fields": "summary,issuetype,parent", "maxResults": "100"}
        if token:
            params["nextPageToken"] = token
        data = get_json(f"/rest/api/3/search/jql?{urllib.parse.urlencode(params)}")
        if not isinstance(data, dict):
            raise JiraError("unexpected response from the Jira search")
        for issue in data.get("issues") or []:
            fields = issue.get("fields") or {}
            parent = fields.get("parent") or {}
            parent_fields = parent.get("fields") or {}
            issues.append(
                {
                    "key": issue.get("key", ""),
                    "type": (fields.get("issuetype") or {}).get("name") or "",
                    "summary": fields.get("summary") or "",
                    "parent": parent.get("key") or "",
                    "parent_type": (parent_fields.get("issuetype") or {}).get("name") or "",
                    "parent_summary": parent_fields.get("summary") or "",
                }
            )
        token = data.get("nextPageToken")
        if not token or data.get("isLast", True):
            return issues
