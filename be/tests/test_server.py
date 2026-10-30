import os

import click
from click.testing import CliRunner
from fastapi.testclient import TestClient
import pytest

import be.server
from be import claude_sessions, cmux, config, jira
from be.commands import pr, ws
from be.server import api, app, views

PRS = [
    {"number": 7, "repo": "acme/api", "title": "Fix <login>", "checks": "pass", "approvals": 2, "draft": False, "author": "dev", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
    {"number": 1234, "repo": "acme/web-app", "title": "Add page", "checks": "fail", "approvals": 0, "draft": False, "author": "dev", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
    {"number": 9, "repo": "acme/api", "title": "WIP", "checks": "pass", "approvals": 0, "draft": True, "author": "dev", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
    {"number": 5, "repo": "acme/api", "title": "Bump", "checks": "pass", "approvals": 0, "draft": False, "author": "renovate", "approved": False, "auto_merge": False, "merge_flag": "--squash"},
]


def node(key, type, summary, mine=True, category="indeterminate", parent="", parent_type="", children=()):
    status = {"new": "To Do", "indeterminate": "In Progress"}[category]
    return {
        "key": key, "type": type, "summary": summary, "status": status, "category": category,
        "assignee": "Me" if mine else "Pat", "parent": parent, "parent_type": parent_type,
        "parent_summary": "Big thing" if parent_type else "", "mine": mine, "children": list(children),
    }


ISSUES = [
    node("ACME-1", "Feature", "Big thing", parent="ACME-0", children=[
        node("ACME-12", "Bug", "Fix <login>", parent="ACME-1", parent_type="Feature"),
        node("ACME-13", "Story", "Theirs", mine=False, category="new", parent="ACME-1"),
    ]),
    node("ACME-20", "Story", "Later", category="new"),
]


def client(state=None, static=None):
    return TestClient(app.create_app(state or api.State(), static=static))


@pytest.fixture
def serve(monkeypatch, tmp_path):
    fetched = []
    monkeypatch.setattr(pr, "review_requests", lambda: fetched.append("review") or PRS)
    monkeypatch.setattr(pr, "team_review_requests", lambda: fetched.append("team") or PRS[:2])
    monkeypatch.setattr(pr, "authored_prs", lambda: fetched.append("mine") or [dict(p) for p in PRS[:3]])
    monkeypatch.setattr(jira, "issue_tree", lambda: fetched.append("jira") or [])
    reviews = []
    monkeypatch.setattr(pr, "open_review", lambda *args: reviews.append(args))
    # every flag given, as the parent is
    yield client(api.State(str(tmp_path), fixed=tuple(views.FLAGS))), fetched, reviews, str(tmp_path)


def table(c, name, refresh=False):
    resp = c.get(f"/api/tables/{name}", params={"refresh": "true"} if refresh else None)
    assert resp.status_code == 200, resp.text
    return resp.json()


def numbers(data):
    return [p["number"] for p in data["rows"]]


def test_tables_load_on_refresh(serve):
    c, fetched, _, _ = serve
    # the jira tree loads the first time it's read; the PR tables wait for refresh
    assert table(c, "jira")["rows"] == [] and fetched == ["jira"]
    review = table(c, "review")
    assert review["rows"] is None and review["error"] is None and review["empty"] == "no review requests"
    assert fetched == ["jira"]
    assert numbers(table(c, "review", refresh=True)) == [7, 1234, 9, 5]
    assert numbers(table(c, "team", refresh=True)) == [7, 1234]
    assert fetched == ["jira", "review", "team"]
    # loaded tables are kept, the tree too; refresh fetches again
    assert numbers(table(c, "review")) == [7, 1234, 9, 5]
    table(c, "jira")
    table(c, "jira", refresh=True)
    assert fetched == ["jira", "review", "team", "jira"]
    assert c.get("/api/tables/nope").status_code == 404


def test_pr_rows(serve):
    c, _, _, _ = serve
    rows = table(c, "review", refresh=True)["rows"]
    assert rows[0]["url"] == "https://github.com/acme/api/pull/7"
    assert rows[0]["title"] == "Fix <login>"
    # the merge flag is the server's business; renovate's PRs are marked for the filter
    assert "merge_flag" not in rows[0]
    assert [p["renovate"] for p in rows] == [False, False, False, True]
    # only your PRs say what can be done to them
    assert "actions" not in rows[0]
    mine = table(c, "mine", refresh=True)["rows"]
    assert [p["actions"] for p in mine] == [["automerge"], ["automerge"], ["ready"]]


def test_mine_actions():
    # approved gets merge alongside auto-merge; nothing once auto-merge is on; drafts only go ready
    assert views.mine_actions({**PRS[0], "approved": True}) == ["automerge", "merge"]
    assert views.mine_actions({**PRS[0], "approved": True, "auto_merge": True}) == []
    assert views.mine_actions({**PRS[2], "approved": True}) == ["ready"]


def test_tables_show_fetch_errors(serve, monkeypatch):
    c, _, _, _ = serve

    def fail():
        raise jira.JiraError("HTTP 401 from x")

    def gh_fail():
        raise click.ClickException("gh not found")

    monkeypatch.setattr(jira, "issue_tree", fail)
    monkeypatch.setattr(pr, "authored_prs", gh_fail)
    assert table(c, "jira")["error"] == "HTTP 401 from x"
    mine = table(c, "mine", refresh=True)
    assert mine["error"] == "gh not found" and mine["rows"] is None


def test_issue_tree(serve, monkeypatch):
    c, _, _, _ = serve
    monkeypatch.setenv("JIRA_URL", "https://x.atlassian.net")
    config.set_value("jira.projects.OPS", "Operations")
    issues = [*ISSUES, node("OPS-3", "Task", "Ops thing", children=[node("ACME-30", "Bug", "Nested", parent="OPS-3")])]
    monkeypatch.setattr(jira, "issue_tree", lambda: issues)
    data = table(c, "jira")
    feature = data["rows"][0]
    assert feature["url"] == "https://x.atlassian.net/browse/ACME-1"
    assert feature["project"] == "ACME" and feature["workspace"] == ""
    assert [child["key"] for child in feature["children"]] == ["ACME-12", "ACME-13"]
    # a bug under a feature can get a workspace for the feature instead
    assert feature["children"][0]["parent_offer"] is True
    assert feature["parent_offer"] is False and feature["children"][1]["parent_offer"] is False
    # the filters offer each project, described as jira.projects has it, and each status, To Do first
    assert data["projects"] == [{"key": "ACME", "note": ""}, {"key": "OPS", "note": "Operations"}]
    assert data["statuses"] == ["To Do", "In Progress"]


def test_issue_workspaces(serve, tmp_path, monkeypatch):
    c, _, _, _ = serve
    monkeypatch.setenv("JIRA_URL", "https://x.atlassian.net")
    spaces = tmp_path / "spaces"
    (spaces / "acme-20").mkdir(parents=True)
    (spaces / "login").mkdir()
    (spaces / "login" / "workspace.yml").write_text("issues:\n- acme-13\n")
    config.set_value("ws.dir", str(spaces))
    monkeypatch.setattr(jira, "issue_tree", lambda: ISSUES)
    rows = table(c, "jira")["rows"]
    # a workspace is found by key ignoring case, or by a link; a child finds its parent's
    assert rows[1]["workspace"] == "acme-20"
    assert rows[0]["children"][1]["workspace"] == "login"
    assert rows[0]["workspace"] == "" and rows[0]["children"][0]["workspace"] == ""


def test_workspaces_and_open(serve, tmp_path, monkeypatch):
    c, _, _, _ = serve
    spaces = tmp_path / "spaces"
    root = spaces / "proj"
    (root / "api" / ".git").mkdir(parents=True)
    (root / "workspace.yml").write_text(
        "name: proj\ndescription: the work\nissue_name: Fix login\nextra_dirs:\n- /tmp/notes\n"
    )
    config.set_value("ws.dir", str(spaces))
    opened = []
    monkeypatch.setattr(ws, "open_root", lambda root, model=None, window=None: opened.append((root, model, window)))
    [row] = table(c, "workspaces")["rows"]
    assert row["dir"] == "proj" and row["description"] == "the work" and row["issue_name"] == "Fix login"
    assert row["repos"] == ["api"] and row["extra_dirs"] == ["/tmp/notes"]
    resp = c.post("/api/workspaces/proj/open")
    assert resp.json() == {"message": "opened proj"} and opened == [(root.resolve(), None, None)]
    resp = c.post("/api/workspaces/missing/open")
    assert resp.status_code == 422 and resp.json()["message"] == "missing: missing is not a workspace"
    assert c.post("/api/workspaces/../open").status_code in (400, 404)
    assert c.post("/api/workspaces/%2E%2E/open").status_code in (400, 404)
    assert len(opened) == 1


def test_workspaces_without_dir(serve):
    data = table(serve[0], "workspaces")
    assert data["rows"] is None and "ws.dir" in data["error"]


def test_create_workspace(serve, tmp_path, monkeypatch):
    c, _, _, _ = serve
    spaces = tmp_path / "spaces"
    (spaces / "taken").mkdir(parents=True)
    config.set_value("ws.dir", str(spaces))
    created = []

    def create(*args):
        os.chdir(spaces)
        created.append(args)

    monkeypatch.setattr(ws, "create_workspace", create)
    cwd = os.getcwd()
    form = {"name": "ACME-12", "repos": "api, web", "extra_dirs": "", "description": "d", "issue_name": "Fix login"}
    assert c.post("/api/workspaces", json=form).json() == {"message": "created ACME-12"}
    assert created == [("ACME-12", "api, web", "", "d", str(spaces), "claude-opus-5-5", None, None, "Fix login")]
    # the server stays where it was
    assert os.getcwd() == cwd
    resp = c.post("/api/workspaces", json={**form, "name": "taken"})
    assert resp.status_code == 422 and "taken already exists" in resp.json()["message"] and len(created) == 1
    assert c.post("/api/workspaces", json={**form, "name": "../x"}).status_code == 400


def test_link_workspace(serve, tmp_path, monkeypatch):
    c, _, _, _ = serve
    spaces = tmp_path / "spaces"
    (spaces / "proj").mkdir(parents=True)
    config.set_value("ws.dir", str(spaces))
    opened = []
    monkeypatch.setattr(ws, "open_root", lambda root, model=None, window=None: opened.append(root))
    resp = c.post("/api/workspaces/proj/link", json={"key": "acme-12"})
    assert resp.json() == {"message": "linked ACME-12 to proj; opened proj"}
    assert ws.read_manifest(spaces / "proj")["issues"] == ["ACME-12"]
    assert opened == [(spaces / "proj").resolve()]
    # the tree now knows the link
    monkeypatch.setenv("JIRA_URL", "https://x.atlassian.net")
    monkeypatch.setattr(jira, "issue_tree", lambda: ISSUES)
    assert table(c, "jira", refresh=True)["rows"][0]["children"][0]["workspace"] == "proj"
    resp = c.post("/api/workspaces/nope/link", json={"key": "ACME-12"})
    assert resp.status_code == 422 and "nope is not a workspace" in resp.json()["message"]
    assert c.post("/api/workspaces/proj/link", json={"key": "not a key"}).status_code == 400


def test_start_work(serve, tmp_path, monkeypatch):
    c, _, _, _ = serve
    spaces = tmp_path / "spaces"
    (spaces / "proj").mkdir(parents=True)
    config.set_value("ws.dir", str(spaces))
    started = []
    monkeypatch.setattr(ws, "start_work", lambda root, key, model=None, window=None: started.append((root, key)))
    resp = c.post("/api/workspaces/proj/start", json={"key": "acme-12"})
    assert resp.json() == {"message": "started ACME-12 in proj"}
    assert started == [((spaces / "proj").resolve(), "ACME-12")]
    resp = c.post("/api/workspaces/nope/start", json={"key": "ACME-12"})
    assert resp.status_code == 422 and "nope is not a workspace" in resp.json()["message"]
    assert c.post("/api/workspaces/proj/start", json={"key": "not a key"}).status_code == 400
    assert c.post("/api/workspaces/%2E%2E/start", json={"key": "ACME-12"}).status_code in (400, 404)
    assert len(started) == 1


def test_open_vscode(serve, tmp_path, monkeypatch):
    c, _, _, _ = serve
    spaces = tmp_path / "spaces"
    (spaces / "proj").mkdir(parents=True)
    config.set_value("ws.dir", str(spaces))
    runs = []
    monkeypatch.setattr(ws.subprocess, "run", lambda args, **kw: runs.append(args) or ws.subprocess.CompletedProcess(args, 0, "", ""))
    assert c.post("/api/workspaces/proj/vscode").json() == {"message": "opened proj in VS Code"}
    assert runs == [["open", "-a", "Visual Studio Code", str((spaces / "proj").resolve())]]
    monkeypatch.setattr(ws.subprocess, "run", lambda args, **kw: ws.subprocess.CompletedProcess(args, 1, "", "no app"))
    resp = c.post("/api/workspaces/proj/vscode")
    assert resp.status_code == 422 and "could not open VS Code: no app" in resp.json()["message"]
    assert c.post("/api/workspaces/nope/vscode").status_code == 422


def test_open_notes(serve, tmp_path, monkeypatch):
    c, _, _, _ = serve
    runs = []
    monkeypatch.setattr(ws.subprocess, "run", lambda args, **kw: runs.append(args) or ws.subprocess.CompletedProcess(args, 0, "", ""))
    config.set_value("notes.dir", str(tmp_path))
    assert c.post("/api/notes/vscode").json() == {"message": f"opened {tmp_path} in VS Code"}
    assert runs == [["open", "-a", "Visual Studio Code", str(tmp_path)]]
    config.set_value("notes.dir", str(tmp_path / "nope"))
    resp = c.post("/api/notes/vscode")
    assert resp.status_code == 422 and "not found; set notes.dir" in resp.json()["message"]
    assert len(runs) == 1


def test_open_configs(serve, tmp_path, monkeypatch):
    c, _, _, _ = serve
    runs = []
    monkeypatch.setattr(ws.subprocess, "run", lambda args, **kw: runs.append(args) or ws.subprocess.CompletedProcess(args, 0, "", ""))
    config.set_value("notes.dir", str(tmp_path))
    resp = c.post("/api/configs/vscode")
    assert resp.status_code == 422 and "not found; set configs.workspace" in resp.json()["message"]
    # by default, in notes.dir
    default = tmp_path / "workspaces" / "configs.code-workspace"
    default.parent.mkdir()
    default.write_text("{}")
    c.post("/api/configs/vscode")
    other = tmp_path / "other.code-workspace"
    other.write_text("{}")
    config.set_value("configs.workspace", str(other))
    assert c.post("/api/configs/vscode").json() == {"message": f"opened {other} in VS Code"}
    assert [r[-1] for r in runs] == [str(default), str(other)]


def test_delete_workspace(serve, tmp_path, monkeypatch):
    c, _, _, _ = serve
    spaces = tmp_path / "spaces"
    (spaces / "proj" / "api").mkdir(parents=True)
    config.set_value("ws.dir", str(spaces))
    layouts = []
    monkeypatch.setattr(cmux, "find_cmux", lambda: "cmux")
    monkeypatch.setattr(cmux, "delete_layout", lambda binary, name: layouts.append(name) or True)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = (spaces / "proj").resolve()
    folder = tmp_path / "home" / ".claude" / "projects" / claude_sessions.project_key(root)
    folder.mkdir(parents=True)
    (folder / "11111111-1111-1111-1111-111111111111.jsonl").write_text(f'{{"type":"user","cwd":"{root}"}}\n')
    assert c.delete("/api/workspaces/proj").json() == {"message": "deleted proj and 1 claude session"}
    assert not (spaces / "proj").exists() and layouts == ["proj"]
    assert not folder.exists()
    resp = c.delete("/api/workspaces/proj")
    assert resp.status_code == 422 and "proj is not a workspace" in resp.json()["message"]
    assert c.delete("/api/workspaces/%2E%2E").status_code in (400, 404, 405)
    assert spaces.is_dir()


def test_workspace_sessions(serve, tmp_path, monkeypatch):
    c, _, _, _ = serve
    spaces = tmp_path / "spaces"
    root = (spaces / "proj").resolve()
    root.mkdir(parents=True)
    config.set_value("ws.dir", str(spaces))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    folder = tmp_path / "home" / ".claude" / "projects" / claude_sessions.project_key(root)
    folder.mkdir(parents=True)
    sid = "11111111-1111-1111-1111-111111111111"
    (folder / f"{sid}.jsonl").write_text(
        f'{{"type":"user","cwd":"{root}"}}\n{{"type":"ai-title","aiTitle":"Fix login"}}\n'
    )
    sessions = c.get("/api/workspaces/proj/sessions").json()["sessions"]
    assert [(s["id"], s["title"]) for s in sessions] == [(sid, "Fix login")]
    resumed = []
    monkeypatch.setattr(ws, "resume_session", lambda root, cwd, sid, model=None, window=None: resumed.append((root, cwd, sid)))
    assert c.post(f"/api/workspaces/proj/sessions/{sid}/resume").json() == {"message": "resumed Fix login"}
    assert resumed == [(root, root, sid)]
    resp = c.post("/api/workspaces/proj/sessions/nope/resume")
    assert resp.status_code == 422 and "not a session id" in resp.json()["message"]
    assert c.delete(f"/api/workspaces/proj/sessions/{sid}").json() == {"message": "deleted Fix login"}
    assert c.get("/api/workspaces/proj/sessions").json() == {"sessions": []}
    assert c.delete(f"/api/workspaces/proj/sessions/{sid}").status_code == 422


def test_cloud_issue(serve, monkeypatch):
    c, _, _, _ = serve
    filed = []
    monkeypatch.setattr(ws, "cloud_issue", lambda text, model=None, window=None: filed.append(text))
    resp = c.post("/api/jira/cloud-issue", json={"text": "  rotate the NAT IP\n"})
    assert resp.json() == {"message": "opened claude to file a cloud issue"}
    assert filed == ["rotate the NAT IP"]
    assert c.post("/api/jira/cloud-issue", json={"text": "  "}).status_code == 400
    assert len(filed) == 1


def test_cloud_issue_reports_failure(serve, monkeypatch):
    c, _, _, _ = serve

    def fail(text, model=None, window=None):
        raise click.ClickException("cmux not found")

    monkeypatch.setattr(ws, "cloud_issue", fail)
    resp = c.post("/api/jira/cloud-issue", json={"text": "x"})
    assert resp.status_code == 422 and "cmux not found" in resp.json()["message"]


def test_review(serve):
    c, _, reviews, parent = serve
    resp = c.post("/api/prs/review", json={"repo": "acme/api", "number": 7})
    assert resp.json() == {"message": "opened acme/api#7"}
    assert reviews == [("acme/api", 7, parent, "claude", None, None)]


def test_review_uses_posted_agent(serve):
    c, _, reviews, parent = serve
    c.post("/api/prs/review", json={"repo": "acme/api", "number": 7, "agent": "cursor"})
    assert reviews == [("acme/api", 7, parent, "cursor", None, None)]
    c.post("/api/prs/review", json={"repo": "acme/api", "number": 8, "agent": "Claude"})
    assert reviews[-1][3] == "claude"
    # an unknown agent falls back to the configured one
    c.post("/api/prs/review", json={"repo": "acme/api", "number": 9, "agent": "nope"})
    assert reviews[-1][3] == "claude"


def test_review_shows_errors(serve, monkeypatch):
    c, _, _, _ = serve

    def fail(*args):
        raise click.ClickException("clone failed")

    monkeypatch.setattr(pr, "open_review", fail)
    resp = c.post("/api/prs/review", json={"repo": "acme/api", "number": 7})
    assert resp.status_code == 422 and resp.json() == {"message": "acme/api#7: clone failed"}
    resp = c.post("/api/prs/review", json={"repo": "x", "number": "abc"})
    assert resp.status_code == 400 and "number" in resp.json()["message"]


def test_merge(serve, monkeypatch):
    c, _, _, _ = serve
    calls = []
    monkeypatch.setattr(pr, "merge", lambda *args: calls.append(args))
    monkeypatch.setattr(pr, "enable_auto_merge", lambda *args: calls.append(("auto", *args)))
    resp = c.post("/api/prs/merge", json={"repo": "acme/api", "number": 7})
    assert resp.status_code == 422 and resp.json()["message"] == "acme/api#7 is not approved" and calls == []
    # auto-merge leaves nothing to do on the PR but keeps its row
    c.post("/api/prs/automerge", json={"repo": "acme/api", "number": 7})
    mine = table(c, "mine")["rows"]
    assert len(mine) == 3 and mine[0]["actions"] == []


def test_merge_removes_row(serve, monkeypatch):
    c, _, _, _ = serve
    monkeypatch.setattr(pr, "authored_prs", lambda: [{**PRS[0], "approved": True}])
    calls = []
    monkeypatch.setattr(pr, "merge", lambda *args: calls.append(args))
    assert table(c, "mine", refresh=True)["rows"][0]["actions"] == ["automerge", "merge"]
    resp = c.post("/api/prs/merge", json={"repo": "acme/api", "number": 7})
    assert resp.json() == {"message": "merged acme/api#7"} and calls == [("acme/api", 7, "--squash")]
    mine = table(c, "mine")
    assert mine["rows"] == [] and mine["empty"] == "no open PRs by you"


def test_mine_actions_run(serve, monkeypatch):
    c, fetched, _, _ = serve
    calls = []
    monkeypatch.setattr(pr, "mark_ready", lambda *args: calls.append(("ready", *args)))
    monkeypatch.setattr(pr, "enable_auto_merge", lambda *args: calls.append(("auto", *args)))
    assert c.post("/api/prs/ready", json={"repo": "acme/api", "number": 9}).json() == {
        "message": "marked acme/api#9 ready for review"
    }
    assert c.post("/api/prs/automerge", json={"repo": "acme/api", "number": 7}).json() == {
        "message": "enabled auto-merge on acme/api#7"
    }
    assert calls == [("ready", "acme/api", 9), ("auto", "acme/api", 7, "--squash")]
    # your PRs are fetched once if needed, then updated in place
    assert fetched == ["mine"]
    # the PR marked ready now offers auto-merge
    assert table(c, "mine")["rows"][2]["actions"] == ["automerge"]
    # PRs that aren't yours are refused
    resp = c.post("/api/prs/automerge", json={"repo": "acme/api", "number": 5})
    assert resp.status_code == 422 and resp.json()["message"] == "acme/api#5 is not one of your open PRs"
    assert len(calls) == 2
    assert c.post("/api/prs/nope", json={"repo": "acme/api", "number": 5}).status_code == 404


def test_mine_action_shows_errors(serve, monkeypatch):
    c, _, _, _ = serve

    def fail(*args):
        raise click.ClickException("auto-merge is not allowed")

    monkeypatch.setattr(pr, "enable_auto_merge", fail)
    resp = c.post("/api/prs/automerge", json={"repo": "acme/api", "number": 7})
    assert resp.status_code == 422 and resp.json()["message"] == "acme/api#7: auto-merge is not allowed"


def bulk(c, action, *prs):
    return c.post("/api/prs/bulk", json={"action": action, "prs": list(prs)})


def test_bulk(serve, monkeypatch):
    c, fetched, _, _ = serve
    calls = []
    monkeypatch.setattr(pr, "mark_ready", lambda *args: calls.append(("ready", *args)))
    monkeypatch.setattr(pr, "enable_auto_merge", lambda *args: calls.append(("auto", *args)))
    done = bulk(c, "automerge", "acme/api#7", "acme/web-app#1234", "acme/api#9", "acme/api#5").json()
    # the draft is skipped, and PRs that aren't yours are refused
    assert calls == [("auto", "acme/api", 7, "--squash"), ("auto", "acme/web-app", 1234, "--squash")]
    assert [(r["pr"], r["ok"]) for r in done["results"]] == [
        ("acme/api#7", True), ("acme/web-app#1234", True), ("acme/api#9", False), ("acme/api#5", False),
    ]
    assert done["message"] == (
        "enabled auto-merge on acme/api#7; enabled auto-merge on acme/web-app#1234;"
        " skipped acme/api#9: no auto-merge on it; acme/api#5 is not one of your open PRs"
    )
    assert fetched == ["mine"]
    bulk(c, "ready", "acme/api#9")
    assert calls[-1] == ("ready", "acme/api", 9)
    assert table(c, "mine")["rows"][2]["actions"] == ["automerge"]


def test_bulk_merge_keeps_going(serve, monkeypatch):
    c, _, _, _ = serve
    monkeypatch.setattr(
        pr, "authored_prs", lambda: [{**PRS[0], "approved": True}, {**PRS[1], "approved": True}]
    )
    merged = []

    def merge(repo, number, flag):
        if number == 7:
            raise click.ClickException("not mergeable")
        merged.append(number)

    monkeypatch.setattr(pr, "merge", merge)
    done = bulk(c, "merge", "acme/api#7", "acme/web-app#1234").json()
    assert merged == [1234]
    assert done["message"] == "acme/api#7: not mergeable; merged acme/web-app#1234"
    # the merged PR is dropped, the failed one stays
    assert numbers(table(c, "mine")) == [7]


def test_bulk_bad_input(serve):
    c, _, _, _ = serve
    resp = bulk(c, "ready")
    assert resp.status_code == 422 and resp.json()["message"] == "no PRs selected"
    for action, prs in (("nope", ["acme/api#7"]), ("ready", ["acme/api#x"]), ("ready", ["#7"])):
        assert bulk(c, action, *prs).status_code == 400


def test_requests_and_fetches_are_logged(serve, caplog):
    c, _, _, _ = serve
    caplog.set_level("INFO", logger="be")
    table(c, "review", refresh=True)
    messages = [r.getMessage() for r in caplog.records]
    assert "fetched 4 rows for review" in messages
    assert any(m.startswith("GET /api/tables/review?refresh=true 200") for m in messages)


def test_failed_fetch_is_logged_as_warning(monkeypatch, caplog):
    def fail(mine):
        raise click.ClickException("gh api graphql failed: boom")

    monkeypatch.setattr(pr, "fetch_prs", fail)
    assert views.fetch_table("mine") == "gh api graphql failed: boom"
    assert [(r.levelname, r.getMessage()) for r in caplog.records] == [
        ("WARNING", "fetching mine failed: gh api graphql failed: boom")
    ]


def test_meta(serve):
    c, _, _, _ = serve
    meta = c.get("/api/meta").json()
    assert meta["agent"] == "claude" and meta["agents"] == ["claude", "cursor"]
    assert meta["config_path"] == str(config.config_path())
    assert client(api.State(agent="Cursor", fixed=("pr.agent",))).get("/api/meta").json()["agent"] == "cursor"


def test_unknown_api_route(serve):
    resp = serve[0].get("/api/nope")
    assert resp.status_code == 404 and "message" in resp.json()


def test_serves_the_app(tmp_path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<div id=root></div>")
    (static / "assets" / "app.js").write_text("console.log(1)")
    c = client(static=static)
    assert c.get("/").text == "<div id=root></div>"
    # the app's own routes load index.html, so a reload works
    assert c.get("/config").text == "<div id=root></div>"
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/api/nope").status_code == 404
    # nothing outside the build
    assert c.get("/..%2F..%2Fetc%2Fpasswd").text == "<div id=root></div>"


def test_unbuilt_app_says_how_to_build(tmp_path):
    resp = client(static=tmp_path / "missing").get("/")
    assert resp.status_code == 503 and "pnpm" in resp.text
    # --dev serves only the API
    assert client(static=None).get("/").status_code == 404


def test_config(isolated_config, monkeypatch):
    config.set_value("git.name", "<Me>")
    config.set_value("jira.token", "hunter2")
    config.set_value("jira.projects.ACME", "Acme")
    config.set_value("interactive", "yes")
    monkeypatch.setenv("WORK_ORG", "acme")
    data = client().get("/api/config").json()
    assert data["path"] == str(isolated_config) and data["error"] is None
    settings = {s["key"]: s for s in data["settings"]}
    assert list(settings) == list(config.SETTINGS)
    # each setting carries its file value
    assert settings["git.name"]["value"] == "<Me>" and settings["git.name"]["source"] == "file"
    assert settings["claude.model"]["value"] == "" and settings["claude.model"]["default"] == "claude-opus-5-5"
    # the env var's value wins, and says so
    assert settings["work_org"]["source"] == "env:WORK_ORG"
    assert settings["work_org"]["notes"] == ["WORK_ORG overrides the file: acme"]
    assert settings["jira.token"]["secret"] is True and settings["jira.token"]["value"] == "hunter2"
    # dropdowns offer their choices; the file's value may be outside them
    assert settings["interactive"]["choices"] == ["true", "false"] and settings["interactive"]["value"] == "yes"
    assert "warning" in settings["server.log_level"]["choices"]
    # the map has its entries
    assert settings["jira.projects"]["entries"] == {"ACME": "Acme"} and "value" not in settings["jira.projects"]
    assert [key for key, s in settings.items() if s["notes"]] == ["work_org"]


def test_config_notes_flags():
    def notes(fixed, key):
        settings = client(api.State(fixed=fixed)).get("/api/config").json()["settings"]
        return next(s["notes"] for s in settings if s["key"] == key)

    # settings given as flags say a save waits for a restart; pr.agent's toggle can still pick
    assert "--parent was given" in notes(("pr.dir",), "pr.dir")[0]
    assert "its toggle picks the agent" in notes(("pr.agent",), "pr.agent")[0]
    assert notes((), "pr.dir") == []


def test_config_masks_env_secret(monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "s3cret")
    resp = client().get("/api/config")
    assert "JIRA_API_TOKEN overrides the file: ********" in resp.text and "s3cret" not in resp.text


def test_config_invalid_file(isolated_config):
    isolated_config.parent.mkdir(parents=True)
    isolated_config.write_text("not = [toml")
    data = client().get("/api/config").json()
    assert "invalid config file" in data["error"] and data["settings"] == []


def test_set_config(serve):
    c, _, _, _ = serve
    assert c.put("/api/config/git.email", json={"value": " me@example.com "}).json() == {"message": "saved git.email"}
    assert config.file_value("git.email") == "me@example.com"
    assert c.delete("/api/config/git.email").json() == {"message": "removed git.email"}
    assert config.file_value("git.email") is None
    # saving an empty value removes it too
    c.put("/api/config/git.name", json={"value": "Me"})
    assert c.put("/api/config/git.name", json={"value": ""}).json() == {"message": "removed git.name"}
    assert config.load_file() == {}


def test_set_config_map_entries(serve):
    c, _, _, _ = serve
    resp = c.put("/api/config/jira.projects", json={"name": "OPS", "value": "Operations"})
    assert resp.json() == {"message": "saved jira.projects.OPS"}
    c.put("/api/config/jira.projects.OPS", json={"value": "Ops"})
    assert config.file_value("jira.projects") == {"OPS": "Ops"}
    for name in ("", "a.b"):
        resp = c.put("/api/config/jira.projects", json={"name": name, "value": "x"})
        assert resp.status_code == 422 and "give the new entry a name" in resp.json()["message"]
    assert c.delete("/api/config/jira.projects.OPS").json() == {"message": "removed jira.projects.OPS"}
    assert config.load_file() == {}


def test_set_config_errors(serve, monkeypatch):
    c, _, _, _ = serve
    resp = c.put("/api/config/server.log_level", json={"value": "loud"})
    assert resp.status_code == 422
    assert resp.json()["message"] == "server.log_level must be one of debug, info, warning, error, not 'loud'"
    assert c.put("/api/config/nope", json={"value": "x"}).json()["message"].startswith("nope: unknown key")
    monkeypatch.setenv("WORK_ORG", "acme")
    assert c.put("/api/config/work_org", json={"value": "x"}).json() == {
        "message": "saved work_org; WORK_ORG is set and overrides it"
    }


@pytest.fixture
def serve_live(monkeypatch):
    """The server with no flags given, so pr.dir and server.log_level are reread."""
    reviews = []
    monkeypatch.setattr(pr, "open_review", lambda *args: reviews.append(args))
    logger = be.server.logging.getLogger("be")
    monkeypatch.setattr(logger, "level", logger.level)
    yield client(api.State()), reviews, logger


def test_config_applies_live(serve_live, tmp_path):
    c, reviews, logger = serve_live
    review = {"repo": "acme/api", "number": 7}
    c.put("/api/config/pr.dir", json={"value": str(tmp_path)})
    c.post("/api/prs/review", json=review)
    assert reviews == [("acme/api", 7, str(tmp_path), "claude", None, None)]
    c.put("/api/config/pr.agent", json={"value": "cursor"})
    assert c.get("/api/meta").json()["agent"] == "cursor"
    c.post("/api/prs/review", json=review)
    assert reviews[-1] == ("acme/api", 7, str(tmp_path), "cursor", None, None)
    # the reviews page's toggle wins over the setting
    c.post("/api/prs/review", json={**review, "agent": "claude"})
    assert reviews[-1][3] == "claude"
    c.put("/api/config/cursor.pr.model", json={"value": "composer-x"})
    c.put("/api/config/claude.pr.model", json={"value": "opus-x"})
    c.post("/api/prs/review", json=review)
    assert reviews[-1] == ("acme/api", 7, str(tmp_path), "cursor", "opus-x", "composer-x")
    c.put("/api/config/server.log_level", json={"value": "debug"})
    assert logger.level == be.server.logging.DEBUG
    c.delete("/api/config/server.log_level")
    assert logger.level == be.server.logging.WARNING


class Stopped(Exception):
    pass


@pytest.fixture
def started(monkeypatch):
    """What `be server` was started with, stopping before it serves."""
    made = []

    def run(app, **kw):
        made.append((app, kw))
        raise Stopped

    monkeypatch.setattr(be.server.uvicorn, "run", run)
    logger = be.server.logging.getLogger("be")
    monkeypatch.setattr(logger, "level", logger.level)
    return made


@pytest.mark.parametrize(
    "args, env, level",
    [([], {}, "WARNING"), (["--log-level", "DEBUG"], {}, "DEBUG"), ([], {"BE_SERVER_LOG_LEVEL": "info"}, "INFO")],
)
def test_log_level_option(started, monkeypatch, args, env, level):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    result = CliRunner().invoke(be.server.server, ["--no-open", *args])
    assert isinstance(result.exception, Stopped)
    assert be.server.logging.getLevelName(be.server.logging.getLogger("be").level) == level


def test_log_level_rejects_unknown_levels():
    result = CliRunner().invoke(be.server.server, ["--no-open", "--log-level", "loud"])
    assert result.exit_code == 2 and "loud" in result.output


def test_flags_fix_settings(started, tmp_path):
    CliRunner().invoke(be.server.server, ["--no-open"])
    CliRunner().invoke(be.server.server, ["--no-open", "--parent", str(tmp_path)], env={"BE_SERVER_LOG_LEVEL": "info"})
    CliRunner().invoke(be.server.server, ["--no-open", "--claude-model", "opus-x", "--cursor-model", "composer-x"])
    # only flags fix a setting; an env var or the file is reread when used
    states = [app.state.be for app, _ in started]
    assert [s.fixed for s in states] == [(), ("pr.dir",), ("claude.pr.model", "cursor.pr.model")]
    assert states[1].parent == str(tmp_path) and states[2].claude_model == "opus-x"
    assert started[0][1]["host"] == "127.0.0.1" and started[0][1]["port"] == 8765


def test_dev_serves_only_the_api(started, monkeypatch):
    launched = []
    monkeypatch.setattr(be.server.click, "launch", launched.append)
    result = CliRunner().invoke(be.server.server, ["--dev"])
    assert be.server.DEV_URL in result.output and launched == [be.server.DEV_URL]
    app_ = started[0][0]
    assert not any(getattr(r, "path", "") == "/{path:path}" for r in app_.routes)


def test_claude_usage(serve, monkeypatch):
    from be import claude_usage
    from tests.test_claude_usage import TEXT

    c, *_ = serve
    monkeypatch.setattr(claude_usage, "fetch", lambda: TEXT)
    data = c.get("/api/claude-usage").json()
    assert [(l["label"], l["percent"]) for l in data["limits"]] == [("Current session", 9), ("Current week (all models)", 18)]
    assert data["error"] is None

    def fail():
        raise click.ClickException("claude is not installed or not on PATH")

    monkeypatch.setattr(claude_usage, "fetch", fail)
    data = c.get("/api/claude-usage").json()
    assert data == {**data, "limits": [], "error": "claude is not installed or not on PATH"}


def test_cursor_usage(serve, monkeypatch):
    from be import cursor_usage
    from tests.test_cursor_usage import PLAN, USAGE

    c, *_ = serve
    monkeypatch.setattr(cursor_usage, "fetch", lambda: (USAGE, PLAN, {"noUsageBasedAllowed": True}))
    data = c.get("/api/cursor-usage").json()
    assert data["plan"] == "Team"
    assert [(l["label"], l["percent"]) for l in data["limits"]] == [("Included", 12), ("Auto", 11), ("API", 16)]
    assert data["on_demand"]["kind"] == "disabled"
    assert data["error"] is None

    def fail():
        raise click.ClickException(cursor_usage.LOGIN)

    monkeypatch.setattr(cursor_usage, "fetch", fail)
    data = c.get("/api/cursor-usage").json()
    assert data == {**data, "limits": [], "error": cursor_usage.LOGIN}


def test_starred(serve, monkeypatch):
    c, _, _, _ = serve
    asked = []
    monkeypatch.setattr(api.github, "pr_states", lambda names: asked.append(names) or ([PRS[0]], ["acme/web-app#1234"]))
    resp = c.post("/api/prs/starred", json={"prs": ["acme/api#7", "acme/web-app#1234"]})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert asked == [[("acme/api", 7), ("acme/web-app", 1234)]]
    assert [p["url"] for p in data["rows"]] == ["https://github.com/acme/api/pull/7"]
    assert "actions" not in data["rows"][0] and data["merged"] == ["acme/web-app#1234"] and data["error"] is None
    for bad in (["acme/api"], ["api#7"], ["acme/api#x"]):
        assert c.post("/api/prs/starred", json={"prs": bad}).status_code == 400


def test_starred_shows_errors(serve, monkeypatch):
    c, _, _, _ = serve

    def fail(names):
        raise click.ClickException("gh not found")

    monkeypatch.setattr(api.github, "pr_states", fail)
    data = c.post("/api/prs/starred", json={"prs": ["acme/api#7"]}).json()
    assert data == {"rows": None, "merged": [], "error": "gh not found"}


def test_todos(serve, tmp_path, monkeypatch):
    c, _, _, _ = serve
    monkeypatch.setenv("BE_TODO_DIR", str(tmp_path / "todos"))
    monkeypatch.setenv("JIRA_URL", "https://acme.atlassian.net")
    assert c.get("/api/todos").json() == {"rows": [], "error": None, "dir": str(tmp_path / "todos")}
    resp = c.post("/api/todos", json={"title": "Fix it", "jira": "acme-1", "tags": ["work"], "due": "2026-01-01"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["message"] == "added Fix it"
    [row] = c.get("/api/todos").json()["rows"]
    assert row["id"] == "fix-it" and row["url"] == "https://acme.atlassian.net/browse/ACME-1" and row["overdue"]
    resp = c.put("/api/todos/fix-it", json={"notes": "details", "due": ""})
    assert resp.status_code == 200 and resp.json()["todo"]["notes"] == "details"
    assert resp.json()["todo"]["due"] is None
    assert c.post("/api/todos/fix/done").status_code == 200
    assert c.get("/api/todos").json()["rows"] == []
    assert [t["status"] for t in c.get("/api/todos", params={"done": "true"}).json()["rows"]] == ["done"]
    assert c.post("/api/todos/fix-it/reopen").status_code == 200
    assert c.delete("/api/todos/fix-it").json() == {"message": "deleted fix-it"}
    assert (tmp_path / "todos").is_dir() and not list((tmp_path / "todos").glob("*.md"))


def test_todo_errors(serve, tmp_path, monkeypatch):
    c, _, _, _ = serve
    monkeypatch.setenv("BE_TODO_DIR", str(tmp_path / "todos"))
    assert c.post("/api/todos", json={"title": " "}).status_code == 422
    assert c.post("/api/todos", json={"title": "x", "priority": "urgent"}).json()["message"].startswith("priority")
    assert c.post("/api/todos/nope/done").status_code == 422
    assert c.delete("/api/todos/nope").json() == {"message": "no todo nope"}
    # without jira.url a todo's Jira key just has no link
    c.post("/api/todos", json={"title": "x", "jira": "ACME-2"})
    assert c.get("/api/todos").json()["rows"][0]["url"] == ""


def test_calendar(serve, monkeypatch):
    from be import gcal
    from datetime import date

    c, *_ = serve
    asked = []
    monkeypatch.setattr(gcal, "events", lambda day, tz: asked.append((day, tz)) or [{"id": "e1", "title": "Standup"}])
    data = c.get("/api/calendar", params={"day": "2026-10-29", "tz": "America/Denver"}).json()
    assert asked == [(date(2026, 10, 29), "America/Denver")]
    assert data == {**data, "day": "2026-10-29", "events": [{"id": "e1", "title": "Standup"}], "error": None}

    def fail(day, tz):
        raise gcal.CalendarError("not signed in to Google; run `be calendar login`")

    monkeypatch.setattr(gcal, "events", fail)
    data = c.get("/api/calendar", params={"day": "2026-10-29"}).json()
    assert data == {**data, "events": [], "error": "not signed in to Google; run `be calendar login`"}
    assert c.get("/api/calendar", params={"day": "tomorrow"}).status_code == 400


THREAD = {"id": "t1", "subject": "Budget", "messages": []}


def test_mail(serve, monkeypatch):
    from be import gmail

    c, _, _, _ = serve
    asked = []
    monkeypatch.setattr(gmail, "list_threads", lambda q, page: asked.append((q, page)) or ([{"id": "t1"}], "p2"))
    data = c.get("/api/mail", params={"q": "is:unread"}).json()
    assert (data["threads"], data["next_page"], data["error"]) == ([{"id": "t1"}], "p2", None)
    assert asked == [("is:unread", None)]
    assert [a["key"] for a in c.get("/api/mail/actions").json()["actions"]][:2] == ["summarize", "reply"]

    changed = []
    monkeypatch.setattr(gmail, "modify", lambda id, add, remove: changed.append((id, add, remove)))
    assert c.post("/api/mail/t1/modify", json={"remove": ["INBOX"]}).json() == {"message": "updated the thread"}
    assert changed == [("t1", [], ["INBOX"])]
    assert c.post("/api/mail/t1/modify", json={}).status_code == 400

    trashed = []
    monkeypatch.setattr(gmail, "trash", trashed.append)
    assert c.post("/api/mail/t1/trash").json() == {"message": "moved the thread to Trash"}
    assert trashed == ["t1"]
    assert c.post("/api/mail/trash", json={"ids": ["t2", "t3"]}).json() == {"message": "moved 2 threads to Trash"}
    assert sorted(trashed) == ["t1", "t2", "t3"]
    assert c.post("/api/mail/trash", json={"ids": []}).status_code == 400

    def flaky(id):
        if id == "bad":
            raise gmail.MailError("HTTP 404 from Gmail")

    monkeypatch.setattr(gmail, "trash", flaky)
    resp = c.post("/api/mail/trash", json={"ids": ["ok", "bad"]})
    assert resp.status_code == 422 and resp.json()["message"] == "moved 1 of 2 threads to Trash; HTTP 404 from Gmail"


def test_mail_not_signed_in(serve):
    c, _, _, _ = serve
    data = c.get("/api/mail").json()
    assert data["threads"] == [] and "be calendar login" in data["error"]
    resp = c.get("/api/mail/t1")
    assert resp.status_code == 422 and "be calendar login" in resp.json()["message"]


def test_mail_action(serve, monkeypatch, tmp_path):
    from be import gmail

    c, _, _, _ = serve
    opened = []
    monkeypatch.setattr(gmail, "get_thread", lambda id: THREAD)
    monkeypatch.setattr(gmail, "save_thread", lambda thread: tmp_path / "t1.md")
    monkeypatch.setattr(ws, "mail_action", lambda path, prompt, name, model=None, window=None: opened.append((path, prompt, name)))
    assert c.post("/api/mail/t1/action", json={"action": "summarize"}).json() == {"message": "opened claude: summarize"}
    assert c.post("/api/mail/t1/action", json={"prompt": " who is Pat? "}).json() == {"message": "opened claude: claude"}
    assert opened == [
        (tmp_path / "t1.md", gmail.ACTIONS[0]["prompt"], "mail: Budget"),
        (tmp_path / "t1.md", "who is Pat?", "mail: Budget"),
    ]
    assert c.post("/api/mail/t1/action", json={"action": "nope"}).status_code == 400
    assert c.post("/api/mail/t1/action", json={"prompt": " "}).status_code == 400
