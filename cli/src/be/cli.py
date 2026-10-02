"""Root command group for be."""

from __future__ import annotations

import click

from be.commands.config import config_group
from be.commands.git import git
from be.commands.pr import pr
from be.commands.ws import ws


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """Personal workflow CLI."""


cli.add_command(config_group)
cli.add_command(git)
cli.add_command(pr)
cli.add_command(ws)


def main() -> None:
    cli()
