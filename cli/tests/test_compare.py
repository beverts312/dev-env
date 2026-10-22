import pytest
from click.testing import CliRunner

from be.cli import cli


@pytest.fixture
def trees(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    for path in ("a.txt", "sub/b.txt"):
        (source / path).parent.mkdir(parents=True, exist_ok=True)
        (source / path).write_text("s")
    for path in ("a.txt", "sub/b.txt", "sub/c.txt", "new.txt"):
        (target / path).parent.mkdir(parents=True, exist_ok=True)
        (target / path).write_text("t")
    return source, target


def test_dirs_lists_target_only_files(trees):
    source, target = trees
    result = CliRunner().invoke(cli, ["compare", "dirs", str(source), str(target)])
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == ["new.txt", "sub/c.txt"]


def test_dirs_matching(trees):
    source, target = trees
    result = CliRunner().invoke(cli, ["compare", "dirs", "-m", str(source), str(target)])
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == ["a.txt", "sub/b.txt"]


def test_dirs_reads_env_vars(trees, monkeypatch):
    source, target = trees
    monkeypatch.setenv("SOURCE", str(source))
    monkeypatch.setenv("TARGET", str(target))
    result = CliRunner().invoke(cli, ["compare", "dirs"])
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == ["new.txt", "sub/c.txt"]


def test_dirs_rejects_missing_dir(tmp_path):
    result = CliRunner().invoke(cli, ["compare", "dirs", str(tmp_path), str(tmp_path / "nope")])
    assert result.exit_code != 0
    assert "does not exist" in result.output
