"""`be server`: a local web page with the `pr ls` and `jira ls` tables, and a config page."""

from __future__ import annotations

import html
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import click
from click.core import ParameterSource

from be import config, jira
from be.commands import jira as jira_command
from be.commands import pr
from be.github import same_login

log = logging.getLogger(__name__)

LOG_LEVELS = config.SETTINGS["server.log_level"].choices
# the flag that fixes each setting the server reads, until it restarts, when given
FLAGS = {"pr.dir": "--parent", "server.log_level": "--log-level"}

# (id, heading) for each table; a PR table's id is its pr.KINDS list
TABLES = (
    ("review", "review requests"),
    ("team", "team review requests"),
    ("mine", "your PRs"),
    ("jira", "jira issues"),
)
# (id, label, table ids) for each tab, in page order
TABS = (
    ("work", "my work", ("mine", "jira")),
    ("reviews", "reviews", ("review", "team")),
)

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
:root {
  color-scheme: dark;
  --bg: #0b0e14; --surface: #121722; --raised: #171d2a; --inset: #0f141d;
  --border: #232b3a; --border-strong: #2c3647; --rule: #1c2330;
  --text: #e6e9ef; --text-2: #c7cfdb; --muted: #8b95a7;
  --accent: #6ea8fe; --accent-fill: #2f6feb; --accent-tint: rgba(110, 168, 254, 0.1);
  --pass: #56d364; --fail: #ff7b72; --pending: #e3b341;
  --mono: ui-monospace, SFMono-Regular, Menlo, monospace;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, system-ui, sans-serif;
}
a { color: var(--accent); text-decoration: none; }
a:hover { color: #9cc3ff; }
button, select, input { font: inherit; color: inherit; }
button { cursor: pointer; }
header {
  position: sticky; top: 0; z-index: 2; display: flex; flex-wrap: wrap; align-items: center; gap: 16px;
  padding: 12px 24px; background: rgba(11, 14, 20, 0.92); backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
}
.brand { font: 700 16px var(--mono); letter-spacing: 0.5px; }
.tabs { display: flex; gap: 4px; padding: 4px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; }
.tab {
  display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border: 0; border-radius: 7px;
  background: transparent; color: var(--muted); font-weight: 500; text-transform: capitalize;
}
.tab:hover { color: var(--text); }
.tab.active { background: var(--accent-fill); color: #fff; }
.count:not(:empty) { font-size: 11px; padding: 1px 7px; border-radius: 999px; background: rgba(255, 255, 255, 0.12); }
.keys-toggle {
  padding: 6px 10px; background: transparent; color: var(--muted);
  border: 1px solid var(--border); border-radius: 8px;
}
.keys-toggle:hover { color: var(--text); border-color: var(--border-strong); }
.nav-link {
  padding: 6px 10px; color: var(--muted); border: 1px solid var(--border); border-radius: 8px;
}
.nav-link:hover { color: var(--text); border-color: var(--border-strong); }
.header-links { display: flex; gap: 8px; margin-left: auto; }
.keys { margin: 0; padding: 8px 24px; background: var(--inset); border-bottom: 1px solid var(--border); color: var(--muted); font-size: 12px; }
main { max-width: 1280px; margin: 0 auto; padding: 20px 24px 48px; }
.tab-panel { display: flex; flex-direction: column; gap: 20px; }
.tab-panel:not(.active) { display: none; }
.msg {
  display: flex; align-items: center; gap: 12px; margin: 0 0 20px; padding: 10px 14px;
  background: var(--accent-tint); border: 1px solid rgba(110, 168, 254, 0.35); border-radius: 10px; color: #cfe0ff;
}
.msg span { flex: 1; }
.dismiss { background: transparent; border: 0; color: var(--muted); }
section { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.head { display: flex; align-items: center; gap: 12px; padding: 14px 16px 10px; }
h2 { margin: 0; font-size: 15px; font-weight: 600; text-transform: capitalize; }
.collapse {
  display: inline-flex; padding: 2px; background: transparent; border: 0; border-radius: 6px; color: var(--muted);
}
.collapse:hover { color: var(--text); background: var(--raised); }
.collapse svg { transition: transform 0.15s; }
section.collapsed .collapse svg { transform: rotate(-90deg); }
section.collapsed > :not(.head) { display: none; }
.hidden-count { margin-left: 8px; color: var(--muted); font-size: 12px; font-weight: 400; text-transform: none; }
.refresh {
  display: inline-flex; align-items: center; gap: 6px; margin-left: auto; padding: 5px 10px;
  border: 1px solid var(--border-strong); border-radius: 8px; color: var(--text-2); font-size: 12px;
}
.refresh:hover { color: var(--text); background: var(--raised); }
.refresh.loading { pointer-events: none; opacity: 0.7; }
.refresh.loading svg { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.filters { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 0 16px 12px; }
.filters label {
  display: inline-flex; align-items: center; gap: 6px; padding: 4px 4px 4px 10px;
  background: var(--raised); border: 1px solid var(--border); border-radius: 8px; color: var(--muted); font-size: 12px;
}
.filters label:has(input[type=checkbox]) { padding: 5px 10px; border-radius: 999px; }
.filters label:has(input:checked) { background: var(--accent-tint); border-color: rgba(110, 168, 254, 0.35); color: #cfe0ff; }
.filters select, .filters input[type=search] {
  background: var(--bg); border: 1px solid var(--border-strong); border-radius: 6px; padding: 3px 6px;
}
.filters input[type=search] { flex: 0 1 260px; padding: 6px 10px; border-radius: 8px; font-size: 13px; }
.filters input[type=search]:focus, .filters select:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
input[type=checkbox] { accent-color: var(--accent); margin: 0; }
form { margin: 0; }
.bulk {
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 0 16px 12px; padding: 6px 8px 6px 12px;
  background: var(--raised); border: 1px solid var(--border); border-radius: 10px; font-size: 12px;
}
.bulk:has(button:not(:disabled)) { border-color: rgba(110, 168, 254, 0.35); }
.picked-count { margin-right: 6px; color: var(--text-2); }
.table-wrap { overflow-x: auto; border-top: 1px solid var(--border); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
  padding: 8px 12px; background: var(--inset); color: var(--muted); text-align: left;
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.6px; white-space: nowrap;
}
td { padding: 8px 12px; border-top: 1px solid var(--rule); white-space: nowrap; }
td:last-child { width: 1%; }
tr.pr:hover td, tr.issue:hover td { background: rgba(255, 255, 255, 0.02); }
tr.selected td { background: var(--accent-tint); }
tr.selected td:first-child { box-shadow: inset 3px 0 0 var(--accent); }
tr.filtered { display: none; }
td a { font-family: var(--mono); }
td.col-checks::before { content: ""; display: inline-block; width: 8px; height: 8px; margin-right: 6px; border-radius: 50%; background: var(--muted); }
tr[data-checks=pass] td.col-checks { color: var(--pass); }
tr[data-checks=pass] td.col-checks::before { background: var(--pass); }
tr[data-checks=fail] td.col-checks { color: var(--fail); }
tr[data-checks=fail] td.col-checks::before { background: var(--fail); }
tr[data-checks=pending] td.col-checks { color: var(--pending); }
tr[data-checks=pending] td.col-checks::before { background: var(--pending); }
tr[data-draft=yes] td.col-draft { color: var(--muted); font-style: italic; }
.actions { display: flex; justify-content: flex-end; gap: 6px; }
.actions button, .bulk button {
  padding: 4px 10px; background: #1d2433; border: 1px solid var(--border-strong); border-radius: 6px; font-size: 12px;
}
.actions button:hover, .bulk button:hover:not(:disabled) { background: #252e40; }
form[action='/merge'] button, .bulk button[value=merge]:not(:disabled) { background: var(--accent-fill); border-color: var(--accent-fill); color: #fff; }
.bulk button:disabled { opacity: 0.45; cursor: default; }
.empty { padding: 20px 12px; color: var(--muted); text-align: center; }
.config td { vertical-align: top; }
.config td.key { font-family: var(--mono); }
.config .help { margin-top: 2px; color: var(--muted); font: 12px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, system-ui, sans-serif; white-space: normal; }
.config .note { margin-top: 4px; color: var(--pending); font-size: 12px; white-space: normal; }
.config .value { display: flex; gap: 6px; }
.config input, .config select {
  min-width: 0; width: 320px; max-width: 100%; padding: 5px 8px;
  background: var(--bg); border: 1px solid var(--border-strong); border-radius: 6px; font-size: 13px;
}
.config input[name=name] { width: 100%; }
.config input:focus, .config select:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
.config tr.entry td.key { padding-left: 28px; }
.config td.source { padding-top: 14px; color: var(--muted); font-size: 12px; }
.config button[value=save] { background: var(--accent-fill); border-color: var(--accent-fill); color: #fff; }
.config .reveal { padding: 4px 10px; background: #1d2433; border: 1px solid var(--border-strong); border-radius: 6px; font-size: 12px; }
.config-path { margin: 0; padding: 10px 16px; border-top: 1px solid var(--border); color: var(--muted); font-size: 12px; }
.config-path code { font-family: var(--mono); color: var(--text-2); }
@media (max-width: 640px) {
  header, main { padding-left: 16px; padding-right: 16px; }
  .keys { padding: 8px 16px; }
  .filters input[type=search] { flex: 1 1 100%; }
  /* each setting stacks: key, then value, then source beside its buttons */
  .config tr:has(th) { display: none; }
  .config tr { display: grid; grid-template-columns: 1fr auto; padding: 6px 0; border-top: 1px solid var(--rule); }
  .config td { padding: 4px 16px; border-top: 0; }
  .config td.key, .config td:nth-child(2) { grid-column: 1 / -1; }
  .config tr.entry td.key { padding-left: 16px; }
  .config td.source { padding-top: 8px; }
  .config td:last-child { width: auto; }
  .config .value > :first-child { flex: 1; width: auto; }
}
""" + "".join(f".hide-{key} .col-{key} {{ display: none; }}\n" for key, *_ in PR_SELECTS)

CHEVRON_ICON = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"></path></svg>'
)

REFRESH_ICON = (
    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"></path><path d="M21 3v5h-5"></path></svg>'
)

# keyboard parity with `pr ls -i`: arrows/j/k move, enter reviews (or opens an issue), o opens,
# m switches table, a toggles the table's filters, r marks your draft ready, u enables auto-merge;
# x checks your PR for the bulk bar; c collapses the table; t or 1/2 switch tab; filters apply here and
# are remembered per table in localStorage, as are collapsed tables and the shown tab
SCRIPT = """
const panels = [...document.querySelectorAll(".tab-panel")];
const tabs = [...document.querySelectorAll(".tab")];
let p = 0, t = 0, r = 0;
// keys move between the tables of the shown tab
const sections = () => [...panels[p].querySelectorAll("section")];
const shown = "tr.pr:not(.filtered), tr.issue:not(.filtered)";
// a collapsed table's rows can't be moved to
const rows = () => sections()[t].classList.contains("collapsed") ? [] : [...sections()[t].querySelectorAll(shown)];
function showTab(i) {
  p = i; t = 0; r = 0;
  panels.forEach((x, j) => x.classList.toggle("active", j === p));
  tabs.forEach((x, j) => { x.classList.toggle("active", j === p); x.setAttribute("aria-selected", j === p); });
  try { localStorage.setItem("be.tab", panels[p].dataset.tab); } catch {}
  draw();
}
// each tab's badge counts its shown rows
function updateCounts() {
  panels.forEach((x, j) => {
    const n = x.querySelectorAll(shown).length;
    tabs[j].querySelector(".count").textContent = n ? n : "";
  });
}
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
  if (count) count.textContent = hidden ? `${hidden} hidden` : "";
  updateCounts();
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
function setCollapsed(s, on) {
  s.classList.toggle("collapsed", on);
  s.querySelector(".collapse").setAttribute("aria-expanded", !on);
  try { localStorage.setItem(`be.collapsed.${s.dataset.table}`, on ? "1" : "0"); } catch {}
}
function draw() {
  document.querySelectorAll("tr.selected").forEach(e => e.classList.remove("selected"));
  r = Math.max(0, Math.min(r, rows().length - 1));
  const row = rows()[r];
  if (row) row.classList.add("selected");
}
document.querySelectorAll("section").forEach(s => {
  try { if (localStorage.getItem(`be.collapsed.${s.dataset.table}`) === "1") setCollapsed(s, true); } catch {}
  s.querySelector(".collapse").addEventListener("click", () => {
    setCollapsed(s, !s.classList.contains("collapsed"));
    draw();
  });
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
    const search = sections()[t].querySelector(".filters input[type=search]");
    if (search) { search.focus(); e.preventDefault(); }
    return;
  }
  const row = rows()[r];
  if (e.key === "ArrowDown" || e.key === "j") r = Math.min(r + 1, rows().length - 1);
  else if (e.key === "ArrowUp" || e.key === "k") r = Math.max(r - 1, 0);
  else if (e.key === "m") { t = (t + 1) % sections().length; r = 0; }
  else if (e.key === "c") { const s = sections()[t]; setCollapsed(s, !s.classList.contains("collapsed")); r = 0; }
  else if (e.key === "t") { showTab((p + 1) % panels.length); return; }
  else if (e.key >= "1" && e.key <= String(panels.length)) { showTab(Number(e.key) - 1); return; }
  else if (e.key === "a") {
    // like --all: clear every filter, or turn them all back on (dropdowns to their defaults)
    const s = sections()[t], bs = boxes(s), xs = selects(s);
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
    if (pick) { pick.checked = !pick.checked; updateBulk(sections()[t]); }
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
tabs.forEach((x, j) => x.addEventListener("click", () => showTab(j)));
// a refresh blocks while the table is fetched; spin its icon meanwhile
document.querySelectorAll("a.refresh").forEach(a => a.addEventListener("click", () => a.classList.add("loading")));
const keys = document.querySelector(".keys"), toggle = document.querySelector(".keys-toggle");
toggle.addEventListener("click", () => { keys.hidden = !keys.hidden; toggle.setAttribute("aria-expanded", !keys.hidden); });
const dismiss = document.querySelector(".msg .dismiss");
if (dismiss) dismiss.addEventListener("click", () => dismiss.parentElement.remove());
// the tab named in the URL's hash, else the one last shown
let start = location.hash.slice(1);
if (!start) try { start = localStorage.getItem("be.tab"); } catch {}
showTab(Math.max(0, panels.findIndex(x => x.dataset.tab === start)));
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
    """The heading with its collapse button and refresh link, filter dropdowns and checkboxes, (if search) a
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
        f'<div class="head"><button type="button" class="collapse" aria-expanded="true"'
        f' aria-label="collapse {html.escape(heading)}">{CHEVRON_ICON}</button><h2>{html.escape(heading)}<span class="hidden-count"></span></h2>'
        f'<a class="refresh" href="/refresh?table={table}">{REFRESH_ICON}refresh</a></div>',
        f'<div class="filters">{boxes}</div>',
        bulk,
        '<div class="table-wrap"><table>',
        *rows,
        "</table></div></section>",
    ]


def empty_row(header: tuple, colspan: int, message: str) -> list[str]:
    return [
        header_row(header, colspan - len(header)),
        f'<tr><td class="empty" colspan={colspan}>{html.escape(message)}</td></tr>',
    ]


NOT_LOADED = "not loaded; refresh to load"


def pr_table(table: str, heading: str, prs: list[dict] | str | None) -> str:
    """A `pr ls` table; prs is None before it's loaded, or the error message when that failed."""
    mine = table == "mine"
    # your PRs are never by Renovate, so they skip its checkbox
    filters = () if mine else PR_FILTERS
    header = pr_header(mine)
    colspan = len(header) + 1
    if not prs or isinstance(prs, str):
        if prs is None:
            message = NOT_LOADED
        else:
            message = f"github: {prs}" if prs else pr.EMPTY[table]
        rows = empty_row(header, colspan, message)
        return "\n".join(section(table, heading, filters, rows, search=True, selects=PR_SELECTS))
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
            f'<tr class="pr" data-search="{search}"{data}{hide_attr(p, filters)}>'
            + pick
            + "".join(f"<td{col_attr(h)}>{cells[h]}</td>" for h in header)
            + actions
            + "</tr>"
        )
    bulk = bulk_bar() if mine else ""
    return "\n".join(
        section(table, heading, filters, out, search=True, selects=PR_SELECTS, bulk=bulk)
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


KEYS = (
    "j/k move · enter review or open issue · o open in browser · r mark your draft ready"
    " · u enable auto-merge on your PR · x check your PR for bulk actions · t or 1/2 switch tab"
    " · m switch table · c collapse table · a toggle filters · / search repo or title"
)


def page_shell(title: str, header: str, main: str, script: str, message: str = "", extra: str = "") -> str:
    """A page with STYLE, header, any dismissable message atop main, and script; extra sits between header and main."""
    parts = [
        "<!doctype html><html><head><meta charset=utf-8>",
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{html.escape(title)}</title><style>{STYLE}</style></head><body>",
        f'<header><span class="brand">be</span>{header}</header>',
        f"{extra}<main>",
    ]
    if message:
        parts.append(
            f'<p class="msg"><span>{html.escape(message)}</span>'
            '<button type="button" class="dismiss" aria-label="dismiss">✕</button></p>'
        )
    parts.append(f"{main}</main><script>{script}</script></body></html>")
    return "\n".join(parts)


def render_page(loaded: dict[str, list[dict] | str], message: str = "") -> str:
    """The `pr ls` tables and the `jira ls` table in tabs, each loaded on refresh, with the `-i` actions."""
    headings = dict(TABLES)
    tabs = "".join(
        f'<button type="button" class="tab" data-tab="{tab}">{html.escape(label)}'
        '<span class="count"></span></button>'
        for tab, label, _ in TABS
    )
    header = (
        f'<nav class="tabs" aria-label="tabs">{tabs}</nav>'
        '<div class="header-links"><button type="button" class="keys-toggle" aria-expanded="false">? keys</button>'
        '<a class="nav-link" href="/config">config</a></div>'
    )
    parts = []
    for tab, _, tables in TABS:
        parts.append(f'<div class="tab-panel" data-tab="{tab}">')
        for table in tables:
            if table == "jira":
                parts.append(issue_table(headings[table], loaded.get(table)))
            else:
                parts.append(pr_table(table, headings[table], loaded.get(table)))
        parts.append("</div>")
    keys = f'<p class="keys" hidden>{KEYS}</p>'
    return page_shell("be", header, "\n".join(parts), SCRIPT, message, extra=keys)


# shows and hides the secret settings' values, and dismisses the message
CONFIG_SCRIPT = """
document.querySelectorAll("button.reveal").forEach(b => b.addEventListener("click", () => {
  const input = b.previousElementSibling, show = input.type === "password";
  input.type = show ? "text" : "password";
  b.textContent = show ? "hide" : "show";
  b.setAttribute("aria-pressed", show);
}));
const dismiss = document.querySelector(".msg .dismiss");
if (dismiss) dismiss.addEventListener("click", () => dismiss.parentElement.remove());
"""

CONFIG_HEADER = ("KEY", "VALUE", "SOURCE")
UNSET_CHOICE = "(unset)"


def value_input(s: config.Setting, form: str, value: str) -> str:
    """The input for setting s in form: a dropdown of its choices (and a blank entry naming its default, and
    any other value the file has), a password box with a show button if secret, else a text box showing its
    default."""
    attrs = f'name="value" form="{form}" aria-label="{html.escape(s.key)}"'
    if s.choices:
        options = (*s.choices, value) if value and value not in s.choices else s.choices
        blank = f"(default: {s.default})" if s.default else UNSET_CHOICE
        choices = f'<option value="">{html.escape(blank)}</option>' + "".join(
            f'<option value="{html.escape(o)}"{" selected" if o == value else ""}>{html.escape(o)}</option>'
            for o in options
        )
        return f"<select {attrs}>{choices}</select>"
    placeholder = f' placeholder="{html.escape(s.default)}"' if s.default else ""
    if s.secret:
        return (
            f'<input type="password" {attrs} value="{html.escape(value)}" autocomplete="off">'
            '<button type="button" class="reveal" aria-pressed="false">show</button>'
        )
    return f'<input type="text" {attrs} value="{html.escape(value)}"{placeholder}>'


def config_actions(form: str, key: str, save: str = "save", unset: str = "unset") -> str:
    """The form a row's inputs belong to, with its key and save and unset buttons."""
    return (
        f'<td><form id="{form}" class="actions" method="post" action="/config/set">'
        f'<input type="hidden" name="key" value="{html.escape(key)}">'
        f'<button name="do" value="save">{save}</button>'
        + (f'<button formaction="/config/unset">{unset}</button>' if unset else "")
        + "</form></td>"
    )


def override_note(s: config.Setting, effective) -> str:
    """The note on a setting whose env var wins over the file, with the value it gives (masked if secret)."""
    if s.secret:
        shown = "********"
    elif isinstance(effective, dict):
        shown = ", ".join(effective) or "no entries"
    else:
        shown = effective
    return f'<div class="note">{s.env} overrides the file: {html.escape(str(shown))}</div>'


def config_rows(fixed: tuple[str, ...]) -> list[str]:
    """A row per setting, and per entry of a map setting plus a row to add one, each saved on its own."""
    data = config.load_file()
    rows = ["<tr>" + "".join(f"<th>{h}</th>" for h in CONFIG_HEADER) + "<th></th></tr>"]
    for n, s in enumerate(config.SETTINGS.values()):
        effective, source = config.resolve(s.key)
        file = config.file_value(s.key, data)
        notes = override_note(s, effective) if source.startswith("env:") else ""
        if s.key in fixed:
            notes += f'<div class="note">{FLAGS[s.key]} was given, so `be server` uses it until restarted</div>'
        key_cell = f'<td class="key">{html.escape(s.key)}<div class="help">{html.escape(s.help)}</div></td>'
        if s.kind != "map":
            form = f"cfg-{n}"
            value = "" if file is None else str(file)
            rows.append(
                f'<tr class="setting">{key_cell}'
                f'<td><div class="value">{value_input(s, form, value)}</div>{notes}</td>'
                f'<td class="source">{html.escape(source)}</td>{config_actions(form, s.key)}</tr>'
            )
            continue
        entries = file if isinstance(file, dict) else {}
        count = f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'} in the file"
        rows.append(
            f'<tr class="setting">{key_cell}<td>{count}{notes}</td>'
            f'<td class="source">{html.escape(source)}</td><td></td></tr>'
        )
        for m, (name, v) in enumerate(entries.items()):
            form, key = f"cfg-{n}-{m}", f"{s.key}.{name}"
            rows.append(
                f'<tr class="entry"><td class="key">{html.escape(key)}</td>'
                f'<td><div class="value">{value_input(s, form, str(v))}</div></td>'
                f'<td class="source">file</td>{config_actions(form, key, unset="remove")}</tr>'
            )
        form = f"cfg-{n}-new"
        rows.append(
            f'<tr class="entry add"><td class="key"><input type="text" name="name" form="{form}"'
            f' placeholder="NAME" aria-label="new {html.escape(s.key)} name"></td>'
            f'<td><div class="value"><input type="text" name="value" form="{form}" placeholder="description"'
            f' aria-label="new {html.escape(s.key)} description"></div></td>'
            f"<td></td>{config_actions(form, s.key, save='add', unset='')}</tr>"
        )
    return rows


def render_config(message: str = "", fixed: tuple[str, ...] = ()) -> str:
    """Every setting with its file value to edit, its source and help; fixed names the settings `be server`
    was given a flag for, which a save won't change until it restarts."""
    try:
        rows = config_rows(fixed)
    except click.ClickException as e:
        # e.g. the file isn't valid TOML: show why instead of the settings
        rows = empty_row(CONFIG_HEADER, len(CONFIG_HEADER) + 1, e.format_message())
    path = html.escape(str(config.config_path()))
    main = "\n".join([
        '<section class="config"><div class="head"><h2>config</h2></div>',
        '<div class="table-wrap"><table>',
        *rows,
        "</table></div>",
        f'<p class="config-path">saved to <code>{path}</code>; an env var wins over the file.'
        " Saving an empty value removes it.</p></section>",
    ])
    header = '<div class="header-links"><a class="nav-link" href="/">← tables</a></div>'
    return page_shell("be config", header, main, CONFIG_SCRIPT, message)


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


def fetch_table(table: str) -> list[dict] | str:
    """The table's rows, or the error message from looking them up."""
    log.debug("fetching %s", table)
    try:
        if table == "jira":
            rows = jira.in_progress_issues()
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


def make_handler(parent: str | None, fixed: tuple[str, ...] = tuple(FLAGS)) -> type[BaseHTTPRequestHandler]:
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
                self.send_page(render_page(loaded, message))
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path not in ("/review", "/bulk", "/config/set", "/config/unset", *MINE_PATHS):
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", 0))
            form = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)
            if path.startswith("/config/"):
                self.config_action(form, unset=path == "/config/unset")
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
                pr.open_review(repo, int(number), self.parent())
            except click.ClickException as e:
                log.warning("reviewing %s#%s failed: %s", repo, number, e.format_message())
                self.redirect(f"{repo}#{number}: {e.format_message()}")
                return
            log.info("opened %s#%s for review", repo, number)
            self.redirect(f"opened {repo}#{number}")

        def parent(self) -> str | None:
            """--parent if given, else pr.dir as it's set now."""
            return parent if "pr.dir" in fixed else config.resolve("pr.dir")[0]

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
    """Serve a web page with the `pr ls` tables and the `jira ls` table, in two tabs.

    Each PR can be reviewed (as `pr review`) or opened on GitHub, and each of
    your PRs marked ready (drafts), set to auto-merge, or merged (approved),
    one at a time or checked and done in bulk; each issue
    opened in Jira. Each table loads when you click its refresh link, and its
    filter checkboxes apply in the page. The config page (/config) edits the
    config file, one setting at a time; pr.dir and server.log_level apply at
    once unless --parent or --log-level was given. Ctrl-C stops it.
    """
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # only be's own loggers, so --log-level debug doesn't turn on libraries' debug output
    logging.getLogger("be").setLevel(log_level.upper())
    ctx = click.get_current_context()
    params = {"pr.dir": "parent", "server.log_level": "log_level"}
    fixed = tuple(
        key for key, param in params.items()
        if ctx.get_parameter_source(param) == ParameterSource.COMMANDLINE
    )
    httpd = HTTPServer((host, port), make_handler(parent, fixed))
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
