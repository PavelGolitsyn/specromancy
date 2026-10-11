"""Canonical SHA-256 helpers and safe relative-path handling."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON data in the canonical form used by persisted hashes."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_text(content: str) -> str:
    return sha256_bytes(content.encode("utf-8"))


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def sha256_file(path: str | os.PathLike[str]) -> str:
    """Hash a regular file without normalizing its contents."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_relative_path(path: str | os.PathLike[str]) -> str:
    """Return a normalized POSIX path, rejecting absolute and dot paths."""

    raw = os.fspath(path)
    if not raw or "\\" in raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise ValueError(f"path must be a non-empty relative POSIX path: {raw!r}")
    pure = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"path contains a dot segment: {raw!r}")
    normalized = pure.as_posix()
    if normalized != raw:
        raise ValueError(f"path is not normalized: {raw!r}")
    return normalized


def relative_path(path: Path, root: Path) -> str:
    """Return a normalized path relative to an already trusted root."""

    resolved_root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"path resolves outside root: {path}")
    return normalize_relative_path(resolved.relative_to(resolved_root).as_posix())


def resolve_relative_path(
    root: str | os.PathLike[str],
    relative: str | os.PathLike[str],
    *,
    must_exist: bool = False,
) -> Path:
    """Resolve a normalized relative path and reject symlink escapes."""

    normalized = normalize_relative_path(relative)
    resolved_root = Path(root).resolve(strict=True)
    candidate = (resolved_root / normalized).resolve(strict=must_exist)
    if not candidate.is_relative_to(resolved_root):
        raise ValueError(f"path resolves outside root: {normalized!r}")
    return candidate


# Concise aliases are useful at call sites and preserve the public terminology.
hash_bytes = sha256_bytes
hash_text = sha256_text
hash_json = sha256_json
hash_file = sha256_file
