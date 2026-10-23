import subprocess
import tomllib

import click
import pytest
from click.testing import CliRunner

from be import config
from be.cli import cli


class Done:
    returncode = 0


def run(*args, env=None):
    return CliRunner().invoke(cli, list(args), env=env)


def capture_clone(monkeypatch):
    calls = []
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **kw: calls.append(cmd) or Done()
    )
    return calls


def test_file_value_used(isolated_config, monkeypatch):
    assert run("config", "set", "work_org", "fromfile").exit_code == 0
    calls = capture_clone(monkeypatch)
    assert run("git", "clone", "repo").exit_code == 0
    assert calls[0][-1] == "git@github.com:fromfile/repo.git"


def test_precedence_flag_env_file(isolated_config, monkeypatch):
    run("config", "set", "work_org", "fromfile")
    calls = capture_clone(monkeypatch)
    run("git", "clone", "repo", env={"WORK_ORG": "fromenv"})
    run("git", "clone", "repo", "--org", "fromflag", env={"WORK_ORG": "fromenv"})
    assert [c[-1] for c in calls] == [
        "git@github.com:fromenv/repo.git",
        "git@github.com:fromflag/repo.git",
    ]


def test_set_get_unset(isolated_config):
    assert run("config", "set", "git.email", "me@example.com").exit_code == 0
    assert tomllib.loads(isolated_config.read_text()) == {
        "git": {"email": "me@example.com"}
    }
    got = run("config", "get", "git.email", "--source")
    assert got.output.strip() == "me@example.com\tfile"
    assert run("config", "unset", "git.email").exit_code == 0
    assert tomllib.loads(isolated_config.read_text()) == {}
    assert run("config", "get", "git.email").exit_code == 1


def test_set_unknown_key():
    result = run("config", "set", "nope", "x")
    assert result.exit_code == 2
    assert "valid keys" in result.output


def test_set_warns_when_env_overrides():
    out = run("config", "set", "work_org", "x", env={"WORK_ORG": "y"})
    assert out.exit_code == 0
    assert "WORK_ORG is set" in out.output


def test_list_sources():
    run("config", "set", "git.name", "Me")
    out = run("config", "list", env={"WORK_ORG": "acme"}).output
    lines = {line.split()[0]: line.split()[-1] for line in out.splitlines()}
    assert lines["work_org"] == "env:WORK_ORG"
    assert lines["git.name"] == "file"
    assert lines["claude.model"] == "default"
    assert lines["git.email"] == "unset"


def test_init(isolated_config):
    result = run("config", "init", env={"WORK_ORG": "acme"})
    assert result.exit_code == 0, result.output
    data = tomllib.loads(isolated_config.read_text())
    assert data["work_org"] == "acme"
    assert "model" not in data.get("claude", {})
    assert '# model = "claude-opus-5-5"' in isolated_config.read_text()
    assert "email" not in data.get("git", {})
    again = run("config", "init")
    assert again.exit_code == 1
    assert "--force" in again.output
    assert run("config", "init", "--force").exit_code == 0


def test_invalid_file_is_clean_error(isolated_config):
    isolated_config.parent.mkdir(parents=True)
    isolated_config.write_text("work_org = \n")
    result = run("config", "list")
    assert result.exit_code == 1
    assert "invalid config file" in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_help_mentions_config_key():
    assert "[config: work_org]" in run("git", "clone", "--help").output


def test_map_entries(isolated_config):
    assert run("config", "set", "jira.projects.ACME", "Acme").exit_code == 0
    assert run("config", "set", "jira.projects.OPS", "Operations").exit_code == 0
    assert tomllib.loads(isolated_config.read_text()) == {
        "jira": {"projects": {"ACME": "Acme", "OPS": "Operations"}}
    }
    assert run("config", "get", "jira.projects.ACME").output == "Acme\n"
    assert (
        run("config", "get", "jira.projects").output
        == "ACME\tAcme\nOPS\tOperations\n"
    )
    out = run("config", "list").output
    assert "jira.projects.OPS" in out
    assert run("config", "unset", "jira.projects.ACME").exit_code == 0
    assert run("config", "unset", "jira.projects.OPS").exit_code == 0
    assert tomllib.loads(isolated_config.read_text()) == {}
    assert run("config", "get", "jira.projects").exit_code == 1


def test_map_rejects_bare_set_and_unknown_parent():
    assert run("config", "set", "jira.projects", "x").exit_code == 2
    assert run("config", "set", "jira.url.x", "y").exit_code == 2


def test_map_env_json(isolated_config):
    env = {"JIRA_PROJECTS": '{"ACME": "Acme"}'}
    got = run("config", "get", "jira.projects.ACME", "--source", env=env)
    assert got.output == "Acme\tenv:JIRA_PROJECTS\n"
    assert run("config", "init", env=env).exit_code == 0
    assert tomllib.loads(isolated_config.read_text())["jira"]["projects"] == {
        "ACME": "Acme"
    }
    bad = run("config", "get", "jira.projects", env={"JIRA_PROJECTS": "nope"})
    assert bad.exit_code == 1
    assert "invalid JSON" in bad.output


def test_list_masks_secrets_and_init_is_private(isolated_config):
    run("config", "set", "jira.token", "hunter2")
    assert "hunter2" not in run("config", "list").output
    assert run("config", "get", "jira.token").output == "hunter2\n"
    isolated_config.unlink()
    assert run("config", "init").exit_code == 0
    assert isolated_config.stat().st_mode & 0o777 == 0o600


def tty(monkeypatch, on: bool) -> None:
    monkeypatch.setattr(config, "in_terminal", lambda: on)


def test_interactive_flag_wins(monkeypatch):
    monkeypatch.setenv("BE_INTERACTIVE", "true")
    tty(monkeypatch, True)
    assert config.interactive(False) is False
    assert config.interactive(True) is True


def test_interactive_setting_needs_a_terminal(monkeypatch):
    monkeypatch.setenv("BE_INTERACTIVE", "yes")
    tty(monkeypatch, True)
    assert config.interactive(None) is True
    tty(monkeypatch, False)
    assert config.interactive(None) is False


def test_interactive_defaults_off(monkeypatch):
    tty(monkeypatch, True)
    assert config.interactive(None) is False


def test_interactive_rejects_other_values(monkeypatch):
    monkeypatch.setenv("BE_INTERACTIVE", "sometimes")
    with pytest.raises(click.ClickException, match="must be true or false"):
        config.interactive(None)
