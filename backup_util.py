#!/usr/bin/env python3
"""
Encrypt a directory as a tar.gz archive and upload it to GCS or S3,
or download and decrypt that archive.

Usage:
    pip install cryptography pyyaml google-cloud-storage boto3

    python backup_util.py setup [--config PATH]
    python backup_util.py gen-key [--config PATH] [--key-path PATH] [--force]
    python backup_util.py upload [--config PATH] [--dry-run]
    python backup_util.py download [--config PATH] [--dest DIR]

Config defaults to ./encrypted_backup.yml in the current working directory.
storage_uri must be gs://bucket/object or s3://bucket/object.
Auth uses ADC for GCS and the standard AWS credential chain for S3.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urlparse

import yaml
from cryptography.fernet import Fernet, InvalidToken


DEFAULT_CONFIG = "encrypted_backup.yml"
DEFAULT_IGNORE = [
    ".git/**",
    "**/node_modules/**",
    ".venv/**",
    "**/__pycache__/**",
    DEFAULT_CONFIG,
]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_config(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"Config not found: {path}")
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Config must be a mapping: {path}")
    return data


def resolve_key_path(config: dict, override: str | None = None) -> Path:
    raw = override or config.get("key_path")
    if not raw:
        raise SystemExit("key_path is required (config or --key-path)")
    return Path(raw).expanduser().resolve()


def resolve_source_dir(config: dict) -> Path:
    raw = config.get("source_dir", ".")
    return Path(raw).expanduser().resolve()


def resolve_storage_uri(config: dict) -> str:
    uri = config.get("storage_uri")
    if not uri or not isinstance(uri, str):
        raise SystemExit("storage_uri is required in config (gs://... or s3://...)")
    return uri.strip()


# ---------------------------------------------------------------------------
# Ignore / file walk
# ---------------------------------------------------------------------------


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a glob with ** support into a regex."""
    pattern = pattern.replace("\\", "/").rstrip("/")
    parts: list[str] = ["^"]
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            parts.append(".*")
            i += 2
        elif pattern[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(pattern[i]))
            i += 1
    parts.append("$")
    return re.compile("".join(parts))


def is_ignored(rel_path: str, patterns: Sequence[str], *, is_dir: bool = False) -> bool:
    path = rel_path.replace("\\", "/").rstrip("/")
    if not path:
        return False
    for pattern in patterns:
        if not pattern:
            continue
        pat = pattern.replace("\\", "/").rstrip("/")
        regex = _glob_to_regex(pat)
        if regex.match(path):
            return True
        # Patterns like ".git/**" should also skip the ".git" directory itself.
        if pat.endswith("/**"):
            prefix_regex = _glob_to_regex(pat[: -len("/**")])
            if prefix_regex.match(path):
                return True
        if is_dir:
            # Directory "foo" is ignored if pattern would match children under it.
            child_regex = _glob_to_regex(pat if pat.endswith("/**") else pat + "/**")
            if child_regex.match(path + "/x"):
                return True
    return False


def collect_files(source_dir: Path, ignore: Sequence[str], extra_ignore: Iterable[Path]) -> list[Path]:
    """Return file paths relative to source_dir that should be archived."""
    patterns = list(ignore)
    for extra in extra_ignore:
        try:
            rel = extra.resolve().relative_to(source_dir)
            patterns.append(rel.as_posix())
        except ValueError:
            pass

    selected: list[Path] = []
    for root, dirs, files in os.walk(source_dir, topdown=True, followlinks=False):
        root_path = Path(root)
        rel_root = root_path.relative_to(source_dir)
        rel_root_str = "" if rel_root == Path(".") else rel_root.as_posix()

        keep_dirs: list[str] = []
        for name in dirs:
            rel = f"{rel_root_str}/{name}" if rel_root_str else name
            if is_ignored(rel, patterns, is_dir=True):
                continue
            keep_dirs.append(name)
        dirs[:] = sorted(keep_dirs)

        for name in files:
            rel = f"{rel_root_str}/{name}" if rel_root_str else name
            if is_ignored(rel, patterns):
                continue
            selected.append(Path(rel))

    selected.sort(key=lambda p: p.as_posix())
    return selected


# ---------------------------------------------------------------------------
# Crypto / archive
# ---------------------------------------------------------------------------


def load_fernet(key_path: Path) -> Fernet:
    if not key_path.is_file():
        raise SystemExit(f"Key file not found: {key_path}")
    key = key_path.read_bytes().strip()
    try:
        return Fernet(key)
    except Exception as exc:
        raise SystemExit(f"Invalid Fernet key at {key_path}: {exc}") from exc


def gen_key(key_path: Path, force: bool) -> None:
    if key_path.exists() and not force:
        raise SystemExit(f"Key already exists: {key_path} (use --force to overwrite)")
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    key_path.chmod(0o600)
    print(f"Wrote Fernet key to {key_path}")


def create_archive(source_dir: Path, files: Sequence[Path], archive_path: Path) -> None:
    with tarfile.open(archive_path, "w:gz") as tar:
        for rel in files:
            full = source_dir / rel
            tar.add(full, arcname=rel.as_posix(), recursive=False)


def encrypt_file(fernet: Fernet, src: Path, dest: Path) -> None:
    dest.write_bytes(fernet.encrypt(src.read_bytes()))


def decrypt_file(fernet: Fernet, src: Path, dest: Path) -> None:
    try:
        dest.write_bytes(fernet.decrypt(src.read_bytes()))
    except InvalidToken as exc:
        raise SystemExit("Decryption failed: invalid key or corrupt ciphertext") from exc


def extract_archive(archive_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tar:
        # filter="data" is Python 3.12+; fall back for older runtimes.
        try:
            tar.extractall(dest_dir, filter="data")
        except TypeError:
            tar.extractall(dest_dir)


# ---------------------------------------------------------------------------
# Cloud storage
# ---------------------------------------------------------------------------


def parse_storage_uri(uri: str) -> tuple[str, str, str]:
    parsed = urlparse(uri)
    scheme = parsed.scheme.lower()
    if scheme not in {"gs", "s3"}:
        raise SystemExit(f"Unsupported storage_uri scheme (use gs:// or s3://): {uri}")
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        raise SystemExit(f"storage_uri must be scheme://bucket/object-path: {uri}")
    return scheme, bucket, key


def upload_object(uri: str, local_path: Path) -> None:
    scheme, bucket, key = parse_storage_uri(uri)
    if scheme == "gs":
        from google.cloud import storage

        client = storage.Client()
        blob = client.bucket(bucket).blob(key)
        blob.upload_from_filename(str(local_path))
    else:
        import boto3

        boto3.client("s3").upload_file(str(local_path), bucket, key)
    print(f"Uploaded {local_path.name} -> {uri}")


def download_object(uri: str, local_path: Path) -> None:
    scheme, bucket, key = parse_storage_uri(uri)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    if scheme == "gs":
        from google.cloud import storage

        client = storage.Client()
        blob = client.bucket(bucket).blob(key)
        blob.download_to_filename(str(local_path))
    else:
        import boto3

        boto3.client("s3").download_file(bucket, key, str(local_path))
    print(f"Downloaded {uri} -> {local_path}")


# ---------------------------------------------------------------------------
# Interactive helpers
# ---------------------------------------------------------------------------


def prompt(message: str, default: str | None = None) -> str:
    if default is not None:
        raw = input(f"{message} [{default}]: ").strip()
        return raw if raw else default
    while True:
        raw = input(f"{message}: ").strip()
        if raw:
            return raw
        print("  A value is required.")


def prompt_yes_no(message: str, *, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = input(f"{message} [{hint}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes"}


def prompt_ignore_patterns() -> list[str]:
    print("\nIgnore globs (relative to source_dir).")
    print("Default patterns:")
    for pattern in DEFAULT_IGNORE:
        print(f"  - {pattern}")
    if prompt_yes_no("Use these defaults?", default=True):
        ignore = list(DEFAULT_IGNORE)
    else:
        ignore = []

    print("Enter additional ignore globs (empty line to finish):")
    while True:
        raw = input("  glob> ").strip()
        if not raw:
            break
        if raw not in ignore:
            ignore.append(raw)
    if DEFAULT_CONFIG not in ignore:
        ignore.append(DEFAULT_CONFIG)
    return ignore


def write_config(path: Path, config: dict) -> None:
    path.write_text(
        yaml.safe_dump(config, default_flow_style=False, sort_keys=False),
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_setup(args: argparse.Namespace) -> None:
    print("Encrypted backup setup\n")

    config_path = Path(prompt("Config file path", args.config or DEFAULT_CONFIG)).expanduser()
    if not config_path.is_absolute():
        config_path = (Path.cwd() / config_path).resolve()
    else:
        config_path = config_path.resolve()

    if config_path.exists():
        if not prompt_yes_no(f"{config_path} already exists. Overwrite?", default=False):
            raise SystemExit("Setup cancelled.")

    key_path_raw = prompt("Path for local encryption key", str(Path.home() / ".keys" / "backup.key"))
    source_dir = prompt("Directory to back up", ".")

    while True:
        storage_uri = prompt("Storage URI (gs://bucket/object or s3://bucket/object)")
        try:
            parse_storage_uri(storage_uri)
            break
        except SystemExit as exc:
            print(f"  {exc}")

    ignore = prompt_ignore_patterns()

    config = {
        "key_path": key_path_raw,
        "source_dir": source_dir,
        "storage_uri": storage_uri,
        "ignore": ignore,
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    write_config(config_path, config)
    print(f"\nWrote config to {config_path}")

    key_path = Path(key_path_raw).expanduser().resolve()
    if prompt_yes_no("Generate encryption key now?", default=True):
        if key_path.exists():
            if not prompt_yes_no(f"Key already exists at {key_path}. Overwrite?", default=False):
                print(f"Keeping existing key at {key_path}")
                print("Setup complete.")
                return
            gen_key(key_path, force=True)
        else:
            gen_key(key_path, force=False)
    else:
        print(f"Skipped key generation. Create one later with:")
        print(f"  python {Path(__file__).name} gen-key --config {config_path}")

    print("Setup complete.")


def cmd_gen_key(args: argparse.Namespace) -> None:
    config: dict = {}
    if args.config is not None or Path(DEFAULT_CONFIG).is_file():
        config_path = Path(args.config) if args.config else Path(DEFAULT_CONFIG)
        if config_path.is_file():
            config = load_config(config_path)
    key_path = resolve_key_path(config, args.key_path)
    gen_key(key_path, force=args.force)


def cmd_upload(args: argparse.Namespace) -> None:
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    source_dir = resolve_source_dir(config)
    storage_uri = resolve_storage_uri(config)
    ignore = config.get("ignore") or []
    if not isinstance(ignore, list):
        raise SystemExit("ignore must be a list of glob patterns")

    key_path = None
    if not args.dry_run:
        key_path = resolve_key_path(config)

    extra_ignore = [config_path]
    if key_path is not None:
        extra_ignore.append(key_path)
    elif config.get("key_path"):
        extra_ignore.append(Path(config["key_path"]).expanduser().resolve())

    files = collect_files(source_dir, ignore, extra_ignore)

    if args.dry_run:
        for rel in files:
            print(rel.as_posix())
        print(f"\n{len(files)} file(s) would be archived from {source_dir}")
        print(f"Would upload encrypted archive to {storage_uri}")
        return

    if not files:
        raise SystemExit(f"No files to upload under {source_dir}")

    fernet = load_fernet(key_path)
    print(f"Archiving {len(files)} file(s) from {source_dir}")

    with tempfile.TemporaryDirectory(prefix="encrypted-backup-") as tmp:
        tmp_dir = Path(tmp)
        archive_path = tmp_dir / "backup.tar.gz"
        encrypted_path = tmp_dir / "backup.tar.gz.enc"
        create_archive(source_dir, files, archive_path)
        print(f"Encrypting archive ({archive_path.stat().st_size} bytes)")
        encrypt_file(fernet, archive_path, encrypted_path)
        upload_object(storage_uri, encrypted_path)


def cmd_download(args: argparse.Namespace) -> None:
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    storage_uri = resolve_storage_uri(config)
    key_path = resolve_key_path(config)
    dest_dir = Path(args.dest).expanduser().resolve()
    fernet = load_fernet(key_path)

    with tempfile.TemporaryDirectory(prefix="encrypted-backup-") as tmp:
        tmp_dir = Path(tmp)
        encrypted_path = tmp_dir / "backup.tar.gz.enc"
        archive_path = tmp_dir / "backup.tar.gz"
        download_object(storage_uri, encrypted_path)
        print("Decrypting archive")
        decrypt_file(fernet, encrypted_path, archive_path)
        print(f"Extracting to {dest_dir}")
        extract_archive(archive_path, dest_dir)
    print("Done")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Encrypt a directory archive and upload to GCS or S3 (and reverse).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="Interactively create config YAML and optionally generate a key")
    setup.add_argument(
        "--config",
        default=None,
        help=f"Default config path offered by the wizard (default: ./{DEFAULT_CONFIG})",
    )
    setup.set_defaults(func=cmd_setup)

    gen = sub.add_parser("gen-key", help="Generate a local Fernet key file")
    gen.add_argument("--config", default=None, help=f"Config path (default: ./{DEFAULT_CONFIG} if present)")
    gen.add_argument("--key-path", default=None, help="Override key_path from config")
    gen.add_argument("--force", action="store_true", help="Overwrite an existing key file")
    gen.set_defaults(func=cmd_gen_key)

    up = sub.add_parser("upload", help="Archive, encrypt, and upload")
    up.add_argument("--config", default=DEFAULT_CONFIG, help=f"Config path (default: ./{DEFAULT_CONFIG})")
    up.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be archived/uploaded without encrypting or uploading",
    )
    up.set_defaults(func=cmd_upload)

    down = sub.add_parser("download", help="Download, decrypt, and extract")
    down.add_argument("--config", default=DEFAULT_CONFIG, help=f"Config path (default: ./{DEFAULT_CONFIG})")
    down.add_argument("--dest", default=".", help="Extraction directory (default: cwd)")
    down.set_defaults(func=cmd_download)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
