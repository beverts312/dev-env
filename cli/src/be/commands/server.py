"""`be server`: a local web page with the `pr ls` and `jira ls` tables, your workspaces, and a config page."""

from __future__ import annotations

import logging
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import click
from click.core import ParameterSource

from be import config, jira
from be.commands import pr, ws
from be.commands.page import (
    FLAGS,
    MINE_BUTTONS,
    MINE_PATHS,
    TABLES,
    mine_actions,
    render_config,
    render_page,
)

log = logging.getLogger(__name__)

LOG_LEVELS = config.SETTINGS["server.log_level"].choices


def save_setting(form: dict, unset: bool) -> str:
    """Set or unset the posted key (a map setting's key with a name adds that entry), and say what happened."""
    key = form.get("key", [""])[0]
    value = form.get("value", [""])[0].strip()
    name = form.get("name", [""])[0].strip()
    try:
        s = config.setting(key)
        if s.kind == "map" and key == s.key:
            if not name or "." in name:
                return f"{key}: give the new entry a name, without dots"
            key = f"{key}.{name}"
        if unset or not value:
            config.unset_value(key)
            log.info("removed %s from the config", key)
            return f"removed {key}"
        if s.choices and value not in s.choices:
            return f"{key} must be one of {', '.join(s.choices)}, not {value!r}"
        overridden = config.set_value(key, value)
    except click.ClickException as e:
        return f"{key}: {e.message}"
    log.info("set %s in the config", key)
    return f"saved {key}" + (f"; {s.env} is set and overrides it" if overridden else "")


def workspace_rows() -> list[dict]:
    """Each workspace in ws.dir, with dir set to the directory `ws open` takes."""
    parent, _ = config.resolve("ws.dir")
    return [
        {**ws.workspace_details(entry), "dir": entry.name}
        for entry in ws.workspace_entries(parent)
    ]


def fetch_table(table: str) -> list[dict] | str:
    """The table's rows, or the error message from looking them up."""
    log.debug("fetching %s", table)
    try:
        if table == "jira":
            rows = jira.issue_tree()
        elif table == "workspaces":
            rows = workspace_rows()
        else:
            rows = pr.fetch_prs(table)
    except click.ClickException as e:
        message = e.format_message()
    except jira.JiraError as e:
        message = str(e)
    else:
        log.info("fetched %d rows for %s", len(rows), table)
        return rows
    log.warning("fetching %s failed: %s", table, message)
    return message


def make_handler(
    parent: str | None,
    fixed: tuple[str, ...] = tuple(FLAGS),
    agent: str = "claude",
    claude_model: str | None = None,
    cursor_model: str | None = None,
) -> type[BaseHTTPRequestHandler]:
    """fixed names the settings in FLAGS given as flags, which keep their value; the rest are reread when used."""
    # each table is fetched only when its refresh link is clicked, then kept
    loaded: dict[str, list[dict] | str] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            log.info("%s %s", self.address_string(), format % args)

        def redirect(self, message: str = "", path: str = "/") -> None:
            self.send_response(303)
            self.send_header("Location", path + ("?" + urlencode({"msg": message}) if message else ""))
            self.end_headers()

        def send_page(self, page: str) -> None:
            body = page.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == "/refresh":
                table = query.get("table", [""])[0]
                if table not in dict(TABLES):
                    self.send_error(404)
                    return
                loaded[table] = fetch_table(table)
                self.redirect()
                return
            message = query.get("msg", [""])[0]
            if url.path == "/config":
                self.send_page(render_config(message, fixed))
            elif url.path == "/":
                # local directories, so they show without a refresh, and the tree finds issues' workspaces
                loaded["workspaces"] = fetch_table("workspaces")
                # my work's tree loads with the page the first time; its refresh link fetches it again
                if "jira" not in loaded:
                    loaded["jira"] = fetch_table("jira")
                self.send_page(render_page(loaded, message, self.agent()))
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path not in ("/review", "/bulk", "/open", "/ws/create", "/ws/link", "/config/set", "/config/unset", *MINE_PATHS):
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", 0))
            form = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)
            if path.startswith("/config/"):
                self.config_action(form, unset=path == "/config/unset")
                return
            if path == "/open":
                self.open_action(form)
                return
            if path == "/ws/create":
                self.create_action(form)
                return
            if path == "/ws/link":
                self.link_action(form)
                return
            if path == "/bulk":
                self.bulk_action(form)
                return
            repo = form.get("repo", [""])[0]
            number = form.get("number", [""])[0]
            if not repo or not number.isdigit():
                self.send_error(400)
                return
            if path != "/review":
                self.mine_action(path[1:], repo, int(number))
                return
            try:
                claude_model, cursor_model = self.models()
                pr.open_review(
                    repo,
                    int(number),
                    self.parent(),
                    self.review_agent(form),
                    claude_model,
                    cursor_model,
                )
            except click.ClickException as e:
                log.warning("reviewing %s#%s failed: %s", repo, number, e.format_message())
                self.redirect(f"{repo}#{number}: {e.format_message()}")
                return
            log.info("opened %s#%s for review", repo, number)
            self.redirect(f"opened {repo}#{number}")

        def parent(self) -> str | None:
            """--parent if given, else pr.dir as it's set now."""
            return parent if "pr.dir" in fixed else config.resolve("pr.dir")[0]

        def agent(self) -> str:
            """--agent if given, else pr.agent as it's set now. The reviews page's toggle starts here."""
            return agent if "pr.agent" in fixed else config.resolve("pr.agent")[0]

        def review_agent(self, form: dict) -> str:
            """The reviews page's toggle when the form posted claude or cursor, else agent()."""
            chosen = form.get("agent", [""])[0].strip().lower()
            return chosen if chosen in pr.AGENTS else self.agent()

        def models(self) -> tuple[str | None, str | None]:
            """--claude-model and --cursor-model if given, else the settings as they're set now."""

            def one(key: str, given: str | None) -> str | None:
                return given if key in fixed else config.resolve(key)[0]

            return one("claude.pr.model", claude_model), one("cursor.pr.model", cursor_model)

        def config_action(self, form: dict, unset: bool) -> None:
            message = save_setting(form, unset)
            if "server.log_level" not in fixed:
                # a saved log level applies now, unless its env var still wins
                level, _ = config.resolve("server.log_level")
                if str(level).lower() in LOG_LEVELS:
                    logging.getLogger("be").setLevel(str(level).upper())
            self.redirect(message, "/config")

        def mine_prs(self) -> list[dict]:
            if not isinstance(loaded.get("mine"), list):
                loaded["mine"] = fetch_table("mine")
            return loaded["mine"] if isinstance(loaded["mine"], list) else []

        def run_action(self, action: str, repo: str, number: int, bulk: bool = False) -> str:
            """Run action on your PR; in bulk, a PR the action isn't offered on is skipped."""
            mine = self.mine_prs()
            found = [p for p in mine if p["repo"] == repo and p["number"] == number]
            if not found:
                return f"{repo}#{number} is not one of your open PRs"
            if bulk and action not in mine_actions(found[0]):
                return f"skipped {repo}#{number}: no {MINE_BUTTONS[action]} on it"
            try:
                message = pr.run_mine_action(action, found[0])
            except click.ClickException as e:
                log.warning("%s on %s#%s failed: %s", action, repo, number, e.format_message())
                return f"{repo}#{number}: {e.format_message()}"
            log.info("%s#%s: %s", repo, number, message)
            # run_mine_action updates the row in place rather than us refetching
            # the table, so a PR marked ready offers auto-merge next, and one set
            # to auto-merge offers nothing; a merged one is dropped
            if message.startswith("merged"):
                mine.remove(found[0])
            return message

        def open_action(self, form: dict) -> None:
            """Open a workspace directory in ws.dir, as `ws open` does."""
            name = form.get("name", [""])[0]
            if not name or "/" in name or name in (".", ".."):
                self.send_error(400)
                return
            try:
                parent, _ = config.resolve("ws.dir")
                entries = {entry.name: entry for entry in ws.workspace_entries(parent)}
                root = entries.get(name)
                if root is None:
                    raise click.ClickException(f"{name} is not a workspace")
                window, _ = config.resolve("cmux.window")
                ws.open_root(root, window=window)
            except click.ClickException as e:
                log.warning("opening workspace %s failed: %s", name, e.format_message())
                self.redirect(f"{name}: {e.format_message()}")
                return
            log.info("opened workspace %s", name)
            self.redirect(f"opened {name}")

        def create_action(self, form: dict) -> None:
            """Create a workspace in ws.dir and open it, as `ws create` does; the tree's dialog posts
            its name, repos, extra dirs, description, and the issue summary to name it after."""

            def field(key: str) -> str:
                return form.get(key, [""])[0].strip()

            name = field("name")
            if not name or "/" in name or name in (".", ".."):
                self.send_error(400)
                return
            try:
                parent, _ = config.resolve("ws.dir")
                if any(entry.name == name for entry in ws.workspace_entries(parent)):
                    raise click.ClickException(f"{name} already exists")
                model, _ = config.resolve("claude.model")
                org, _ = config.resolve("work_org")
                window, _ = config.resolve("cmux.window")
                # create_workspace changes into the new workspace, which the server shouldn't stay in
                cwd = os.getcwd()
                try:
                    ws.create_workspace(
                        name,
                        field("repos"),
                        field("extra_dirs"),
                        field("description"),
                        parent,
                        model,
                        org,
                        window,
                        field("issue_name") or None,
                    )
                finally:
                    os.chdir(cwd)
            except click.ClickException as e:
                log.warning("creating workspace %s failed: %s", name, e.format_message())
                self.redirect(f"{name}: {e.format_message()}")
                return
            except click.exceptions.Exit:
                log.warning("creating workspace %s failed: cmux could not save its layout", name)
                self.redirect(f"{name}: created, but cmux could not save its layout")
                return
            log.info("created workspace %s", name)
            self.redirect(f"created {name}")

        def link_action(self, form: dict) -> None:
            """Link the posted issue key to an existing workspace in ws.dir, then open it."""
            name = form.get("name", [""])[0]
            key = form.get("key", [""])[0].strip().upper()
            if not name or "/" in name or name in (".", "..") or not jira.ISSUE_KEY.fullmatch(key):
                self.send_error(400)
                return
            try:
                parent, _ = config.resolve("ws.dir")
                entries = {entry.name: entry for entry in ws.workspace_entries(parent)}
                root = entries.get(name)
                if root is None:
                    raise click.ClickException(f"{name} is not a workspace")
                ws.link_issue(root, key)
                log.info("linked %s to workspace %s", key, name)
                window, _ = config.resolve("cmux.window")
                ws.open_root(root, window=window)
            except click.ClickException as e:
                log.warning("linking %s to workspace %s failed: %s", key, name, e.format_message())
                self.redirect(f"{name}: {e.format_message()}")
                return
            except OSError as e:
                log.warning("linking %s to workspace %s failed: %s", key, name, e)
                self.redirect(f"{name}: could not save the link: {e.strerror or e}")
                return
            self.redirect(f"linked {key} to {name}; opened {name}")

        def mine_action(self, action: str, repo: str, number: int) -> None:
            self.redirect(self.run_action(action, repo, number))

        def bulk_action(self, form: dict) -> None:
            action = form.get("action", [""])[0]
            picked = [value.rpartition("#") for value in form.get("pr", [])]
            if action not in MINE_BUTTONS or any(not n.isdigit() or not r for r, _, n in picked):
                self.send_error(400)
                return
            if not picked:
                self.redirect("no PRs selected")
                return
            messages = [self.run_action(action, r, int(n), bulk=True) for r, _, n in picked]
            self.redirect("; ".join(messages))

    return Handler


@click.command()
@config.option(
    "pr.dir",
    "--parent",
    help="Parent folder to clone into when reviewing (default: current directory).",
)
@click.option("--host", default="127.0.0.1", show_default=True, help="Address to listen on.")
@click.option("--port", default=8765, show_default=True, help="Port to listen on.")
@click.option("--no-open", is_flag=True, help="Don't open the page in a browser.")
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
    log_level: str,
    agent: str,
    claude_model: str | None,
    cursor_model: str | None,
) -> None:
    """Serve a web page with your Jira issues, the `pr ls` tables, and your workspaces, on four pages.

    A collapsible sidebar switches between my work (the Jira tree), my PRs, reviews, and workspaces.
    Each PR can be reviewed (as `pr review`) or opened on GitHub, and each of
    your PRs marked ready (drafts), set to auto-merge, or merged (approved),
    one at a time or checked and done in bulk; each issue
    opened in Jira. The Jira tree loads with the page the first time, and the workspaces in
    ws.dir every time; clicking a workspace runs `ws open`. The other tables load when you click their
    refresh link, and their filter checkboxes apply in the page. The config page (/config) edits the
    config file, one setting at a time; pr.dir, server.log_level, pr.agent,
    claude.pr.model and cursor.pr.model apply at once unless --parent,
    --log-level, --agent, --claude-model or --cursor-model was given. The reviews
    page's agent toggle overrides that choice for a review started from the page.
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
    httpd = HTTPServer(
        (host, port), make_handler(parent, fixed, agent, claude_model, cursor_model)
    )
    url = f"http://{host}:{httpd.server_port}"
    click.echo(f"serving on {url}")
    if not no_open:
        click.launch(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
