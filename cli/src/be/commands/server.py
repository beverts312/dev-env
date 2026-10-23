"""`be server`: a local web page with the `pr ls` and `jira ls` tables."""

from __future__ import annotations

import html
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import click

from be import config, jira
from be.commands import jira as jira_command
from be.commands import pr
from be.github import same_login

log = logging.getLogger(__name__)

LOG_LEVELS = ("debug", "info", "warning", "error")

# (id, heading) for each table, in page order
TABLES = (("review", "review requests"), ("mine", "your PRs"), ("jira", "jira issues"))
# which PR list each PR table shows, as pr.fetch_prs(mine)
MINE = {"review": False, "mine": True}

# (key, options, default, value) for the PR tables' filter dropdowns, defaulting to what
# pr.filter_prs shows: a row is hidden unless value(row) is the chosen option, or "all" is;
# while one option is chosen the key's column is hidden, as every row would show it
PR_SELECTS = (
    ("checks", ("pass", "fail", "pending", "none"), "pass", lambda p: p["checks"]),
    ("draft", ("no", "yes"), "no", lambda p: "yes" if p["draft"] else "no"),
)
SELECT_ALL = "all"

# (key, label, hides) for each table's filter checkboxes, matching pr.filter_prs and
# jira_command.filter_issues; a row is hidden while any checked filter hides it
PR_FILTERS = (
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
.filters { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.msg { padding: 4px 8px; background: #eee; }
.bulk { display: flex; align-items: center; gap: 4px; margin-bottom: 8px; }
.keys, .empty { color: #666; }
@media (prefers-color-scheme: dark) {
  body { background: #111; color: #ddd; }
  tr.selected { background: #233456; }
  .msg { background: #333; }
  .keys, .empty { color: #999; }
}
""" + "".join(f".hide-{key} .col-{key} {{ display: none; }}\n" for key, *_ in PR_SELECTS)

# keyboard parity with `pr ls -i`: arrows/j/k move, enter reviews (or opens an issue), o opens,
# m switches table, a toggles the table's filters, r marks your draft ready, u enables auto-merge;
# x checks your PR for the bulk bar; filters apply here and are remembered per table in localStorage
SCRIPT = """
const sections = [...document.querySelectorAll("section")];
let t = 0, r = 0;
const rows = () => [...sections[t].querySelectorAll("tr.pr:not(.filtered), tr.issue:not(.filtered)")];
const boxes = s => [...s.querySelectorAll(".filters input[type=checkbox]")];
const selects = s => [...s.querySelectorAll(".filters select")];
const storeKey = (s, box) => `be.filter.${s.dataset.table}.${box.name}`;
function applyFilters(s) {
  const on = boxes(s).filter(b => b.checked).map(b => b.name);
  // a dropdown set to one value hides the rows without it, and its column
  const picked = selects(s).filter(x => x.value !== "all");
  selects(s).forEach(x => s.classList.toggle(`hide-${x.name}`, x.value !== "all"));
  const search = s.querySelector(".filters input[type=search]");
  const text = search ? search.value.trim().toLowerCase() : "";
  let hidden = 0;
  s.querySelectorAll("tr.pr, tr.issue").forEach(row => {
    const hide = (row.dataset.hide || "").split(" ").some(k => on.includes(k))
      || picked.some(x => row.dataset[x.name] !== x.value)
      || (text !== "" && !(row.dataset.search || "").includes(text));
    row.classList.toggle("filtered", hide);
    // a hidden row is never acted on in bulk
    const pick = row.querySelector("input.pick");
    if (hide && pick) pick.checked = false;
    hidden += hide;
  });
  updateBulk(s);
  const count = s.querySelector(".hidden-count");
  if (count) count.textContent = hidden ? ` (${hidden} hidden)` : "";
}
// the bulk bar acts on the checked rows of your PRs; each button counts the checked rows
// it applies to and is disabled when there are none
function updateBulk(s) {
  const bar = s.querySelector("form.bulk");
  if (!bar) return;
  const picked = [...s.querySelectorAll("input.pick:checked")].map(b => b.closest("tr"));
  bar.querySelector(".picked-count").textContent = `${picked.length} selected`;
  bar.querySelectorAll("button[name=action]").forEach(button => {
    const n = picked.filter(row => row.dataset.actions.split(" ").includes(button.value)).length;
    button.disabled = n === 0;
    button.textContent = `${button.dataset.label} (${n})`;
  });
  const all = s.querySelector("input.pick-all");
  const shown = [...s.querySelectorAll("tr.pr:not(.filtered) input.pick")];
  all.checked = shown.length > 0 && shown.every(b => b.checked);
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
  selects(s).forEach(x => {
    try {
      const v = localStorage.getItem(storeKey(s, x));
      if ([...x.options].some(o => o.value === v)) x.value = v;
    } catch {}
    x.addEventListener("change", () => {
      try { localStorage.setItem(storeKey(s, x), x.value); } catch {}
      applyFilters(s);
      r = 0;
      draw();
    });
  });
  const search = s.querySelector(".filters input[type=search]");
  if (search) {
    try { search.value = localStorage.getItem(storeKey(s, search)) || ""; } catch {}
    search.addEventListener("input", () => {
      try { localStorage.setItem(storeKey(s, search), search.value); } catch {}
      applyFilters(s);
      r = 0;
      draw();
    });
  }
  s.querySelectorAll("input.pick").forEach(b => b.addEventListener("change", () => updateBulk(s)));
  const all = s.querySelector("input.pick-all");
  if (all) all.addEventListener("change", () => {
    s.querySelectorAll("tr.pr:not(.filtered) input.pick").forEach(b => { b.checked = all.checked; });
    updateBulk(s);
  });
  const bar = s.querySelector("form.bulk");
  if (bar) bar.addEventListener("submit", e => {
    if (!e.submitter || e.submitter.value !== "merge") return;
    const n = [...s.querySelectorAll("input.pick:checked")]
      .filter(b => b.closest("tr").dataset.actions.split(" ").includes("merge")).length;
    if (!confirm(`Merge ${n} PR${n === 1 ? "" : "s"}?`)) e.preventDefault();
  });
  applyFilters(s);
});
document.addEventListener("keydown", e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  // typing in the search box doesn't trigger keys; escape or enter goes back to the rows
  if (e.target.type === "search") {
    if (e.key === "Escape" || e.key === "Enter") { e.target.blur(); e.preventDefault(); }
    return;
  }
  // a focused dropdown keeps its own keys
  if (e.target.tagName === "SELECT") return;
  if (e.key === "/") {
    const search = sections[t].querySelector(".filters input[type=search]");
    if (search) { search.focus(); e.preventDefault(); }
    return;
  }
  const row = rows()[r];
  if (e.key === "ArrowDown" || e.key === "j") r = Math.min(r + 1, rows().length - 1);
  else if (e.key === "ArrowUp" || e.key === "k") r = Math.max(r - 1, 0);
  else if (e.key === "m") { t = (t + 1) % sections.length; r = 0; }
  else if (e.key === "a") {
    // like --all: clear every filter, or turn them all back on (dropdowns to their defaults)
    const s = sections[t], bs = boxes(s), xs = selects(s);
    const on = !bs.some(b => b.checked) && !xs.some(x => x.value !== "all");
    const set = (el, prop, v) => { if (el[prop] !== v) { el[prop] = v; el.dispatchEvent(new Event("change")); } };
    bs.forEach(b => set(b, "checked", on));
    xs.forEach(x => set(x, "value", on ? x.dataset.default : "all"));
    r = 0;
  }
  else if (e.key === "o" && row) { window.open(row.querySelector("a").href, "_blank"); return; }
  else if (e.key === "Enter" && row) {
    const form = row.querySelector("form");
    if (form) form.submit(); else window.open(row.querySelector("a").href, "_blank");
    return;
  }
  else if (e.key === "x" && row) {
    const pick = row.querySelector("input.pick");
    if (pick) { pick.checked = !pick.checked; updateBulk(sections[t]); }
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
MINE_BUTTONS = {"ready": "ready", "automerge": "auto-merge", pr.MERGE_ACTION: "merge"}
# your PRs' actions, as POST paths
MINE_PATHS = tuple(f"/{a}" for a in MINE_BUTTONS)
# the bulk bar's form, which your PRs' checkboxes belong to
BULK_FORM = "bulk-mine"


def mine_actions(p: dict) -> list[str]:
    """The actions offered on your PR p: only drafts can be marked ready, GitHub won't
    auto-merge a draft, and nothing is offered once auto-merge is on; approved PRs
    can be merged now."""
    if p["draft"]:
        return ["ready"]
    if p["auto_merge"]:
        return []
    return ["automerge", pr.MERGE_ACTION] if p["approved"] else ["automerge"]


def pr_header(mine: bool) -> tuple[str, ...]:
    """pr.pr_header with the draft column, without the author on your PRs, which are all yours."""
    return tuple(h for h in pr.pr_header(drafts=True) if not (mine and h == "AUTHOR"))


def col_attr(heading: str) -> str:
    """The class that hides a dropdown's column while it shows one value."""
    key = heading.lower()
    return f' class="col-{key}"' if key in {k for k, *_ in PR_SELECTS} else ""


def header_row(header: tuple, blank: int = 0) -> str:
    return "<tr>" + "".join(f"<th{col_attr(h)}>{h}</th>" for h in header) + "<th></th>" * blank + "</tr>"


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


def select_html(key: str, options: tuple, default: str) -> str:
    choices = "".join(
        f'<option value="{o}"{" selected" if o == default else ""}>{o}</option>'
        for o in (SELECT_ALL, *options)
    )
    return f'<label>{key} <select name="{key}" data-default="{default}">{choices}</select></label>'


def bulk_bar() -> str:
    """The form your PRs' checkboxes submit, with a button per action."""
    buttons = "".join(
        f'<button name="action" value="{a}" data-label="{label}" disabled>{label} (0)</button>'
        for a, label in MINE_BUTTONS.items()
    )
    return (
        f'<form id="{BULK_FORM}" class="bulk" method="post" action="/bulk">'
        f'<span class="picked-count">0 selected</span>{buttons}</form>'
    )


def section(
    table: str,
    heading: str,
    filters: tuple,
    rows: list[str],
    search: bool = False,
    selects: tuple = (),
    bulk: str = "",
) -> list[str]:
    """The heading with its refresh link, filter dropdowns and checkboxes, (if search) a
    search box matching rows' data-search, and any bulk bar; the caller adds the table."""
    boxes = "".join(select_html(key, options, default) for key, options, default, _ in selects)
    boxes += "".join(
        f'<label><input type="checkbox" name="{key}" checked> {html.escape(label)}</label>'
        for key, label, _ in filters
    )
    if search:
        boxes += '<input type="search" name="search" placeholder="repo or title" aria-label="search repo or title">'
    return [
        f'<section data-table="{table}">',
        f'<h2>{html.escape(heading)}<span class="hidden-count"></span>'
        f' <a href="/refresh?table={table}">refresh</a></h2>',
        f'<div class="filters">{boxes}</div>',
        bulk,
        "<table>",
        *rows,
        "</table></section>",
    ]


def empty_row(header: tuple, colspan: int, message: str) -> list[str]:
    return [
        header_row(header, colspan - len(header)),
        f'<tr><td class="empty" colspan={colspan}>{html.escape(message)}</td></tr>',
    ]


NOT_LOADED = "not loaded; refresh to load"


def pr_table(table: str, heading: str, prs: list[dict] | str | None) -> str:
    """A `pr ls` table; prs is None before it's loaded, or the error message when that failed."""
    mine = MINE[table]
    header = pr_header(mine)
    colspan = len(header) + 1
    if not prs or isinstance(prs, str):
        if prs is None:
            message = NOT_LOADED
        else:
            message = f"github: {prs}" if prs else pr.EMPTY[mine]
        rows = empty_row(header, colspan, message)
        return "\n".join(section(table, heading, PR_FILTERS, rows, search=True, selects=PR_SELECTS))
    out = [header_row(header, 1)]
    if mine:
        out[0] = out[0].replace(
            "<tr>", '<tr><th><input type="checkbox" class="pick-all" aria-label="select all shown"></th>', 1
        )
    for p in prs:
        url = html.escape(pr.pr_url(p["repo"], p["number"]))
        repo = html.escape(p["repo"])
        forms = [pr_form("review", "review", repo, p["number"])]
        pick = ""
        if mine:
            forms += [pr_form(a, MINE_BUTTONS[a], repo, p["number"]) for a in mine_actions(p)]
            name = f"{repo}#{p['number']}"
            pick = (
                f'<td><input type="checkbox" class="pick" name="pr" value="{name}"'
                f' form="{BULK_FORM}" aria-label="select {name}"></td>'
            )
        values = {key: value(p) for key, _, _, value in PR_SELECTS}
        cells = dict(zip(pr.pr_header(drafts=True), (html.escape(c) for c in pr.pr_cells(p, drafts=True))))
        cells["PR"] = f'<a href="{url}" target="_blank">{cells["PR"]}</a>'
        actions = '<td><div class="actions">' + "".join(forms) + "</div></td>"
        # what the search box matches, case-insensitively, and each dropdown's value
        search = html.escape(f"{p['repo']} {p['title']}".lower())
        data = "".join(f' data-{key}="{html.escape(v)}"' for key, v in values.items())
        if mine:
            data += f' data-actions="{" ".join(mine_actions(p))}"'
        out.append(
            f'<tr class="pr" data-search="{search}"{data}{hide_attr(p, PR_FILTERS)}>'
            + pick
            + "".join(f"<td{col_attr(h)}>{cells[h]}</td>" for h in header)
            + actions
            + "</tr>"
        )
    bulk = bulk_bar() if mine else ""
    return "\n".join(
        section(table, heading, PR_FILTERS, out, search=True, selects=PR_SELECTS, bulk=bulk)
    )


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
        '<p class="keys">j/k move · enter review or open issue · o open in browser · r mark your draft ready · u enable auto-merge on your PR · x check your PR for bulk actions · m switch table · a toggle filters · / search repo or title</p>',
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
    log.debug("fetching %s", table)
    try:
        if table == "jira":
            rows = jira.in_progress_issues()
        else:
            rows = pr.fetch_prs(MINE[table])
    except click.ClickException as e:
        message = e.format_message()
    except jira.JiraError as e:
        message = str(e)
    else:
        log.info("fetched %d rows for %s", len(rows), table)
        return rows
    log.warning("fetching %s failed: %s", table, message)
    return message


def make_handler(parent: str | None) -> type[BaseHTTPRequestHandler]:
    # each table is fetched only when its refresh link is clicked, then kept
    loaded: dict[str, list[dict] | str] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            log.info("%s %s", self.address_string(), format % args)

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
            if path not in ("/review", "/bulk", *MINE_PATHS):
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", 0))
            form = parse_qs(self.rfile.read(length).decode())
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
                pr.open_review(repo, int(number), parent)
            except click.ClickException as e:
                log.warning("reviewing %s#%s failed: %s", repo, number, e.format_message())
                self.redirect(f"{repo}#{number}: {e.format_message()}")
                return
            log.info("opened %s#%s for review", repo, number)
            self.redirect(f"opened {repo}#{number}")

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
def server(parent: str | None, host: str, port: int, no_open: bool, log_level: str) -> None:
    """Serve a web page with the `pr ls` tables and the `jira ls` table.

    Each PR can be reviewed (as `pr review`) or opened on GitHub, and each of
    your PRs marked ready (drafts), set to auto-merge, or merged (approved),
    one at a time or checked and done in bulk; each issue
    opened in Jira. Each table loads when you click its refresh link, and its
    filter checkboxes apply in the page. Ctrl-C stops it.
    """
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # only be's own loggers, so --log-level debug doesn't turn on libraries' debug output
    logging.getLogger("be").setLevel(log_level.upper())
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
