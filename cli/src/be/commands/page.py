"""The `be server` pages: the PR and Jira tables, and the config page."""

from __future__ import annotations

import html

import click

from be import config, jira
from be.commands import pr, ws
from be.commands.jira import TOP_LEVEL
from be.github import same_login

# the flag that fixes each setting the server reads, until it restarts, when given
FLAGS = {
    "pr.dir": "--parent",
    "server.log_level": "--log-level",
    "pr.agent": "--agent",
    "claude.pr.model": "--claude-model",
    "cursor.pr.model": "--cursor-model",
}

# (id, heading) for each table; a PR table's id is its pr.KINDS list
TABLES = (
    ("review", "review requests"),
    ("team", "team review requests"),
    ("mine", "your PRs"),
    ("jira", "jira issues"),
    ("workspaces", "workspaces"),
)
# (id, label, table ids) for each page in the sidebar, in order
TABS = (
    ("work", "my work", ("jira",)),
    ("prs", "my PRs", ("mine",)),
    ("reviews", "reviews", ("review", "team")),
    ("workspaces", "workspaces", ("workspaces",)),
)

# (key, options, default, value) for the PR tables' filter dropdowns, defaulting to what
# pr.filter_prs shows: a row is hidden unless value(row) is the chosen option, or "all" is;
# while one option is chosen the key's column is hidden, as every row would show it
PR_SELECTS = (
    ("checks", ("pass", "fail", "pending", "none"), "pass", lambda p: p["checks"]),
    ("draft", ("no", "yes"), "no", lambda p: "yes" if p["draft"] else "no"),
)
SELECT_ALL = "all"

# (key, label, hides) for the PR tables' filter checkboxes, matching pr.filter_prs; a row is
# hidden while any checked filter hides it
PR_FILTERS = (
    ("renovate", f"not by {pr.RENOVATE_USER}", lambda p: same_login(p["author"], pr.RENOVATE_USER)),
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
body:has(.shell) { height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
body:has(.shell) header, body:has(.shell) .keys { flex: none; }
.shell { flex: 1; display: flex; min-height: 0; min-width: 0; position: relative; }
.sidebar {
  flex: none; width: 200px; display: flex; flex-direction: column; gap: 4px;
  padding: 12px 10px; background: var(--surface); border-right: 1px solid var(--border);
  overflow: hidden; transition: width 0.15s ease, padding 0.15s ease, border-width 0.15s ease;
}
.sidebar.collapsed { width: 0; padding-left: 0; padding-right: 0; border-right-width: 0; }
.sidebar.collapsed .nav { visibility: hidden; }
.nav {
  display: flex; align-items: center; gap: 8px; width: 100%; padding: 8px 10px; border: 0; border-radius: 8px;
  background: transparent; color: var(--muted); font-weight: 500; text-transform: capitalize;
  white-space: nowrap; text-align: left;
}
.nav:hover { color: var(--text); background: var(--raised); }
.nav.active { background: var(--accent-fill); color: #fff; }
.nav .count { margin-left: auto; }
.count:empty { display: none; }
.count:not(:empty) { font-size: 11px; padding: 1px 7px; border-radius: 999px; background: rgba(255, 255, 255, 0.12); }
.sidebar-toggle {
  display: inline-flex; padding: 6px; background: transparent; color: var(--muted);
  border: 1px solid var(--border); border-radius: 8px;
}
.sidebar-toggle:hover, .sidebar-toggle[aria-expanded="false"] {
  color: var(--text); border-color: var(--border-strong); background: var(--raised);
}
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
main { flex: 1; min-width: 0; margin: 0; padding: 20px 20px 48px; }
body:has(.shell) main { overflow: auto; }
.tab-panel { display: flex; flex-direction: column; gap: 20px; }
.tab-panel:not(.active) { display: none; }
.agent { display: flex; align-items: center; gap: 10px; align-self: flex-start; }
.agent-label {
  color: var(--muted); font-size: 12px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.6px;
}
.agent-choices {
  display: flex; gap: 4px; padding: 4px;
  background: var(--raised); border: 1px solid var(--border); border-radius: 10px;
}
.agent-choice {
  padding: 4px 12px; border: 0; border-radius: 7px;
  background: transparent; color: var(--muted); font-weight: 500;
}
.agent-choice:hover { color: var(--text); }
.agent-choice[aria-checked="true"] { background: var(--accent-fill); color: #fff; }
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
tr.pr:hover td, tr.ws:hover td { background: rgba(255, 255, 255, 0.02); }
tr.ws { cursor: pointer; }
tr.selected td { background: var(--accent-tint); }
tr.selected td:first-child { box-shadow: inset 3px 0 0 var(--accent); }
tr.filtered { display: none; }
.tree-wrap { overflow-x: auto; padding: 6px 0 10px; border-top: 1px solid var(--border); font-size: 13px; }
.tree, .tree ul { list-style: none; margin: 0; padding: 0; }
/* each level indents, with a guide line down from its parent */
.tree ul { margin-left: 22px; padding-left: 10px; border-left: 1px solid var(--rule); }
.node { display: flex; align-items: center; gap: 10px; padding: 5px 16px 5px 12px; border-radius: 6px; white-space: nowrap; }
.node:hover { background: rgba(255, 255, 255, 0.02); }
.node a { font-family: var(--mono); }
li.issue.selected > .node { background: var(--accent-tint); box-shadow: inset 3px 0 0 var(--accent); }
.node .type { color: var(--muted); font-size: 12px; }
.node .status {
  padding: 1px 8px; border-radius: 999px; font-size: 11px; font-weight: 600;
  background: var(--raised); border: 1px solid var(--border-strong); color: var(--text-2);
}
.node .status.cat-indeterminate { color: var(--pending); border-color: rgba(227, 179, 65, 0.4); background: rgba(227, 179, 65, 0.08); }
.node .summary { overflow: hidden; text-overflow: ellipsis; }
.node .assignee { margin-left: auto; padding-left: 12px; color: var(--muted); font-size: 12px; }
/* issues someone else is assigned stay quieter than yours */
li.issue.other > .node .summary { color: var(--text-2); }
.twist {
  flex: none; display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px;
  margin-right: -4px; padding: 0; background: transparent; border: 0; border-radius: 4px; color: var(--muted);
}
button.twist:hover { color: var(--text); background: var(--raised); }
.twist svg { transition: transform 0.15s; }
li.issue.closed > .node .twist svg { transform: rotate(-90deg); }
li.issue.closed > ul { display: none; }
/* a project filter hides issues outside it, keeping those that only hold a match, dimmed, for context */
li.issue.filtered { display: none; }
li.issue.context > .node { opacity: 0.5; }
section:has(details.multi[open]) { overflow: visible; }
details.multi { position: relative; }
details.multi summary {
  display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; list-style: none; cursor: pointer;
  background: var(--raised); border: 1px solid var(--border); border-radius: 8px; color: var(--muted); font-size: 12px;
}
details.multi summary::-webkit-details-marker { display: none; }
details.multi summary::after { content: "▾"; font-size: 10px; }
details.multi.active summary { background: var(--accent-tint); border-color: rgba(110, 168, 254, 0.35); color: #cfe0ff; }
.multi-label { color: var(--text-2); }
.multi-menu {
  position: absolute; z-index: 4; top: calc(100% + 4px); left: 0; min-width: 180px; max-height: 280px; overflow: auto;
  display: flex; flex-direction: column; gap: 2px; padding: 6px;
  background: var(--surface); border: 1px solid var(--border-strong); border-radius: 10px; box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
}
.filters .multi-menu label {
  padding: 5px 8px; background: transparent; border: 0; border-radius: 6px; color: var(--text-2); font-family: var(--mono); white-space: nowrap;
}
.filters .multi-menu label:hover { background: var(--raised); }
.multi-note { color: var(--muted); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, system-ui, sans-serif; }
.multi-clear { margin-top: 4px; padding: 5px 8px; background: transparent; border: 0; border-top: 1px solid var(--rule); color: var(--accent); font-size: 12px; text-align: left; }
.tree-wrap .empty { margin: 0; }
.node { cursor: default; user-select: none; }
.ws-badge {
  padding: 0 6px; border: 1px solid rgba(110, 168, 254, 0.35); border-radius: 4px;
  color: var(--accent); font: 600 10px/16px var(--mono); text-transform: uppercase;
}
dialog.ws-create {
  width: min(440px, calc(100vw - 32px)); padding: 0; background: var(--surface); color: var(--text);
  border: 1px solid var(--border-strong); border-radius: 12px; box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5);
}
dialog.ws-create::backdrop { background: rgba(0, 0, 0, 0.55); }
.ws-create form { display: flex; flex-direction: column; gap: 12px; padding: 18px; }
.ws-create h3 { margin: 0; font-size: 15px; font-weight: 600; }
.ws-create .ws-key { font-family: var(--mono); }
.ws-create label { display: flex; flex-direction: column; gap: 4px; color: var(--muted); font-size: 12px; }
.ws-create input[type=text] {
  padding: 6px 10px; background: var(--bg); border: 1px solid var(--border-strong); border-radius: 6px; font-size: 13px;
}
.ws-create input[type=text]:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
.ws-for { display: flex; flex-direction: column; gap: 6px; margin: 0; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; }
.ws-for legend { padding: 0 4px; color: var(--muted); font-size: 12px; }
.ws-for label { flex-direction: row; align-items: center; gap: 8px; color: var(--text-2); font-size: 13px; }
.ws-mode { display: flex; gap: 4px; padding: 4px; background: var(--raised); border: 1px solid var(--border); border-radius: 10px; }
.ws-mode[hidden] { display: none; }
.ws-mode label { flex: 1; flex-direction: row; justify-content: center; gap: 0; padding: 5px 8px; border-radius: 7px; cursor: pointer; font-size: 13px; }
.ws-mode input { position: absolute; opacity: 0; pointer-events: none; }
.ws-mode label:has(input:checked) { background: var(--accent-fill); color: #fff; }
.ws-mode label:has(input:focus-visible) { outline: 2px solid var(--accent); }
.ws-new, .ws-link { display: flex; flex-direction: column; gap: 12px; margin: 0; padding: 0; border: 0; }
.ws-new[hidden], .ws-link[hidden] { display: none; }
.ws-create select { padding: 6px 10px; background: var(--bg); border: 1px solid var(--border-strong); border-radius: 6px; font-size: 13px; }
.ws-create .actions button.create { background: var(--accent-fill); border-color: var(--accent-fill); color: #fff; }
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
  header { padding-left: 16px; padding-right: 16px; }
  .keys { padding: 8px 16px; }
  /* an open sidebar covers the page instead of squeezing it */
  .sidebar:not(.collapsed) {
    position: absolute; z-index: 3; top: 0; bottom: 0; height: auto;
    box-shadow: 8px 0 24px rgba(0, 0, 0, 0.45);
  }
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

# keyboard parity with `pr ls -i`: arrows/j/k move, enter reviews (or opens an issue or workspace), o opens,
# m switches table, a toggles the table's filters, r marks your draft ready, u enables auto-merge;
# x checks your PR for the bulk bar; c collapses the table; t or 1-4 switch page; filters apply here and
# are remembered per table in localStorage, as are collapsed tables, the shown page, and the sidebar
SCRIPT = """
const panels = [...document.querySelectorAll(".tab-panel")];
const navs = [...document.querySelectorAll(".sidebar .nav")];
let p = 0, t = 0, r = 0;
// keys move between the tables of the shown page
const sections = () => [...panels[p].querySelectorAll("section")];
const shown = "tr.pr:not(.filtered), li.issue:not(.filtered), tr.ws:not(.filtered)";
// a collapsed table's rows can't be moved to
const rows = () => sections()[t].classList.contains("collapsed") ? [] : [...sections()[t].querySelectorAll(shown)]
  .filter(row => !row.parentElement.closest("li.issue.closed"));
function showTab(i) {
  p = i; t = 0; r = 0;
  panels.forEach((x, j) => x.classList.toggle("active", j === p));
  navs.forEach((x, j) => {
    const on = j === p;
    x.classList.toggle("active", on);
    if (on) x.setAttribute("aria-current", "page"); else x.removeAttribute("aria-current");
  });
  try { localStorage.setItem("be.tab", panels[p].dataset.tab); } catch {}
  draw();
}
// each page's badge counts its shown rows
function updateCounts() {
  panels.forEach((x, j) => {
    const n = x.querySelectorAll(shown).length;
    navs[j].querySelector(".count").textContent = n ? n : "";
  });
}
const boxes = s => [...s.querySelectorAll(".filters > label > input[type=checkbox]")];
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
  s.querySelectorAll("tr.pr").forEach(row => {
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
// an issue's children open and close with its toggle; closed ones are remembered by key
function setOpen(li, open) {
  const twist = li.querySelector(":scope > .node > button.twist");
  if (!twist) return;
  li.classList.toggle("closed", !open);
  twist.setAttribute("aria-expanded", open);
  twist.setAttribute("aria-label", `${open ? "collapse" : "expand"} ${li.dataset.key}`);
  try { if (open) localStorage.removeItem(`be.closed.${li.dataset.key}`); else localStorage.setItem(`be.closed.${li.dataset.key}`, "1"); } catch {}
}
document.querySelectorAll("li.issue").forEach(li => {
  const twist = li.querySelector(":scope > .node > button.twist");
  if (!twist) return;
  try { if (localStorage.getItem(`be.closed.${li.dataset.key}`) === "1") setOpen(li, false); } catch {}
  twist.addEventListener("click", () => {
    const row = rows()[r];
    setOpen(li, li.classList.contains("closed"));
    // keep the selection on the same issue, or on this one if it was hidden
    const i = rows().indexOf(row);
    r = i >= 0 ? i : Math.max(0, rows().indexOf(li));
    draw();
  });
});
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
  // the create workspace dialog keeps its own keys
  if (wsDialog && wsDialog.open) return;
  // so does an open dropdown, but escape closes it
  const multi = e.target.closest && e.target.closest("details.multi");
  if (multi) {
    if (e.key === "Escape") { multi.open = false; multi.querySelector("summary").focus(); e.preventDefault(); }
    return;
  }
  // typing in the search box doesn't trigger keys; escape or enter goes back to the rows
  if (e.target.type === "search") {
    if (e.key === "Escape" || e.key === "Enter") { e.target.blur(); e.preventDefault(); }
    return;
  }
  // a focused dropdown keeps its own keys; the agent toggle too, so enter picks it.
  // sidebar controls keep enter, but t and the page numbers still switch page
  const inChrome = e.target.closest && e.target.closest(".sidebar, .sidebar-toggle");
  if (e.target.tagName === "SELECT" || (e.target.closest && e.target.closest(".agent"))) return;
  if (inChrome && e.key !== "t" && (e.key < "1" || e.key > String(panels.length))) return;
  if (e.key === "/") {
    const search = sections()[t].querySelector(".filters input[type=search]");
    if (search) { search.focus(); e.preventDefault(); }
    return;
  }
  const row = rows()[r];
  if (e.key === "ArrowDown" || e.key === "j") r = Math.min(r + 1, rows().length - 1);
  else if (e.key === "ArrowUp" || e.key === "k") r = Math.max(r - 1, 0);
  else if ((e.key === "ArrowLeft" || e.key === "h") && row && row.matches("li.issue")) {
    // like a file tree: close an open issue, else move to its parent
    if (row.querySelector(":scope > .node > button.twist") && !row.classList.contains("closed")) setOpen(row, false);
    else {
      const parent = row.parentElement.closest("li.issue:not(.filtered)");
      if (parent) r = rows().indexOf(parent);
    }
  }
  else if ((e.key === "ArrowRight" || e.key === "l") && row && row.matches("li.issue")) setOpen(row, true);
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
  else if (e.key === "o" && row) {
    const link = row.querySelector("a");
    if (link) window.open(link.href, "_blank");
    return;
  }
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
navs.forEach((x, j) => x.addEventListener("click", () => {
  showTab(j);
  // on a narrow window the sidebar covers the page, so choosing one tucks it away
  if (matchMedia("(max-width: 640px)").matches) setSidebar(true, true);
}));
// a refresh blocks while the table is fetched; spin its icon meanwhile
document.querySelectorAll("a.refresh").forEach(a => a.addEventListener("click", () => a.classList.add("loading")));
// the jira tree's dropdowns (projects, status) show the issues matching every one with something
// checked, plus, dimmed, any issue holding a match; none checked shows them all. Each is remembered
const pickerKey = picker => `be.filter.jira.${picker.dataset.key}`;
const pickerBoxes = picker => [...picker.querySelectorAll("input[type=checkbox]")];
function applyTree(s) {
  const picks = [...s.querySelectorAll("details.multi")].map(picker => {
    const picked = pickerBoxes(picker).filter(b => b.checked).map(b => b.value);
    picker.classList.toggle("active", picked.length > 0);
    picker.querySelector(".multi-label").textContent = picked.length ? picked.join(", ") : "all";
    try { localStorage.setItem(pickerKey(picker), JSON.stringify(picked)); } catch {}
    return [picker.dataset.key, picked];
  }).filter(([, picked]) => picked.length);
  let hidden = 0;
  // children before their parents, so a parent knows whether it holds a match
  [...s.querySelectorAll("li.issue")].reverse().forEach(li => {
    const match = picks.every(([key, picked]) => picked.includes(li.dataset[key]));
    const holds = !match && !!li.querySelector(":scope > ul > li.issue:not(.filtered)");
    li.classList.toggle("filtered", !match && !holds);
    li.classList.toggle("context", holds);
    hidden += !match && !holds;
  });
  s.querySelector(".hidden-count").textContent = hidden ? `${hidden} hidden` : "";
  updateCounts();
}
document.querySelectorAll("section:has(details.multi)").forEach(s => {
  s.querySelectorAll("details.multi").forEach(picker => {
    let saved = [];
    try { saved = JSON.parse(localStorage.getItem(pickerKey(picker)) || "[]"); } catch {}
    const boxes = pickerBoxes(picker);
    if (Array.isArray(saved)) boxes.forEach(b => { b.checked = saved.includes(b.value); });
    boxes.forEach(b => b.addEventListener("change", () => { applyTree(s); r = 0; draw(); }));
    picker.querySelector(".multi-clear").addEventListener("click", () => {
      boxes.forEach(b => { b.checked = false; });
      applyTree(s); r = 0; draw();
    });
  });
  applyTree(s);
});
// an open dropdown closes on a click outside it, or escape
document.addEventListener("click", e => {
  document.querySelectorAll("details.multi[open]").forEach(d => { if (!d.contains(e.target)) d.open = false; });
});
// double-clicking an issue opens its workspace, or offers to create one
const wsDialog = document.querySelector("dialog.ws-create");
function post(action, fields) {
  const form = document.createElement("form");
  form.method = "post"; form.action = action;
  Object.entries(fields).forEach(([name, value]) => {
    const input = document.createElement("input");
    input.type = "hidden"; input.name = name; input.value = value;
    form.append(input);
  });
  document.body.append(form);
  form.submit();
}
let wsIssue = null;
// the new workspace is named after the issue, or its parent, and takes that one's summary;
// a linked one is linked to that key
function wsFor(parent) {
  const f = wsDialog.querySelector("form"), d = wsIssue.dataset;
  wsDialog.querySelector(".ws-new input[name=name]").value = parent ? d.parent : d.key;
  f.elements.namedItem("issue_name").value = parent ? d.parentSummary : d.summary;
  f.elements.namedItem("key").value = parent ? d.parent : d.key;
}
// creating and linking post different fields; a disabled fieldset's are neither sent nor required
function wsMode(link) {
  const f = wsDialog.querySelector("form");
  f.action = link ? "/ws/link" : "/ws/create";
  [[".ws-new", !link], [".ws-link", link]].forEach(([sel, on]) => {
    const set = wsDialog.querySelector(sel);
    set.hidden = !on; set.disabled = !on;
  });
  wsDialog.querySelector("button.create").textContent = link ? "link and open" : "create";
}
function openIssue(li) {
  const d = li.dataset;
  if (d.workspace) { post("/open", { name: d.workspace }); return; }
  wsIssue = li;
  const f = wsDialog.querySelector("form");
  f.reset();
  wsDialog.querySelector(".ws-key").textContent = d.key;
  wsDialog.querySelector(".ws-for").hidden = !d.parent;
  wsDialog.querySelector(".ws-for-issue").textContent = `${d.key} only`;
  wsDialog.querySelector(".ws-for-parent").textContent =
    d.parent ? `its ${d.parentType} ${d.parent}${d.parentSummary ? ` (${d.parentSummary})` : ""}` : "";
  wsFor(false);
  wsMode(false);
  wsDialog.showModal();
  f.elements.namedItem("repos").focus();
}
if (wsDialog) {
  wsDialog.querySelectorAll("input[name=for]").forEach(x => x.addEventListener("change", () => wsFor(x.value === "parent")));
  wsDialog.querySelectorAll("input[name=mode]").forEach(x => x.addEventListener("change", () => wsMode(x.value === "link")));
  wsDialog.querySelector(".cancel").addEventListener("click", () => wsDialog.close());
}
document.querySelectorAll("li.issue > .node").forEach(node => node.addEventListener("dblclick", e => {
  // the key links to Jira and the arrow collapses; neither opens a workspace
  if (e.target.closest("a, button")) return;
  const li = node.parentElement;
  t = Math.max(0, sections().indexOf(li.closest("section")));
  r = Math.max(0, rows().indexOf(li));
  draw();
  openIssue(li);
}));
// clicking a workspace row opens it; the open button submits on its own
document.querySelectorAll("tr.ws").forEach(row => row.addEventListener("click", e => {
  if (e.target.closest("button")) return;
  row.querySelector("form").submit();
}));
const keys = document.querySelector(".keys"), toggle = document.querySelector(".keys-toggle");
toggle.addEventListener("click", () => { keys.hidden = !keys.hidden; toggle.setAttribute("aria-expanded", !keys.hidden); });
const sidebar = document.querySelector(".sidebar"), sideBtn = document.querySelector(".sidebar-toggle");
function setSidebar(collapsed, store) {
  sidebar.classList.toggle("collapsed", collapsed);
  sidebar.setAttribute("aria-hidden", collapsed);
  sideBtn.setAttribute("aria-expanded", !collapsed);
  sideBtn.setAttribute("aria-label", collapsed ? "expand sidebar" : "collapse sidebar");
  if (collapsed && sidebar.contains(document.activeElement)) sideBtn.focus();
  if (store) try { localStorage.setItem("be.sidebar", collapsed ? "1" : "0"); } catch {}
}
let side = false;
try {
  const v = localStorage.getItem("be.sidebar");
  side = v === null ? matchMedia("(max-width: 640px)").matches : v === "1";
} catch {}
setSidebar(side, false);
sideBtn.addEventListener("click", () => setSidebar(!sidebar.classList.contains("collapsed"), true));
const dismiss = document.querySelector(".msg .dismiss");
if (dismiss) dismiss.addEventListener("click", () => dismiss.parentElement.remove());
// the reviews tab's agent; remembered, and copied onto every review form
const agentBox = document.querySelector(".agent");
function setAgent(name, store) {
  agentBox.querySelectorAll(".agent-choice").forEach(b => {
    b.setAttribute("aria-checked", b.dataset.agent === name);
  });
  document.querySelectorAll("form.review input[name=agent]").forEach(i => { i.value = name; });
  if (store) try { localStorage.setItem("be.agent", name); } catch {}
}
if (agentBox) {
  let saved = "";
  try { saved = localStorage.getItem("be.agent") || ""; } catch {}
  const names = [...agentBox.querySelectorAll(".agent-choice")].map(b => b.dataset.agent);
  if (names.includes(saved)) setAgent(saved, false);
  agentBox.querySelectorAll(".agent-choice").forEach(b => {
    b.addEventListener("click", () => setAgent(b.dataset.agent, true));
  });
}
// the page named in the URL's hash, else the one last shown
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


def pr_form(action: str, label: str, repo: str, number: int, agent: str = "") -> str:
    """agent is posted with a review, so the reviews-tab toggle beats pr.agent."""
    hidden = f'<input type="hidden" name="agent" value="{html.escape(agent)}">' if agent else ""
    kind = ' class="review"' if action == "review" else ""
    return (
        f'<form method="post" action="/{action}"{kind}>'
        f'<input type="hidden" name="repo" value="{repo}">'
        f'<input type="hidden" name="number" value="{number}">'
        f"{hidden}<button>{label}</button></form>"
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
    tree: bool = False,
    extra: str = "",
) -> list[str]:
    """The heading with its collapse button and refresh link, any extra filter control, filter dropdowns and
    checkboxes, (if search) a search box matching rows' data-search, and any bulk bar; the caller adds the
    table, or the tree's list."""
    boxes = extra + "".join(select_html(key, options, default) for key, options, default, _ in selects)
    boxes += "".join(
        f'<label><input type="checkbox" name="{key}" checked> {html.escape(label)}</label>'
        for key, label, _ in filters
    )
    if search:
        boxes += '<input type="search" name="search" placeholder="repo or title" aria-label="search repo or title">'
    parts = [
        f'<section data-table="{table}">',
        f'<div class="head"><button type="button" class="collapse" aria-expanded="true"'
        f' aria-label="collapse {html.escape(heading)}">{CHEVRON_ICON}</button><h2>{html.escape(heading)}<span class="hidden-count"></span></h2>'
        f'<a class="refresh" href="/refresh?table={table}">{REFRESH_ICON}refresh</a></div>',
    ]
    if boxes:
        parts.append(f'<div class="filters">{boxes}</div>')
    open_, close = ('<div class="tree-wrap">', "</div>") if tree else ('<div class="table-wrap"><table>', "</table></div>")
    return [*parts, bulk, open_, *rows, close + "</section>"]


def empty_row(header: tuple, colspan: int, message: str) -> list[str]:
    return [
        header_row(header, colspan - len(header)),
        f'<tr><td class="empty" colspan={colspan}>{html.escape(message)}</td></tr>',
    ]


NOT_LOADED = "not loaded; refresh to load"
NO_ISSUES = "no open issues assigned to you"


def pr_table(table: str, heading: str, prs: list[dict] | str | None, agent: str = "claude") -> str:
    """A `pr ls` table; prs is None before it's loaded, or the error message when that failed.
    agent is what a review button posts."""
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
        forms = [pr_form("review", "review", repo, p["number"], agent)]
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


def issue_workspace(issue: dict, workspaces: dict[str, str]) -> str:
    """The workspace named after or linked to the issue's key, else its parent's key, ignoring case, as
    `jira ls -i` finds it; workspaces is as ws.issue_workspaces maps it. "" when there's none."""
    for key in (issue["key"], issue["parent"]):
        if key and key.upper() in workspaces:
            return workspaces[key.upper()]
    return ""


def issue_data(issue: dict, workspaces: dict[str, str]) -> str:
    """The attributes a double click reads: the workspace to open, else the issue's summary for a new
    one, and its Feature or Epic parent when the new one could be for that instead (as `jira ls -i` asks)."""
    name = issue_workspace(issue, workspaces)
    if name:
        return f' data-workspace="{html.escape(name)}"'
    data = f' data-summary="{html.escape(issue["summary"])}"'
    if issue["type"] not in TOP_LEVEL and issue["parent_type"] in TOP_LEVEL:
        data += (
            f' data-parent="{html.escape(issue["parent"])}" data-parent-type="{html.escape(issue["parent_type"])}"'
            f' data-parent-summary="{html.escape(issue["parent_summary"])}"'
        )
    return data


def issue_project(issue: dict) -> str:
    """The project key an issue key starts with: ACME for ACME-12."""
    return issue["key"].rpartition("-")[0].upper()


def tree_issues(issues: list[dict]) -> list[dict]:
    """Every issue in the tree, parents before their children."""
    return [found for issue in issues for found in (issue, *tree_issues(issue["children"]))]


# the order status categories sort in: To Do, then In Progress, then Done
CATEGORY_ORDER = ("new", "indeterminate", "done")


def tree_statuses(issues: list[dict]) -> list[str]:
    """Every status in the tree, To Do ones first, then In Progress, then any other, each by name."""
    found = {(issue["category"], issue["status"]) for issue in tree_issues(issues) if issue["status"]}
    rank = {category: n for n, category in enumerate(CATEGORY_ORDER)}
    return [status for _, status in sorted(found, key=lambda c: (rank.get(c[0], len(rank)), c[1].lower()))]


def project_notes() -> dict[str, str]:
    """Each project's jira.projects description, by upper-cased key."""
    try:
        described, _ = config.resolve("jira.projects")
    except click.ClickException:
        return {}
    return {key.upper(): str(value) for key, value in described.items()} if isinstance(described, dict) else {}


def multi_filter(key: str, label: str, options: list[str], notes: dict[str, str] | None = None) -> str:
    """A dropdown of checkboxes, one per option, matching issues' data-{key}; notes describe options.
    None checked shows them all."""
    notes = notes or {}
    boxes = "".join(
        f'<label><input type="checkbox" value="{html.escape(o)}"> {html.escape(o)}'
        + (f' <span class="multi-note">{html.escape(notes[o])}</span>' if notes.get(o) else "")
        + "</label>"
        for o in options
    )
    return (
        f'<details class="multi" data-key="{key}"><summary>{html.escape(label)} <span class="multi-label">all</span></summary>'
        f'<div class="multi-menu" role="group" aria-label="{html.escape(label)}">{boxes}'
        '<button type="button" class="multi-clear">show all</button></div></details>'
    )


def issue_node(issue: dict, top: bool, workspaces: dict[str, str]) -> str:
    """An issue's line and, nested beneath it, its children's; a top-level issue names any parent
    it has, as that isn't shown, and one with a workspace is marked."""
    url = html.escape(jira.issue_url(issue["key"]))
    line = [
        f'<a href="{url}" target="_blank">{html.escape(issue["key"])}</a>',
        f'<span class="type">{html.escape(issue["type"])}</span>',
        f'<span class="status cat-{html.escape(issue["category"])}">{html.escape(issue["status"])}</span>',
        f'<span class="summary">{html.escape(issue["summary"])}</span>',
    ]
    workspace = issue_workspace(issue, workspaces)
    if workspace:
        line.append(f'<span class="ws-badge" title="workspace {html.escape(workspace)}">ws</span>')
    if not issue["mine"]:
        line.append(f'<span class="assignee">{html.escape(issue["assignee"] or "unassigned")}</span>')
    elif top and issue["parent"]:
        line.append(f'<span class="assignee">in {html.escape(issue["parent"])}</span>')
    kids = "".join(issue_node(child, False, workspaces) for child in issue["children"])
    key = html.escape(issue["key"])
    if kids:
        twist = (
            f'<button type="button" class="twist" aria-expanded="true"'
            f' aria-label="collapse {key}">{CHEVRON_ICON}</button>'
        )
    else:
        twist = '<span class="twist"></span>'
    mine = "" if issue["mine"] else " other"
    return (
        f'<li class="issue{mine}" data-key="{key}" data-project="{html.escape(issue_project(issue))}"'
        f' data-status="{html.escape(issue["status"])}"'
        f"{issue_data(issue, workspaces)}>"
        f'<div class="node">{twist}{"".join(line)}</div>'
        + (f'<ul>{kids}</ul>' if kids else "")
        + "</li>"
    )


# asks before creating a workspace for an issue double-clicked in the tree, as `jira ls -i` does, or
# linking it to one that exists; {options} is the existing workspaces
WS_DIALOG = """<dialog class="ws-create" aria-labelledby="ws-create-title">
<form method="post" action="/ws/create">
<h3 id="ws-create-title">No workspace for <span class="ws-key"></span></h3>
<fieldset class="ws-for" hidden><legend>workspace for</legend>
<label><input type="radio" name="for" value="issue" checked> <span class="ws-for-issue"></span></label>
<label><input type="radio" name="for" value="parent"> <span class="ws-for-parent"></span></label>
</fieldset>
<div class="ws-mode" role="radiogroup" aria-label="new or existing workspace"{mode_hidden}>
<label><input type="radio" name="mode" value="create" checked> create a new one</label>
<label><input type="radio" name="mode" value="link"> link an existing one</label>
</div>
<fieldset class="ws-new">
<label>name <input type="text" name="name" required></label>
<label>repos <input type="text" name="repos" placeholder="comma separated"></label>
<label>extra dirs <input type="text" name="extra_dirs" placeholder="comma separated"></label>
<label>description <input type="text" name="description"></label>
<input type="hidden" name="issue_name">
</fieldset>
<fieldset class="ws-link" hidden disabled>
<label>workspace <select name="name" required>{options}</select></label>
</fieldset>
<input type="hidden" name="key">
<div class="actions"><button type="button" class="cancel">cancel</button><button class="create">create</button></div>
</form></dialog>"""


def ws_dialog(workspaces: list[str]) -> str:
    """WS_DIALOG offering workspaces to link to, if there are any."""
    options = "".join(f'<option value="{html.escape(n)}">{html.escape(n)}</option>' for n in workspaces)
    return WS_DIALOG.format(options=options, mode_hidden="" if workspaces else " hidden")


def issue_tree(heading: str, issues: list[dict] | str | None, workspaces: list[dict] = ()) -> str:
    """The issues assigned to you as jira.issue_tree nests them; issues is None before it's loaded, or
    the error message when that failed. Double-clicking an issue opens its workspace, one of workspaces
    (as workspace_rows gives them), or offers to create one or link one."""
    if not issues or isinstance(issues, str):
        if issues is None:
            message = NOT_LOADED
        else:
            message = f"jira: {issues}" if issues else NO_ISSUES
        rows = [f'<p class="empty">{html.escape(message)}</p>']
        return "\n".join(section("jira", heading, (), rows, tree=True))
    names = ws.issue_workspaces([(row["dir"], row.get("issues")) for row in workspaces])
    dialog = ws_dialog([row["dir"] for row in workspaces])
    rows = ['<ul class="tree">', *(issue_node(issue, True, names) for issue in issues), "</ul>", dialog]
    projects = sorted({issue_project(issue) for issue in tree_issues(issues)})
    pickers = multi_filter("project", "projects", projects, project_notes()) + multi_filter(
        "status", "status", tree_statuses(issues)
    )
    return "\n".join(section("jira", heading, (), rows, tree=True, extra=pickers))


WS_HEADER = ("NAME", "ISSUE", "DESCRIPTION", "REPOS", "EXTRA")
NO_WORKSPACES = "no workspaces"


def workspace_table(heading: str, rows: list[dict] | str | None) -> str:
    """Workspaces in ws.dir; rows is None before it's loaded, or the error message when that failed.
    Each row opens as `ws open` does."""
    if not rows or isinstance(rows, str):
        if rows is None:
            message = NOT_LOADED
        else:
            message = f"workspaces: {rows}" if rows else NO_WORKSPACES
        body = empty_row(WS_HEADER, len(WS_HEADER) + 1, message)
        return "\n".join(section("workspaces", heading, (), body))

    def listed(value: object) -> str:
        return ", ".join(map(str, value)) if isinstance(value, list) else ""

    out = [header_row(WS_HEADER, 1)]
    for row in rows:
        name = html.escape(row["dir"])
        cells = [
            name,
            html.escape(row.get("issue_name") or ""),
            html.escape(row.get("description") or ""),
            html.escape(listed(row.get("repos"))),
            html.escape(listed(row.get("extra_dirs"))),
        ]
        form = (
            f'<form method="post" action="/open">'
            f'<input type="hidden" name="name" value="{name}"><button>open</button></form>'
        )
        out.append(
            '<tr class="ws">'
            + "".join(f"<td>{cell}</td>" for cell in cells)
            + f'<td><div class="actions">{form}</div></td></tr>'
        )
    return "\n".join(section("workspaces", heading, (), out))


KEYS = (
    "j/k move · enter review, open issue, or open workspace · o open in browser · r mark your draft ready"
    " · u enable auto-merge on your PR · x check your PR for bulk actions · t or 1-4 switch page"
    " · h/l close or open a Jira issue's children · m switch table · c collapse table · a toggle filters"
    " · / search repo or title"
)


def page_shell(
    title: str, header: str, main: str, script: str, message: str = "", extra: str = "", nav: str = ""
) -> str:
    """A page with STYLE, header, any dismissable message atop main, and script.
    extra sits between header and main; nav is a sidebar beside main."""
    parts = [
        "<!doctype html><html><head><meta charset=utf-8>",
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{html.escape(title)}</title><style>{STYLE}</style></head><body>",
        f'<header><span class="brand">be</span>{header}</header>',
        extra,
        f'<div class="shell">{nav}<main>' if nav else "<main>",
    ]
    if message:
        parts.append(
            f'<p class="msg"><span>{html.escape(message)}</span>'
            '<button type="button" class="dismiss" aria-label="dismiss">✕</button></p>'
        )
    close = "</main></div>" if nav else "</main>"
    parts.append(f"{main}{close}<script>{script}</script></body></html>")
    return "\n".join(parts)


def review_agent(agent: str | None) -> str:
    """claude or cursor; anything else falls back to claude, the pr.agent default."""
    name = str(agent or "").lower()
    return name if name in pr.AGENTS else "claude"


def agent_toggle(agent: str) -> str:
    """The reviews page's claude/cursor switch. agent is the one shown selected."""
    buttons = "".join(
        f'<button type="button" class="agent-choice" role="radio" data-agent="{name}"'
        f' aria-checked="{"true" if name == agent else "false"}">{name}</button>'
        for name in pr.AGENTS
    )
    return (
        '<div class="agent"><span class="agent-label" id="agent-label">review agent</span>'
        f'<div class="agent-choices" role="radiogroup" aria-labelledby="agent-label">{buttons}</div></div>'
    )


SIDEBAR_ICON = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<rect x="3" y="3" width="18" height="18" rx="2"></rect><path d="M9 3v18"></path></svg>'
)


def page_nav() -> str:
    """My work and reviews, in a sidebar the header button collapses."""
    buttons = "".join(
        f'<button type="button" class="nav" data-tab="{tab}">'
        f'<span class="nav-label">{html.escape(label)}</span><span class="count"></span></button>'
        for tab, label, _ in TABS
    )
    return f'<nav class="sidebar" aria-label="pages">{buttons}</nav>'


def render_page(loaded: dict[str, list[dict] | str], message: str = "", agent: str = "claude") -> str:
    """The `pr ls` tables, the `jira ls` table and the workspaces on two pages, each loaded on refresh, with the `-i` actions.
    The reviews page's toggle chooses the agent a review button starts; agent is its starting choice."""
    agent = review_agent(agent)
    headings = dict(TABLES)
    header = (
        f'<button type="button" class="sidebar-toggle" aria-expanded="true"'
        f' aria-label="collapse sidebar">{SIDEBAR_ICON}</button>'
        '<div class="header-links"><button type="button" class="keys-toggle" aria-expanded="false">? keys</button>'
        '<a class="nav-link" href="/config">config</a></div>'
    )
    parts = []
    for tab, _, tables in TABS:
        parts.append(f'<div class="tab-panel" data-tab="{tab}">')
        if tab == "reviews":
            parts.append(agent_toggle(agent))
        for table in tables:
            if table == "jira":
                spaces = loaded.get("workspaces")
                spaces = spaces if isinstance(spaces, list) else []
                parts.append(issue_tree(headings[table], loaded.get(table), spaces))
            elif table == "workspaces":
                parts.append(workspace_table(headings[table], loaded.get(table)))
            else:
                parts.append(pr_table(table, headings[table], loaded.get(table), agent))
        parts.append("</div>")
    keys = f'<p class="keys" hidden>{KEYS}</p>'
    return page_shell("be", header, "\n".join(parts), SCRIPT, message, extra=keys, nav=page_nav())


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
            if s.key == "pr.agent":
                flag_note = (
                    f"{FLAGS[s.key]} was given, so the reviews page starts on it;"
                    " its toggle picks the agent for a review"
                )
            else:
                flag_note = f"{FLAGS[s.key]} was given, so `be server` uses it until restarted"
            notes += f'<div class="note">{flag_note}</div>'
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
