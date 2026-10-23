"""`be config`: inspect and edit ~/.be/config."""

from __future__ import annotations

import os

import click
import tomli_w

from be import config


def complete_key(ctx, param, incomplete: str) -> list[str]:
    return [key for key in config.SETTINGS if key.startswith(incomplete)]


key_argument = click.argument("key", shell_complete=complete_key)


def template() -> str:
    """A commented config with every setting, prefilled from the environment."""
    lines = ["# be configuration. Env vars override values set here.", ""]
    section = None
    for s in config.SETTINGS.values():
        table, _, name = s.key.rpartition(".")
        if table != section:
            if table:
                lines += ["", f"[{table}]"]
            section = table
        # only env values are written live; built-in defaults stay commented
        # so the file doesn't pin them
        value = config.env_value(s) if os.environ.get(s.env) else None
        if s.kind == "map":
            lines += ["", f"[{s.key}]", f"# {s.help} (env: {s.env}, as JSON)"]
            lines.append(tomli_w.dumps(value).strip() if value else '# KEY = "description"')
            section = s.key
            continue
        lines.append(f"# {s.help} (env: {s.env})")
        entry = tomli_w.dumps({name: value or s.default or ""}).strip()
        lines.append(entry if value else f"# {entry}")
    return "\n".join(lines) + "\n"


@click.group(name="config")
def config_group() -> None:
    """Inspect and edit the config file (~/.be/config, or $BE_CONFIG)."""


@config_group.command()
def path() -> None:
    """Print the config file path."""
    click.echo(config.config_path())


@config_group.command(name="list")
def list_() -> None:
    """Show every setting, its effective value, and where it came from."""
    rows = []
    for key in config.SETTINGS:
        value, source = config.resolve(key)
        if config.SETTINGS[key].secret and value is not None:
            value = "********"
        if isinstance(value, dict):
            rows += [(f"{key}.{name}", v, source) for name, v in value.items()] or [(key, None, "unset")]
        else:
            rows.append((key, value, source))
    width = max(len(key) for key, _, _ in rows)
    for key, value, source in rows:
        shown = "" if value is None else value
        click.echo(f"{key:<{width}}  {shown!s:<40}  {source}")


@config_group.command()
@key_argument
@click.option("--source", is_flag=True, help="Also print where the value came from.")
def get(key: str, source: bool) -> None:
    """Print the effective value of KEY."""
    value, origin = config.resolve(key)
    if value is None or value == {}:
        raise click.exceptions.Exit(1)
    lines = [f"{name}\t{v}" for name, v in value.items()] if isinstance(value, dict) else [value]
    for line in lines:
        click.echo(f"{line}\t{origin}" if source else line)


@config_group.command(name="set")
@key_argument
@click.argument("value")
def set_(key: str, value: str) -> None:
    """Write KEY = VALUE to the config file. Map entries are set as KEY.NAME."""
    if config.set_value(key, value):
        click.echo(f"warning: {config.setting(key).env} is set and overrides this value", err=True)


@config_group.command()
@key_argument
def unset(key: str) -> None:
    """Remove KEY from the config file."""
    config.unset_value(key)


@config_group.command()
@click.option("--force", is_flag=True, help="Overwrite an existing config file.")
def init(force: bool) -> None:
    """Write a commented config file prefilled from the environment."""
    path = config.config_path()
    if path.exists() and not force:
        raise click.ClickException(f"{path} already exists; use --force to overwrite")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(template())
    path.chmod(0o600)
    click.echo(f"wrote {path}")


@config_group.command()
def edit() -> None:
    """Open the config file in $EDITOR, creating it if needed."""
    path = config.config_path()
    if not path.exists():
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_text(template())
    path.chmod(0o600)
    click.edit(filename=str(path))
    config.load_file()
