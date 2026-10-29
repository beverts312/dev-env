import shutil
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from be import backup as lib
from be.cli import cli


@pytest.mark.parametrize(
    ("path", "is_dir", "expected"),
    [
        (".git", True, True),
        (".git/HEAD", False, True),
        ("a/b/node_modules", True, True),
        ("pkg/__pycache__/x.pyc", False, True),
        ("encrypted_backup.yml", False, True),
        ("src/main.py", False, False),
        ("sub/.git", True, False),
    ],
)
def test_is_ignored(path, is_dir, expected):
    assert lib.is_ignored(path, lib.DEFAULT_IGNORE, is_dir=is_dir) is expected


@pytest.mark.parametrize("uri", ["http://b/o", "gs://bucket", "s3:///obj"])
def test_parse_storage_uri_rejects_bad_uris(uri):
    with pytest.raises(Exception):
        lib.parse_storage_uri(uri)


def write_setup(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "src"
    (source / ".git").mkdir(parents=True)
    (source / ".git" / "HEAD").write_text("ref")
    (source / "notes").mkdir()
    (source / "notes" / "a.md").write_text("hello")
    key = tmp_path / "keys" / "backup.key"
    config_path = source / lib.DEFAULT_CONFIG
    lib.write_config(
        config_path,
        {
            "key_path": str(key),
            "source_dir": str(source),
            "storage_uri": "gs://bucket/backup.enc",
            "ignore": lib.DEFAULT_IGNORE,
        },
    )
    return config_path, key


def test_gen_key_reads_key_path_from_config(tmp_path):
    config_path, key = write_setup(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["backup", "gen-key", "--config", str(config_path)])
    assert result.exit_code == 0, result.output
    assert key.stat().st_mode & 0o777 == 0o600

    again = runner.invoke(cli, ["backup", "gen-key", "--config", str(config_path)])
    assert again.exit_code != 0
    assert "already exists" in again.output


def test_upload_dry_run_lists_files(tmp_path):
    config_path, _ = write_setup(tmp_path)
    result = CliRunner().invoke(cli, ["backup", "upload", "--config", str(config_path), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "notes/a.md" in result.output
    assert ".git" not in result.output
    assert "1 file(s) would be archived" in result.output


def test_upload_then_download_round_trips(tmp_path, monkeypatch):
    config_path, key = write_setup(tmp_path)
    bucket = tmp_path / "bucket"
    bucket.mkdir()
    monkeypatch.setattr(lib, "upload_object", lambda uri, p: shutil.copy(p, bucket / "obj"))
    monkeypatch.setattr(lib, "download_object", lambda uri, p: shutil.copy(bucket / "obj", p))
    runner = CliRunner()
    assert runner.invoke(cli, ["backup", "gen-key", "--config", str(config_path)]).exit_code == 0

    up = runner.invoke(cli, ["backup", "upload", "--config", str(config_path)])
    assert up.exit_code == 0, up.output
    assert b"hello" not in (bucket / "obj").read_bytes()

    dest = tmp_path / "restore"
    down = runner.invoke(cli, ["backup", "download", "--config", str(config_path), "--dest", str(dest)])
    assert down.exit_code == 0, down.output
    assert (dest / "notes" / "a.md").read_text() == "hello"
    assert not (dest / ".git").exists()
    assert not (dest / lib.DEFAULT_CONFIG).exists()


def test_setup_writes_config(tmp_path):
    config_path = tmp_path / "backup.yml"
    key = tmp_path / "k.key"
    answers = [
        str(config_path),
        str(key),
        "src",
        "ftp://nope",
        "s3://bucket/obj",
        "y",
        "*.log",
        "",
        "y",
    ]
    result = CliRunner().invoke(cli, ["backup", "setup"], input="\n".join(answers) + "\n")
    assert result.exit_code == 0, result.output
    assert "unsupported storage_uri scheme" in result.output
    data = yaml.safe_load(config_path.read_text())
    assert data["storage_uri"] == "s3://bucket/obj"
    assert data["ignore"] == lib.DEFAULT_IGNORE + ["*.log"]
    assert key.is_file()
