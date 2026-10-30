"""Signing in to Google with your own OAuth desktop client, and calling its JSON APIs.

`be calendar login` signs in once through the browser, for every scope be uses, and saves a
refresh token; calls trade it for an access token, kept until it expires."""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

import click

from be import config

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = (
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
)
LOGIN = "run `be calendar login`"

# (refresh token, access token, expires at)
_cached: tuple[str, str, float] | None = None


class GoogleError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        # the HTTP status Google answered with, if it answered
        self.status = status


def client() -> tuple[str, str]:
    client_id, _ = config.resolve("google.client_id")
    client_secret, _ = config.resolve("google.client_secret")
    if not client_id or not client_secret:
        raise GoogleError("google.client_id and google.client_secret must be set")
    return client_id, client_secret


def post_token(fields: dict) -> dict:
    """POST fields to Google's token endpoint; its JSON answer."""
    request = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode(fields).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        try:
            error = json.load(e).get("error", "")
        except (ValueError, AttributeError):
            error = ""
        if error == "invalid_grant":
            raise GoogleError(f"the Google sign-in expired or was revoked; {LOGIN}") from None
        raise GoogleError(f"HTTP {e.code} from Google's token endpoint{f' ({error})' if error else ''}") from None
    except urllib.error.URLError as e:
        raise GoogleError(f"could not reach Google: {e.reason}") from None
    except (json.JSONDecodeError, TimeoutError) as e:
        raise GoogleError(str(e)) from None


def login(open_browser=webbrowser.open) -> None:
    """Sign in through the browser, with a loopback redirect and PKCE, and save the refresh token."""
    client_id, client_secret = client()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    got: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            if "code" in query or "error" in query:
                got.update(query)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Signed in to be; you can close this tab." if "code" in query else b"Sign-in failed.")

        def log_message(self, *args):
            pass

    with http.server.HTTPServer(("127.0.0.1", 0), Handler) as server:
        redirect = f"http://127.0.0.1:{server.server_port}"
        url = AUTH_URL + "?" + urllib.parse.urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect,
                "response_type": "code",
                "scope": " ".join(SCOPES),
                "access_type": "offline",
                # without consent, Google only sends a refresh token the first time
                "prompt": "consent",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
            }
        )
        click.echo(f"Opening the browser to sign in; if it doesn't open, visit:\n{url}")
        open_browser(url)
        server.timeout = 5
        deadline = time.monotonic() + 300
        # the browser may ask for a favicon first
        while not got:
            if time.monotonic() > deadline:
                raise GoogleError("timed out waiting for the sign-in")
            server.handle_request()
    if got.get("error"):
        raise GoogleError(f"sign-in failed: {got['error']}")
    if got.get("state") != state:
        raise GoogleError("sign-in failed: the state didn't match")
    tokens = post_token(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": got["code"],
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect,
        }
    )
    if not tokens.get("refresh_token"):
        raise GoogleError("Google sent no refresh token")
    config.set_value("google.refresh_token", tokens["refresh_token"])


def access_token() -> str:
    global _cached
    refresh, _ = config.resolve("google.refresh_token")
    if not refresh:
        raise GoogleError(f"not signed in to Google; {LOGIN}")
    if _cached and _cached[0] == refresh and _cached[2] > time.time() + 60:
        return _cached[1]
    client_id, client_secret = client()
    tokens = post_token(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        }
    )
    if not tokens.get("access_token"):
        raise GoogleError("Google sent no access token")
    _cached = (refresh, tokens["access_token"], time.time() + float(tokens.get("expires_in", 3600)))
    return tokens["access_token"]


def call(url: str, name: str, body: dict | None = None, method: str | None = None) -> dict:
    """The JSON answer to an authorized call to url; name is the API's, for errors."""
    headers = {"Authorization": f"Bearer {access_token()}", "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            answer = json.load(response)
    except urllib.error.HTTPError as e:
        hint = f"; {LOGIN}" if e.code in (401, 403) else ""
        raise GoogleError(f"HTTP {e.code} from {name}{hint}", e.code) from None
    except urllib.error.URLError as e:
        raise GoogleError(f"could not reach {name}: {e.reason}") from None
    except (json.JSONDecodeError, TimeoutError) as e:
        raise GoogleError(str(e)) from None
    if not isinstance(answer, dict):
        raise GoogleError(f"unexpected response from {name}")
    return answer


def get_json(url: str, params: dict, name: str) -> dict:
    return call(f"{url}?{urllib.parse.urlencode(params, doseq=True)}" if params else url, name)


def post_json(url: str, body: dict, name: str) -> dict:
    return call(url, name, body, "POST")
