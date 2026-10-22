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


def issue_summary(key: str) -> str:
    url, _ = config.resolve("jira.url")
    email, _ = config.resolve("jira.email")
    token, _ = config.resolve("jira.token")
    if not url or not email or not token:
        raise JiraError("jira.url, jira.email and jira.token must be set")
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    request = urllib.request.Request(
        f"{url.rstrip('/')}/rest/api/3/issue/{urllib.parse.quote(key)}?fields=summary",
        headers={"Authorization": f"Basic {auth}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
    except urllib.error.HTTPError as e:
        # Jira answers 404, not 401, when it rejects the credentials
        hint = "; the issue is missing or the token was rejected" if e.code == 404 else ""
        raise JiraError(f"HTTP {e.code} from {url}{hint}") from None
    except urllib.error.URLError as e:
        raise JiraError(f"could not reach {url}: {e.reason}") from None
    except (json.JSONDecodeError, TimeoutError) as e:
        raise JiraError(str(e)) from None
    summary = data.get("fields", {}).get("summary") if isinstance(data, dict) else None
    if not isinstance(summary, str) or not summary:
        raise JiraError(f"no summary in the response for {key}")
    return summary
