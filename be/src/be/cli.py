"""Root command group for be."""

from __future__ import annotations

import click

from be.commands.backup import backup
from be.commands.calendar import calendar_group
from be.commands.compare import compare
from be.commands.config import config_group
from be.commands.convert import convert
from be.commands.dns import dns
from be.commands.git import git
from be.commands.jira import jira_group
from be.commands.kube import kube
from be.commands.pr import pr
from be.server import server
from be.commands.todo import todo_group
from be.commands.ws import ws


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """Personal workflow CLI."""


cli.add_command(backup)
cli.add_command(calendar_group)
cli.add_command(compare)
cli.add_command(config_group)
cli.add_command(convert)
cli.add_command(dns)
cli.add_command(git)
cli.add_command(jira_group)
cli.add_command(kube)
cli.add_command(pr)
cli.add_command(server)
cli.add_command(todo_group)
cli.add_command(ws)


def main() -> None:
    cli()
