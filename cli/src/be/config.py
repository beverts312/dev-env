"""Settings, resolved from CLI flags > env vars > ~/.be/config > defaults."""

from __future__ import annotations

import os
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


SETTINGS = {
    s.key: s
    for s in (
        Setting("work_org", "WORK_ORG", "GitHub org for bare repo names"),
        Setting("git.email", "GIT_EMAIL", "git user.email for `be git author`"),
        Setting("git.name", "GIT_NAME", "git user.name for `be git author`"),
        Setting("pr.dir", "PRS_DIR", "Parent directory for PR checkouts"),
        Setting("claude.model", "BE_CLAUDE_MODEL", "Model passed as claude --model", "claude-opus-5-5"),
        Setting("cmux.bin", "BE_CMUX_BIN", "Path to the cmux binary"),
    )
}


def setting(key: str) -> Setting:
    try:
        return SETTINGS[key]
    except KeyError:
        valid = ", ".join(SETTINGS)
        raise click.BadParameter(f"unknown key {key!r}; valid keys: {valid}") from None


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


def file_value(key: str, data: dict[str, Any] | None = None) -> Any:
    node: Any = load_file() if data is None else data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def resolve(key: str) -> tuple[Any, str]:
    """Return (value, source) where source is env:<VAR>, file, default or unset."""
    s = setting(key)
    if os.environ.get(s.env):
        return os.environ[s.env], f"env:{s.env}"
    value = file_value(key)
    if value is not None:
        return value, "file"
    if s.default is not None:
        return s.default, "default"
    return None, "unset"


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
