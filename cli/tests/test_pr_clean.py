from pathlib import Path

from click.testing import CliRunner

from be.cli import cli


def populate(root: Path) -> Path:
    (root / "repo-a" / "sub").mkdir(parents=True)
    (root / "repo-a" / "sub" / "f.txt").write_text("x")
    (root / "loose.txt").write_text("x")
    outside = root.parent / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    (root / "link").symlink_to(outside)
    return outside


def run(*args, input=None, env=None):
    return CliRunner().invoke(cli, ["pr", "clean", *args], input=input, env=env)


def test_requires_configured_dir():
    result = run("--yes")
    assert result.exit_code == 2
    assert "pr.dir" in result.output


def test_dry_run_deletes_nothing(tmp_path):
    root = tmp_path / "prs"
    populate(root)
    result = run("--parent", str(root), "--dry-run")
    assert result.exit_code == 0
    assert "repo-a/" in result.output
    assert len(list(root.iterdir())) == 3


def test_declining_aborts(tmp_path):
    root = tmp_path / "prs"
    populate(root)
    result = run("--parent", str(root), input="n\n")
    assert result.exit_code == 1
    assert len(list(root.iterdir())) == 3


def test_deletes_contents_not_symlink_targets(tmp_path):
    root = tmp_path / "prs"
    outside = populate(root)
    result = run(input="y\n", env={"PRS_DIR": str(root)})
    assert result.exit_code == 0, result.output
    assert root.is_dir() and list(root.iterdir()) == []
    assert (outside / "keep.txt").exists()


def test_refuses_home(tmp_path):
    result = run("--parent", str(Path.home()), "--yes")
    assert result.exit_code == 1
    assert "refusing" in result.output
