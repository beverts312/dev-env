"""`be backup`: encrypted directory backups to GCS or S3 (replaces backup_util.py)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import click

from be import backup as lib

CONFIG_HELP = f"Backup config YAML (default: ./{lib.DEFAULT_CONFIG})."


@click.group()
def backup() -> None:
    """Encrypt a directory and upload it to GCS or S3, or restore it."""


def prompt_ignore_patterns() -> list[str]:
    click.echo("\nIgnore globs (relative to source_dir).\nDefault patterns:")
    for pattern in lib.DEFAULT_IGNORE:
        click.echo(f"  - {pattern}")
    ignore = list(lib.DEFAULT_IGNORE) if click.confirm("Use these defaults?", default=True) else []

    click.echo("Enter additional ignore globs (empty line to finish):")
    while True:
        raw = click.prompt("  glob", default="", show_default=False).strip()
        if not raw:
            break
        if raw not in ignore:
            ignore.append(raw)
    if lib.DEFAULT_CONFIG not in ignore:
        ignore.append(lib.DEFAULT_CONFIG)
    return ignore


@backup.command()
@click.option("--config", "config_path", default=lib.DEFAULT_CONFIG, help="Config path offered by the wizard.")
def setup(config_path: str) -> None:
    """Write a backup config interactively, optionally with a key."""
    click.echo("Encrypted backup setup\n")

    path = Path(click.prompt("Config file path", default=config_path)).expanduser().resolve()
    if path.exists() and not click.confirm(f"{path} already exists. Overwrite?", default=False):
        raise click.ClickException("setup cancelled")

    key_path_raw = click.prompt(
        "Path for local encryption key", default=str(Path.home() / ".keys" / "backup.key")
    )
    source_dir = click.prompt("Directory to back up", default=".")

    def check_uri(value: str) -> str:
        lib.parse_storage_uri(value)
        return value

    storage_uri = click.prompt(
        "Storage URI (gs://bucket/object or s3://bucket/object)", value_proc=check_uri
    )
    ignore = prompt_ignore_patterns()

    lib.write_config(
        path,
        {
            "key_path": key_path_raw,
            "source_dir": source_dir,
            "storage_uri": storage_uri,
            "ignore": ignore,
        },
    )
    click.echo(f"\nWrote config to {path}")

    key_path = Path(key_path_raw).expanduser().resolve()
    if not click.confirm("Generate encryption key now?", default=True):
        click.echo(f"Skipped key generation. Create one later with:\n  be backup gen-key --config {path}")
    elif not key_path.exists():
        lib.gen_key(key_path, force=False)
    elif click.confirm(f"Key already exists at {key_path}. Overwrite?", default=False):
        lib.gen_key(key_path, force=True)
    else:
        click.echo(f"Keeping existing key at {key_path}")
    click.echo("Setup complete.")


@backup.command("gen-key")
@click.option("--config", "config_path", default=None, help=f"{CONFIG_HELP} Read only if present.")
@click.option("--key-path", default=None, help="Override key_path from the config.")
@click.option("--force", is_flag=True, help="Overwrite an existing key file.")
def gen_key(config_path: str | None, key_path: str | None, force: bool) -> None:
    """Generate a local Fernet key file."""
    path = Path(config_path or lib.DEFAULT_CONFIG)
    data = lib.load_config(path) if path.is_file() else {}
    lib.gen_key(lib.resolve_key_path(data, key_path), force=force)


@backup.command()
@click.option("--config", "config_path", default=lib.DEFAULT_CONFIG, help=CONFIG_HELP)
@click.option(
    "--dry-run",
    is_flag=True,
    help="List the files that would be archived without encrypting or uploading.",
)
def upload(config_path: str, dry_run: bool) -> None:
    """Archive, encrypt, and upload source_dir."""
    path = Path(config_path).expanduser().resolve()
    data = lib.load_config(path)
    source_dir = lib.resolve_source_dir(data)
    storage_uri = lib.resolve_storage_uri(data)
    ignore = data.get("ignore") or []
    if not isinstance(ignore, list):
        raise click.ClickException("ignore must be a list of glob patterns")

    key_path = None if dry_run else lib.resolve_key_path(data)
    extra_ignore = [path]
    if key_path is not None:
        extra_ignore.append(key_path)
    elif data.get("key_path"):
        extra_ignore.append(Path(data["key_path"]).expanduser().resolve())

    files = lib.collect_files(source_dir, ignore, extra_ignore)

    if dry_run:
        for rel in files:
            click.echo(rel.as_posix())
        click.echo(f"\n{len(files)} file(s) would be archived from {source_dir}")
        click.echo(f"Would upload encrypted archive to {storage_uri}")
        return

    if not files:
        raise click.ClickException(f"no files to upload under {source_dir}")

    fernet = lib.load_fernet(key_path)
    click.echo(f"Archiving {len(files)} file(s) from {source_dir}")
    with tempfile.TemporaryDirectory(prefix="encrypted-backup-") as tmp:
        archive_path = Path(tmp) / "backup.tar.gz"
        encrypted_path = Path(tmp) / "backup.tar.gz.enc"
        lib.create_archive(source_dir, files, archive_path)
        click.echo(f"Encrypting archive ({archive_path.stat().st_size} bytes)")
        lib.encrypt_file(fernet, archive_path, encrypted_path)
        lib.upload_object(storage_uri, encrypted_path)


@backup.command()
@click.option("--config", "config_path", default=lib.DEFAULT_CONFIG, help=CONFIG_HELP)
@click.option("--dest", default=".", help="Extraction directory (default: current directory).")
def download(config_path: str, dest: str) -> None:
    """Download, decrypt, and extract the backup into DEST."""
    data = lib.load_config(Path(config_path).expanduser().resolve())
    storage_uri = lib.resolve_storage_uri(data)
    fernet = lib.load_fernet(lib.resolve_key_path(data))
    dest_dir = Path(dest).expanduser().resolve()

    with tempfile.TemporaryDirectory(prefix="encrypted-backup-") as tmp:
        encrypted_path = Path(tmp) / "backup.tar.gz.enc"
        archive_path = Path(tmp) / "backup.tar.gz"
        lib.download_object(storage_uri, encrypted_path)
        click.echo("Decrypting archive")
        lib.decrypt_file(fernet, encrypted_path, archive_path)
        click.echo(f"Extracting to {dest_dir}")
        lib.extract_archive(archive_path, dest_dir)
    click.echo("Done")
