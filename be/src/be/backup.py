"""Encrypted directory backups to GCS or S3 (replaces backup_util.py).

A directory is archived as tar.gz, encrypted with a local Fernet key, and
uploaded to storage_uri (gs://bucket/object or s3://bucket/object). Auth uses
Application Default Credentials for GCS and the standard AWS credential chain for S3.
"""

from __future__ import annotations

import os
import re
import tarfile
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urlparse

import click
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


# Config


def load_config(path: Path) -> dict:
    if not path.is_file():
        raise click.ClickException(f"config not found: {path}")
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise click.ClickException(f"config must be a mapping: {path}")
    return data


def write_config(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))


def resolve_key_path(data: dict, override: str | None = None) -> Path:
    raw = override or data.get("key_path")
    if not raw:
        raise click.ClickException("key_path is required (config or --key-path)")
    return Path(raw).expanduser().resolve()


def resolve_source_dir(data: dict) -> Path:
    return Path(data.get("source_dir", ".")).expanduser().resolve()


def resolve_storage_uri(data: dict) -> str:
    uri = data.get("storage_uri")
    if not uri or not isinstance(uri, str):
        raise click.ClickException(
            "storage_uri is required in config (gs://... or s3://...)"
        )
    return uri.strip()


# Ignore / file walk


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
        if _glob_to_regex(pat).match(path):
            return True
        # Patterns like ".git/**" should also skip the ".git" directory itself.
        if pat.endswith("/**") and _glob_to_regex(pat[: -len("/**")]).match(path):
            return True
        if is_dir:
            # Directory "foo" is ignored if the pattern would match children under it.
            child_regex = _glob_to_regex(pat if pat.endswith("/**") else pat + "/**")
            if child_regex.match(path + "/x"):
                return True
    return False


def collect_files(
    source_dir: Path, ignore: Sequence[str], extra_ignore: Iterable[Path]
) -> list[Path]:
    """Return file paths relative to source_dir that should be archived."""
    patterns = list(ignore)
    for extra in extra_ignore:
        try:
            patterns.append(extra.resolve().relative_to(source_dir).as_posix())
        except ValueError:
            pass

    selected: list[Path] = []
    for root, dirs, files in os.walk(source_dir, topdown=True, followlinks=False):
        rel_root = Path(root).relative_to(source_dir)
        rel_root_str = "" if rel_root == Path(".") else rel_root.as_posix()

        keep_dirs: list[str] = []
        for name in dirs:
            rel = f"{rel_root_str}/{name}" if rel_root_str else name
            if not is_ignored(rel, patterns, is_dir=True):
                keep_dirs.append(name)
        dirs[:] = sorted(keep_dirs)

        for name in files:
            rel = f"{rel_root_str}/{name}" if rel_root_str else name
            if not is_ignored(rel, patterns):
                selected.append(Path(rel))

    selected.sort(key=lambda p: p.as_posix())
    return selected


# Crypto / archive


def load_fernet(key_path: Path) -> Fernet:
    if not key_path.is_file():
        raise click.ClickException(f"key file not found: {key_path}")
    try:
        return Fernet(key_path.read_bytes().strip())
    except Exception as e:
        raise click.ClickException(f"invalid Fernet key at {key_path}: {e}") from None


def gen_key(key_path: Path, force: bool) -> None:
    if key_path.exists() and not force:
        raise click.ClickException(
            f"key already exists: {key_path} (use --force to overwrite)"
        )
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(Fernet.generate_key())
    key_path.chmod(0o600)
    click.echo(f"Wrote Fernet key to {key_path}")


def create_archive(source_dir: Path, files: Sequence[Path], archive_path: Path) -> None:
    with tarfile.open(archive_path, "w:gz") as tar:
        for rel in files:
            tar.add(source_dir / rel, arcname=rel.as_posix(), recursive=False)


def encrypt_file(fernet: Fernet, src: Path, dest: Path) -> None:
    dest.write_bytes(fernet.encrypt(src.read_bytes()))


def decrypt_file(fernet: Fernet, src: Path, dest: Path) -> None:
    try:
        dest.write_bytes(fernet.decrypt(src.read_bytes()))
    except InvalidToken:
        raise click.ClickException(
            "decryption failed: invalid key or corrupt ciphertext"
        ) from None


def extract_archive(archive_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tar:
        # filter="data" arrived in 3.11.4; fall back for older 3.11 runtimes.
        try:
            tar.extractall(dest_dir, filter="data")
        except TypeError:
            tar.extractall(dest_dir)


# Cloud storage


def parse_storage_uri(uri: str) -> tuple[str, str, str]:
    parsed = urlparse(uri)
    scheme = parsed.scheme.lower()
    if scheme not in {"gs", "s3"}:
        raise click.BadParameter(
            f"unsupported storage_uri scheme (use gs:// or s3://): {uri}"
        )
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        raise click.BadParameter(
            f"storage_uri must be scheme://bucket/object-path: {uri}"
        )
    return scheme, bucket, key


def _gcs_blob(bucket: str, key: str):
    try:
        from google.cloud import storage
    except ImportError:
        raise click.ClickException(
            "google-cloud-storage is not installed; install be with the backup extra: "
            "uv tool install --editable './be[backup]'"
        ) from None
    return storage.Client().bucket(bucket).blob(key)


def _s3_client():
    try:
        import boto3
    except ImportError:
        raise click.ClickException(
            "boto3 is not installed; install be with the backup extra: "
            "uv tool install --editable './be[backup]'"
        ) from None
    return boto3.client("s3")


def upload_object(uri: str, local_path: Path) -> None:
    scheme, bucket, key = parse_storage_uri(uri)
    if scheme == "gs":
        _gcs_blob(bucket, key).upload_from_filename(str(local_path))
    else:
        _s3_client().upload_file(str(local_path), bucket, key)
    click.echo(f"Uploaded {local_path.name} -> {uri}")


def download_object(uri: str, local_path: Path) -> None:
    scheme, bucket, key = parse_storage_uri(uri)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    if scheme == "gs":
        _gcs_blob(bucket, key).download_to_filename(str(local_path))
    else:
        _s3_client().download_file(bucket, key, str(local_path))
    click.echo(f"Downloaded {uri} -> {local_path}")
