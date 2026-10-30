"""Settings, resolved from CLI flags > env vars > ~/.be/config > defaults."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import tomli_w

CONFIG_ENV = "BE_CONFIG"
DEFAULT_CONFIG_PATH = Path("~/.be/config")


@dataclass(frozen=True)
class Setting:
    key: str
    env: str
    help: str
    default: str | None = None
    # "map" is a table of strings: set entries as <key>.<name>, env var is JSON
    kind: str = "str"
    # masked in `be config list`
    secret: bool = False
    # the only values it takes, if limited; `be server`'s config page offers them in a dropdown
    choices: tuple[str, ...] = ()


SETTINGS = {
    s.key: s
    for s in (
        Setting("work_org", "WORK_ORG", "GitHub org for bare repo names"),
        Setting(
            "interactive",
            "BE_INTERACTIVE",
            "Use -i by default when run in a terminal: true or false",
            "false",
            choices=("true", "false"),
        ),
        Setting("git.email", "GIT_EMAIL", "git user.email for `be git author`"),
        Setting("git.name", "GIT_NAME", "git user.name for `be git author`"),
        Setting("pr.dir", "PRS_DIR", "Parent directory for PR checkouts"),
        Setting("pr.agent", "BE_PR_AGENT", "Agent CLI for `be pr review`: claude or cursor", "claude"),
        Setting(
            "claude.pr.model",
            "BE_CLAUDE_PR_MODEL",
            "Model for Claude pr reviews, passed as claude --model",
        ),
        Setting(
            "cursor.pr.model",
            "BE_CURSOR_PR_MODEL",
            "Model for Cursor pr reviews, passed as agent --model",
        ),
        Setting("ws.dir", "WS_DIR", "Parent directory for workspaces"),
        Setting("todo.dir", "BE_TODO_DIR", "Directory that holds the todo markdown files", "~/notes/todos"),
        Setting("claude.model", "BE_CLAUDE_MODEL", "Model passed as claude --model", "claude-opus-5-5"),
        Setting("cmux.bin", "BE_CMUX_BIN", "Path to the cmux binary"),
        Setting(
            "cmux.window",
            "BE_CMUX_WINDOW",
            "cmux window for new workspaces: pick, or a window index, ref or UUID",
        ),
        Setting(
            "server.log_level",
            "BE_SERVER_LOG_LEVEL",
            "`be server` log level: debug, info, warning or error",
            "warning",
            choices=("debug", "info", "warning", "error"),
        ),
        Setting("cloudflare.account_id", "CLOUDFLARE_ACCOUNT_ID", "Cloudflare account for new zones"),
        Setting("jira.url", "JIRA_URL", "Base URL of the Jira site"),
        Setting("jira.email", "JIRA_EMAIL", "Atlassian account email for the Jira API"),
        Setting("jira.token", "JIRA_API_TOKEN", "Atlassian API token for the Jira API", secret=True),
        Setting("jira.projects", "JIRA_PROJECTS", "Jira project keys and their descriptions", kind="map"),
        Setting("google.client_id", "GOOGLE_CLIENT_ID", "OAuth desktop client ID for `be calendar login`"),
        Setting(
            "google.client_secret",
            "GOOGLE_CLIENT_SECRET",
            "OAuth desktop client secret for `be calendar login`",
            secret=True,
        ),
        Setting(
            "google.refresh_token",
            "GOOGLE_REFRESH_TOKEN",
            "Google refresh token, saved by `be calendar login`",
            secret=True,
        ),
        Setting("calendar.id", "BE_CALENDAR_ID", "Google calendar the home page shows", "primary"),
    )
}


def setting(key: str) -> Setting:
    """The setting for KEY, or for the map setting KEY is an entry of."""
    s = SETTINGS.get(key)
    if s is None:
        s = SETTINGS.get(key.rpartition(".")[0])
        if s is None or s.kind != "map":
            valid = ", ".join(f"{k}.<name>" if v.kind == "map" else k for k, v in SETTINGS.items())
            raise click.BadParameter(f"unknown key {key!r}; valid keys: {valid}")
    return s


def config_path() -> Path:
    return Path(os.environ.get(CONFIG_ENV) or DEFAULT_CONFIG_PATH).expanduser()


def load_file() -> dict[str, Any]:
    path = config_path()
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        raise click.ClickException(f"invalid config file {path}: {e}") from None


def save_file(data: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config-")
    try:
        with os.fdopen(fd, "wb") as f:
            tomli_w.dump(data, f)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def set_value(key: str, value: str) -> bool:
    """Write KEY = VALUE to the config file; True if the setting's env var overrides it."""
    s = setting(key)
    if s.kind == "map" and key == s.key:
        raise click.BadParameter(f"{key} is a map; set entries with {key}.<name>")
    data = load_file()
    *tables, name = key.split(".")
    node = data
    for table in tables:
        node = node.setdefault(table, {})
    node[name] = value
    save_file(data)
    return bool(os.environ.get(s.env))


def unset_value(key: str) -> None:
    """Remove KEY from the config file, and any tables that leaves empty."""
    setting(key)
    data = load_file()
    *tables, name = key.split(".")
    parents = [data]
    for table in tables:
        child = parents[-1].get(table)
        if not isinstance(child, dict):
            return
        parents.append(child)
    parents[-1].pop(name, None)
    for table, parent in zip(reversed(tables), reversed(parents[:-1])):
        if parent[table]:
            break
        del parent[table]
    save_file(data)


def file_value(key: str, data: dict[str, Any] | None = None) -> Any:
    node: Any = load_file() if data is None else data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def env_value(s: Setting) -> Any:
    raw = os.environ[s.env]
    if s.kind != "map":
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise click.ClickException(f"invalid JSON in {s.env}: {e}") from None


def resolve(key: str) -> tuple[Any, str]:
    """Return (value, source) where source is env:<VAR>, file, default or unset."""
    s = setting(key)
    if os.environ.get(s.env):
        value, source = env_value(s), f"env:{s.env}"
    else:
        value, source = file_value(s.key), "file"
        if value is None and s.default is not None:
            value, source = s.default, "default"
    if s.kind == "map" and value is not None:
        if not isinstance(value, dict) or not all(isinstance(v, str) for v in value.values()):
            raise click.ClickException(f"{s.key} ({source}) must be a table of strings")
        if key != s.key:
            value = value.get(key[len(s.key) + 1 :])
    if value is None:
        return None, "unset"
    return value, source


class SettingOption(click.Option):
    """An option whose default comes from the config file, below its env var."""

    def __init__(self, *args: Any, setting_key: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setting_key = setting_key

    def get_default(self, ctx: click.Context, call: bool = True) -> Any:
        value = file_value(self.setting_key)
        if value is not None:
            return value
        return super().get_default(ctx, call=call)


def option(key: str, *param_decls: str, help: str = "", **kwargs: Any):
    """click.option backed by a setting: env var first, then the config file."""
    s = SETTINGS[key]
    if s.default is not None:
        kwargs.setdefault("default", s.default)
        suffix = f"[config: {key}; default: {s.default}]"
    else:
        suffix = f"[config: {key}]"
    return click.option(
        *param_decls,
        cls=SettingOption,
        setting_key=key,
        envvar=s.env,
        show_envvar=True,
        help=f"{help or s.help}  {suffix}",
        **kwargs,
    )


BOOLEANS = {"true": True, "yes": True, "on": True, "1": True}
BOOLEANS |= {"false": False, "no": False, "off": False, "0": False}


def interactive_option(help: str):
    """The -i/--interactive flag, with -I/--no-interactive to override the setting."""
    return click.option(
        "-i/-I",
        "--interactive/--no-interactive",
        default=None,
        help=f"{help} -I turns it off.  [config: interactive]",
    )


def in_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def interactive(flag: bool | None) -> bool:
    """The flag if given, else the interactive setting when stdin and stdout are a terminal."""
    if flag is not None:
        return flag
    value, source = resolve("interactive")
    on = BOOLEANS.get(str(value).lower())
    if on is None:
        raise click.ClickException(f"interactive ({source}) must be true or false, not {value!r}")
    return on and in_terminal()
