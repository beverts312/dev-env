"""`be server`: a local web page with the `pr ls` and `jira ls` tables."""

from __future__ import annotations

import html
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import click

from be import config, jira
from be.commands import jira as jira_command
from be.commands import pr

# (mine, heading) for each table, in page order
TABLES = ((False, "review requests"), (True, "your PRs"))

STYLE = """
body { font: 14px ui-monospace, monospace; margin: 16px; background: #fff; color: #222; }
table { border-collapse: collapse; margin-bottom: 24px; }
th, td { text-align: left; padding: 2px 12px 2px 0; }
tr.selected { background: #dde8ff; }
form { margin: 0; }
.actions { display: flex; gap: 4px; }
.msg { padding: 4px 8px; background: #eee; }
.keys { color: #666; }
@media (prefers-color-scheme: dark) {
  body { background: #111; color: #ddd; }
  tr.selected { background: #233456; }
  .msg { background: #333; }
  .keys { color: #999; }
}
"""

# keyboard parity with `pr ls -i`: arrows/j/k move, enter reviews (or opens an issue), o opens,
# m switches table, a toggles all, r marks your draft ready, u enables auto-merge
SCRIPT = """
const tables = [...document.querySelectorAll("table")];
let t = 0, r = 0;
const rows = () => [...tables[t].querySelectorAll("tr.pr, tr.issue")];
function draw() {
  document.querySelectorAll("tr.selected").forEach(e => e.classList.remove("selected"));
  const row = rows()[r];
  if (row) row.classList.add("selected");
}
document.addEventListener("keydown", e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const row = rows()[r];
  if (e.key === "ArrowDown" || e.key === "j") r = Math.min(r + 1, rows().length - 1);
  else if (e.key === "ArrowUp" || e.key === "k") r = Math.max(r - 1, 0);
  else if (e.key === "m") { t = (t + 1) % tables.length; r = 0; }
  else if (e.key === "a") { location = document.getElementById("all").href; return; }
  else if (e.key === "o" && row) { window.open(row.querySelector("a").href, "_blank"); return; }
  else if (e.key === "Enter" && row) {
    const form = row.querySelector("form");
    if (form) form.submit(); else window.open(row.querySelector("a").href, "_blank");
    return;
  }
  else if ((e.key === "r" || e.key === "u") && row) {
    const form = row.querySelector(`form[action="/${e.key === "r" ? "ready" : "automerge"}"]`);
    if (form) form.submit();
    return;
  }
  else return;
  e.preventDefault();
  draw();
});
draw();
"""


# POST path and button label for each action on your own PRs
MINE_BUTTONS = (("ready", "ready"), ("automerge", "auto-merge"))


def pr_form(action: str, label: str, repo: str, number: int, show_all: bool) -> str:
    return (
        f'<form method="post" action="/{action}">'
        f'<input type="hidden" name="repo" value="{repo}">'
        f'<input type="hidden" name="number" value="{number}">'
        f'<input type="hidden" name="all" value="{int(show_all)}">'
        f"<button>{label}</button></form>"
    )


def pr_table(prs: list[dict], mine: bool, heading: str, show_all: bool) -> str:
    shown, hidden = pr.filter_prs(prs, show_all)
    if hidden:
        heading += f" ({hidden} hidden)"
    out = [f"<h2>{html.escape(heading)}</h2>", "<table>"]
    out.append("<tr>" + "".join(f"<th>{h}</th>" for h in pr.PR_HEADER) + "<th></th></tr>")
    if not shown:
        out.append(f"<tr><td colspan={len(pr.PR_HEADER) + 1}>{pr.EMPTY[mine]}</td></tr>")
    for p in shown:
        url = html.escape(pr.pr_url(p["repo"], p["number"]))
        repo = html.escape(p["repo"])
        forms = [pr_form("review", "review", repo, p["number"], show_all)]
        if mine:
            # only drafts can be marked ready, and GitHub won't auto-merge a draft
            action, label = MINE_BUTTONS[0] if p["draft"] else MINE_BUTTONS[1]
            forms.append(pr_form(action, label, repo, p["number"], show_all))
        cells = [
            f'<a href="{url}" target="_blank">#{p["number"]}</a>',
            repo,
            html.escape(p["author"]),
            html.escape(p["checks"]),
            html.escape(p["title"]),
            '<div class="actions">' + "".join(forms) + "</div>",
        ]
        out.append('<tr class="pr">' + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    out.append("</table>")
    return "\n".join(out)


ISSUE_HEADER = ("ISSUE", "TYPE", "SUMMARY")


def issue_table(issues: list[dict] | str, show_all: bool) -> str:
    """The `jira ls` table; issues is the error message when the lookup failed."""
    heading = "jira issues"
    if isinstance(issues, str):
        shown, hidden = [], 0
        empty = f"jira: {issues}"
    else:
        shown, hidden = jira_command.filter_issues(issues, show_all)
        empty = jira_command.EMPTY
    if hidden:
        heading += f" ({hidden} hidden)"
    out = [f"<h2>{html.escape(heading)}</h2>", "<table>"]
    out.append("<tr>" + "".join(f"<th>{h}</th>" for h in ISSUE_HEADER) + "</tr>")
    if not shown:
        out.append(f"<tr><td colspan={len(ISSUE_HEADER)}>{html.escape(empty)}</td></tr>")
    for issue in shown:
        url = html.escape(jira.issue_url(issue["key"]))
        cells = [
            f'<a href="{url}" target="_blank">{html.escape(issue["key"])}</a>',
            html.escape(issue["type"]),
            html.escape(issue["summary"]),
        ]
        out.append('<tr class="issue">' + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    out.append("</table>")
    return "\n".join(out)


def render_page(
    fetched: dict[bool, list[dict]],
    show_all: bool,
    message: str = "",
    issues: list[dict] | str = (),
) -> str:
    """Both `pr ls` tables and the `jira ls` table, with links for the `-i` actions."""
    toggle = "/" if show_all else "/?all=1"
    links = (
        f'<a id="all" href="{toggle}">{"filter" if show_all else "show all"}</a>'
        f' · <a href="/refresh?all={int(show_all)}">refresh</a>'
    )
    parts = [
        "<!doctype html><html><head><meta charset=utf-8>",
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>be</title><style>{STYLE}</style></head><body>",
        f"<p>{links}</p>",
        '<p class="keys">j/k move · enter review or open issue · o open in browser · r mark your draft ready · u enable auto-merge on your PR · m switch table · a toggle all</p>',
    ]
    if message:
        parts.append(f'<p class="msg">{html.escape(message)}</p>')
    for mine, heading in TABLES:
        parts.append(pr_table(fetched[mine], mine, heading, show_all))
    parts.append(issue_table(issues, show_all))
    parts.append(f"<script>{SCRIPT}</script></body></html>")
    return "\n".join(parts)


def make_handler(parent: str | None) -> type[BaseHTTPRequestHandler]:
    # each list is fetched once, like `pr ls -i`; /refresh clears it
    fetched: dict[bool, list[dict]] = {}
    # the jira issues, or the error message from looking them up
    issues: list[list[dict] | str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            pass

        def redirect(self, show_all: bool, message: str = "") -> None:
            query = {"all": 1} if show_all else {}
            if message:
                query["msg"] = message
            self.send_response(303)
            self.send_header("Location", "/" + ("?" + urlencode(query) if query else ""))
            self.end_headers()

        def do_GET(self) -> None:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            show_all = query.get("all") == ["1"]
            if url.path == "/refresh":
                fetched.clear()
                issues.clear()
                self.redirect(show_all)
                return
            if url.path != "/":
                self.send_error(404)
                return
            for mine, _ in TABLES:
                if mine not in fetched:
                    fetched[mine] = pr.fetch_prs(mine)
            if not issues:
                try:
                    issues.append(jira.in_progress_issues())
                except jira.JiraError as e:
                    issues.append(str(e))
            body = render_page(fetched, show_all, query.get("msg", [""])[0], issues[0]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path not in ("/review", *(f"/{a}" for a in pr.MINE_ACTIONS)):
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", 0))
            form = parse_qs(self.rfile.read(length).decode())
            repo = form.get("repo", [""])[0]
            number = form.get("number", [""])[0]
            show_all = form.get("all") == ["1"]
            if not repo or not number.isdigit():
                self.send_error(400)
                return
            if path != "/review":
                self.mine_action(path[1:], repo, int(number), show_all)
                return
            try:
                pr.open_review(repo, int(number), parent)
            except click.ClickException as e:
                self.redirect(show_all, f"{repo}#{number}: {e.format_message()}")
                return
            self.redirect(show_all, f"opened {repo}#{number}")

        def mine_action(self, action: str, repo: str, number: int, show_all: bool) -> None:
            if True not in fetched:
                fetched[True] = pr.fetch_prs(True)
            found = [p for p in fetched[True] if p["repo"] == repo and p["number"] == number]
            if not found:
                self.redirect(show_all, f"{repo}#{number} is not one of your open PRs")
                return
            try:
                message = pr.run_mine_action(action, found[0])
            except click.ClickException as e:
                message = f"{repo}#{number}: {e.format_message()}"
            # drafts and checks may have changed
            fetched.pop(True, None)
            self.redirect(show_all, message)

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
def server(parent: str | None, host: str, port: int, no_open: bool) -> None:
    """Serve a web page with the `pr ls` tables and the `jira ls` table.

    Each PR can be reviewed (as `pr review`) or opened on GitHub, and each of
    your PRs marked ready (drafts) or set to auto-merge; each issue
    opened in Jira, and the filters toggle like `pr ls -i`. Ctrl-C stops it.
    """
    httpd = HTTPServer((host, port), make_handler(parent))
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
