"""`be server`: a local web app with your Jira issues, the `pr ls` tables, your workspaces, and a config page."""

from __future__ import annotations

import logging

import click
import uvicorn
from click.core import ParameterSource

from be import config
from be.commands import pr
from be.server.api import LOG_LEVELS, State
from be.server.app import create_app

# where `pnpm dev` in be/web serves the app, proxying /api to the server
DEV_URL = "http://localhost:5173"


@click.command()
@config.option(
    "pr.dir",
    "--parent",
    help="Parent folder to clone into when reviewing (default: current directory).",
)
@click.option("--host", default="127.0.0.1", show_default=True, help="Address to listen on.")
@click.option("--port", default=8765, show_default=True, help="Port to listen on.")
@click.option("--no-open", is_flag=True, help="Don't open the app in a browser.")
@click.option(
    "--dev",
    is_flag=True,
    help=f"Serve only the API, for `pnpm -C be/web dev`, and open its app at {DEV_URL}.",
)
@config.option(
    "server.log_level",
    "--log-level",
    type=click.Choice(LOG_LEVELS, case_sensitive=False),
    help="Log requests (info), fetches and gh calls (debug), and failures and retries (warning).",
)
@pr.agent_option()
@pr.model_options
def server(
    parent: str | None,
    host: str,
    port: int,
    no_open: bool,
    dev: bool,
    log_level: str,
    agent: str,
    claude_model: str | None,
    cursor_model: str | None,
) -> None:
    """Serve a web app with your Jira issues, the `pr ls` tables, and your workspaces, on four pages.

    A sidebar switches between my work (the Jira tree), my PRs, reviews, and workspaces.
    Each PR can be reviewed (as `pr review`) or opened on GitHub, and each of
    your PRs marked ready (drafts), set to auto-merge, or merged (approved),
    one at a time or checked and done in bulk; each issue
    opened in Jira, or its workspace opened or created. The Jira tree loads the first time it's shown,
    and the workspaces in ws.dir every time; the PR tables load when you refresh them. The config page
    edits the config file, one setting at a time; pr.dir, server.log_level, pr.agent,
    claude.pr.model and cursor.pr.model apply at once unless --parent,
    --log-level, --agent, --claude-model or --cursor-model was given. The reviews
    page's agent toggle overrides that choice for a review started from the page.
    /mcp serves an MCP server with tools for managing your todos, as `be todo` does.
    Ctrl-C stops it.
    """
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # only be's own loggers, so --log-level debug doesn't turn on libraries' debug output
    logging.getLogger("be").setLevel(log_level.upper())
    ctx = click.get_current_context()
    params = {
        "pr.dir": "parent",
        "server.log_level": "log_level",
        "pr.agent": "agent",
        "claude.pr.model": "claude_model",
        "cursor.pr.model": "cursor_model",
    }
    fixed = tuple(
        key for key, param in params.items()
        if ctx.get_parameter_source(param) == ParameterSource.COMMANDLINE
    )
    state = State(parent, fixed, agent, claude_model, cursor_model)
    app = create_app(state, static=None, host=host) if dev else create_app(state, host=host)
    url = DEV_URL if dev else f"http://{host}:{port}"
    click.echo(f"serving the API on http://{host}:{port}; the app is at {url}" if dev else f"serving on {url}")
    if not no_open:
        click.launch(url)
    # be logs its own requests; uvicorn's logging would replace basicConfig's
    uvicorn.run(app, host=host, port=port, log_config=None, access_log=False, log_level="warning")
