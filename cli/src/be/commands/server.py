"""`be server`: a local web page with the `pr ls` and `jira ls` tables."""

from __future__ import annotations

import html
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import click

from be import config, jira
from be.commands import jira as jira_command
from be.commands import pr
from be.github import same_login

# (id, heading) for each table, in page order
TABLES = (("review", "review requests"), ("mine", "your PRs"), ("jira", "jira issues"))
# which PR list each PR table shows, as pr.fetch_prs(mine)
MINE = {"review": False, "mine": True}

# (key, label, hides) for each table's filter checkboxes, matching pr.filter_prs and
# jira_command.filter_issues; a row is hidden while any checked filter hides it
PR_FILTERS = (
    ("checks", "passing checks", lambda p: p["checks"] != "pass"),
    ("draft", "not drafts", lambda p: p["draft"]),
    ("renovate", f"not by {pr.RENOVATE_USER}", lambda p: same_login(p["author"], pr.RENOVATE_USER)),
)
ISSUE_FILTERS = (
    ("feature", f"not {jira_command.FEATURE}s", lambda i: i["type"] == jira_command.FEATURE),
)

STYLE = """
body { font: 14px ui-monospace, monospace; margin: 16px; background: #fff; color: #222; }
h2 { margin-bottom: 4px; }
h2 a { font-size: 14px; font-weight: normal; }
table { border-collapse: collapse; margin-bottom: 24px; }
th, td { text-align: left; padding: 2px 12px 2px 0; }
tr.selected { background: #dde8ff; }
tr.filtered { display: none; }
form { margin: 0; }
.actions { display: flex; gap: 4px; }
.filters { display: flex; gap: 12px; margin-bottom: 8px; }
.msg { padding: 4px 8px; background: #eee; }
.keys, .empty { color: #666; }
@media (prefers-color-scheme: dark) {
  body { background: #111; color: #ddd; }
  tr.selected { background: #233456; }
  .msg { background: #333; }
  .keys, .empty { color: #999; }
}
"""

# keyboard parity with `pr ls -i`: arrows/j/k move, enter reviews (or opens an issue), o opens,
# m switches table, a toggles the table's filters, r marks your draft ready, u enables auto-merge;
# filters apply here and are remembered per table in localStorage
SCRIPT = """
const sections = [...document.querySelectorAll("section")];
let t = 0, r = 0;
const rows = () => [...sections[t].querySelectorAll("tr.pr:not(.filtered), tr.issue:not(.filtered)")];
const boxes = s => [...s.querySelectorAll(".filters input")];
const storeKey = (s, box) => `be.filter.${s.dataset.table}.${box.name}`;
function applyFilters(s) {
  const on = boxes(s).filter(b => b.checked).map(b => b.name);
  let hidden = 0;
  s.querySelectorAll("tr.pr, tr.issue").forEach(row => {
    const hide = (row.dataset.hide || "").split(" ").some(k => on.includes(k));
    row.classList.toggle("filtered", hide);
    hidden += hide;
  });
  const count = s.querySelector(".hidden-count");
  if (count) count.textContent = hidden ? ` (${hidden} hidden)` : "";
}
function draw() {
  document.querySelectorAll("tr.selected").forEach(e => e.classList.remove("selected"));
  r = Math.max(0, Math.min(r, rows().length - 1));
  const row = rows()[r];
  if (row) row.classList.add("selected");
}
sections.forEach(s => {
  boxes(s).forEach(box => {
    try { const v = localStorage.getItem(storeKey(s, box)); if (v !== null) box.checked = v === "1"; } catch {}
    box.addEventListener("change", () => {
      try { localStorage.setItem(storeKey(s, box), box.checked ? "1" : "0"); } catch {}
      applyFilters(s);
      draw();
    });
  });
  applyFilters(s);
});
document.addEventListener("keydown", e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const row = rows()[r];
  if (e.key === "ArrowDown" || e.key === "j") r = Math.min(r + 1, rows().length - 1);
  else if (e.key === "ArrowUp" || e.key === "k") r = Math.max(r - 1, 0);
  else if (e.key === "m") { t = (t + 1) % sections.length; r = 0; }
  else if (e.key === "a") {
    // like --all: clear every filter, or turn them all back on
    const bs = boxes(sections[t]);
    const on = !bs.some(b => b.checked);
    bs.forEach(b => { if (b.checked !== on) { b.checked = on; b.dispatchEvent(new Event("change")); } });
    r = 0;
  }
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


def pr_form(action: str, label: str, repo: str, number: int) -> str:
    return (
        f'<form method="post" action="/{action}">'
        f'<input type="hidden" name="repo" value="{repo}">'
        f'<input type="hidden" name="number" value="{number}">'
        f"<button>{label}</button></form>"
    )


def hide_attr(item: dict, filters: tuple) -> str:
    """The data-hide attribute naming the filters that hide item, if any."""
    keys = [key for key, _, hides in filters if hides(item)]
    return f' data-hide="{" ".join(keys)}"' if keys else ""


def section(table: str, heading: str, filters: tuple, rows: list[str]) -> list[str]:
    """The heading with its refresh link and filter checkboxes; the caller adds the table."""
    boxes = "".join(
        f'<label><input type="checkbox" name="{key}" checked> {html.escape(label)}</label>'
        for key, label, _ in filters
    )
    return [
        f'<section data-table="{table}">',
        f'<h2>{html.escape(heading)}<span class="hidden-count"></span>'
        f' <a href="/refresh?table={table}">refresh</a></h2>',
        f'<div class="filters">{boxes}</div>',
        "<table>",
        *rows,
        "</table></section>",
    ]


def empty_row(header: tuple, colspan: int, message: str) -> list[str]:
    return [
        "<tr>" + "".join(f"<th>{h}</th>" for h in header) + "<th></th>" * (colspan - len(header)) + "</tr>",
        f'<tr><td class="empty" colspan={colspan}>{html.escape(message)}</td></tr>',
    ]


NOT_LOADED = "not loaded; refresh to load"


def pr_table(table: str, heading: str, prs: list[dict] | str | None) -> str:
    """A `pr ls` table; prs is None before it's loaded, or the error message when that failed."""
    mine = MINE[table]
    colspan = len(pr.PR_HEADER) + 1
    if not prs or isinstance(prs, str):
        if prs is None:
            message = NOT_LOADED
        else:
            message = f"github: {prs}" if prs else pr.EMPTY[mine]
        return "\n".join(section(table, heading, PR_FILTERS, empty_row(pr.PR_HEADER, colspan, message)))
    out = ["<tr>" + "".join(f"<th>{h}</th>" for h in pr.PR_HEADER) + "<th></th></tr>"]
    for p in prs:
        url = html.escape(pr.pr_url(p["repo"], p["number"]))
        repo = html.escape(p["repo"])
        forms = [pr_form("review", "review", repo, p["number"])]
        if mine:
            # only drafts can be marked ready, and GitHub won't auto-merge a draft
            action, label = MINE_BUTTONS[0] if p["draft"] else MINE_BUTTONS[1]
            forms.append(pr_form(action, label, repo, p["number"]))
        cells = [
            f'<a href="{url}" target="_blank">#{p["number"]}</a>',
            repo,
            html.escape(p["author"]),
            html.escape(p["checks"]),
            html.escape(p["title"]),
            '<div class="actions">' + "".join(forms) + "</div>",
        ]
        out.append(
            f'<tr class="pr"{hide_attr(p, PR_FILTERS)}>' + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"
        )
    return "\n".join(section(table, heading, PR_FILTERS, out))


ISSUE_HEADER = ("ISSUE", "TYPE", "SUMMARY")


def issue_table(heading: str, issues: list[dict] | str | None) -> str:
    """The `jira ls` table; issues is None before it's loaded, or the error message when that failed."""
    if not issues or isinstance(issues, str):
        if issues is None:
            message = NOT_LOADED
        else:
            message = f"jira: {issues}" if issues else jira_command.EMPTY
        rows = empty_row(ISSUE_HEADER, len(ISSUE_HEADER), message)
        return "\n".join(section("jira", heading, ISSUE_FILTERS, rows))
    out = ["<tr>" + "".join(f"<th>{h}</th>" for h in ISSUE_HEADER) + "</tr>"]
    for issue in issues:
        url = html.escape(jira.issue_url(issue["key"]))
        cells = [
            f'<a href="{url}" target="_blank">{html.escape(issue["key"])}</a>',
            html.escape(issue["type"]),
            html.escape(issue["summary"]),
        ]
        out.append(
            f'<tr class="issue"{hide_attr(issue, ISSUE_FILTERS)}>'
            + "".join(f"<td>{c}</td>" for c in cells)
            + "</tr>"
        )
    return "\n".join(section("jira", heading, ISSUE_FILTERS, out))


def render_page(loaded: dict[str, list[dict] | str], message: str = "") -> str:
    """The `pr ls` tables and the `jira ls` table, each loaded on refresh, with the `-i` actions."""
    parts = [
        "<!doctype html><html><head><meta charset=utf-8>",
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>be</title><style>{STYLE}</style></head><body>",
        '<p class="keys">j/k move · enter review or open issue · o open in browser · r mark your draft ready · u enable auto-merge on your PR · m switch table · a toggle filters</p>',
    ]
    if message:
        parts.append(f'<p class="msg">{html.escape(message)}</p>')
    for table, heading in TABLES:
        if table == "jira":
            parts.append(issue_table(heading, loaded.get(table)))
        else:
            parts.append(pr_table(table, heading, loaded.get(table)))
    parts.append(f"<script>{SCRIPT}</script></body></html>")
    return "\n".join(parts)


def fetch_table(table: str) -> list[dict] | str:
    """The table's rows, or the error message from looking them up."""
    try:
        if table == "jira":
            return jira.in_progress_issues()
        return pr.fetch_prs(MINE[table])
    except click.ClickException as e:
        return e.format_message()
    except jira.JiraError as e:
        return str(e)


def make_handler(parent: str | None) -> type[BaseHTTPRequestHandler]:
    # each table is fetched only when its refresh link is clicked, then kept
    loaded: dict[str, list[dict] | str] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            pass

        def redirect(self, message: str = "") -> None:
            self.send_response(303)
            self.send_header("Location", "/" + ("?" + urlencode({"msg": message}) if message else ""))
            self.end_headers()

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
            if url.path != "/":
                self.send_error(404)
                return
            body = render_page(loaded, query.get("msg", [""])[0]).encode()
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
            if not repo or not number.isdigit():
                self.send_error(400)
                return
            if path != "/review":
                self.mine_action(path[1:], repo, int(number))
                return
            try:
                pr.open_review(repo, int(number), parent)
            except click.ClickException as e:
                self.redirect(f"{repo}#{number}: {e.format_message()}")
                return
            self.redirect(f"opened {repo}#{number}")

        def mine_action(self, action: str, repo: str, number: int) -> None:
            if not isinstance(loaded.get("mine"), list):
                loaded["mine"] = fetch_table("mine")
            mine = loaded["mine"] if isinstance(loaded["mine"], list) else []
            found = [p for p in mine if p["repo"] == repo and p["number"] == number]
            if not found:
                self.redirect(f"{repo}#{number} is not one of your open PRs")
                return
            try:
                message = pr.run_mine_action(action, found[0])
            except click.ClickException as e:
                message = f"{repo}#{number}: {e.format_message()}"
            # drafts and checks may have changed
            loaded["mine"] = fetch_table("mine")
            self.redirect(message)

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
    opened in Jira. Each table loads when you click its refresh link, and its
    filter checkboxes apply in the page. Ctrl-C stops it.
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
