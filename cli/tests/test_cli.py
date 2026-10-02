import subprocess

from click.testing import CliRunner

from be.cli import cli


def test_help_shows_envvars():
    runner = CliRunner()
    assert "GIT_EMAIL" in runner.invoke(cli, ["git", "author", "--help"]).output
    assert "WORK_ORG" in runner.invoke(cli, ["git", "clone", "--help"]).output
    assert "PRS_DIR" in runner.invoke(cli, ["pr", "review", "--help"]).output
    assert "BE_CLAUDE_MODEL" in runner.invoke(cli, ["ws", "setup", "--help"]).output


def test_author_requires_env():
    result = CliRunner().invoke(cli, ["git", "author"], env={"GIT_EMAIL": None, "GIT_NAME": None})
    assert result.exit_code == 2
    assert "--email" in result.output


def test_author_sets_config(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    result = CliRunner().invoke(
        cli, ["git", "author"], env={"GIT_EMAIL": "me@example.com", "GIT_NAME": "Me"}
    )
    assert result.exit_code == 0, result.output
    assert calls == [
        ["git", "config", "--global", "user.email", "me@example.com"],
        ["git", "config", "--global", "user.name", "Me"],
    ]


def test_clone_uses_org(monkeypatch):
    calls = []

    class Done:
        returncode = 0

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd) or Done())
    result = CliRunner().invoke(cli, ["git", "clone", "repo", "dest"], env={"WORK_ORG": "acme"})
    assert result.exit_code == 0, result.output
    assert calls == [
        ["git", "clone", "--recurse-submodules", "git@github.com:acme/repo.git", "dest"]
    ]


def test_clone_without_org_errors():
    result = CliRunner().invoke(cli, ["git", "clone", "repo"], env={"WORK_ORG": None})
    assert result.exit_code == 2
    assert "WORK_ORG" in result.output
