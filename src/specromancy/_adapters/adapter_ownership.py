"""Manifest ownership, drift checks, preflight, and per-file atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .adapter_contracts import ADAPTER_SCHEMA_VERSION, MANIFEST_PATH, AdapterError, _target_for_path
from ..hashing import SHA256_PATTERN, normalize_relative_path, sha256_bytes


def write_adapters(
    root: Path, rendered: Mapping[str, bytes], manifest_bytes: bytes
) -> tuple[str, ...]:
    """Preflight ownership, replace outputs, recheck stale hashes, then write manifest."""

    previous = _read_previous_manifest(root)
    conflicts, stale = _preflight_generation(root, rendered, previous)
    if conflicts:
        raise AdapterError(
            "adapter generation stopped to protect unowned or modified files",
            conflicts,
        )

    for path, content in rendered.items():
        target = _target(root, path)
        if target.is_file() and not target.is_symlink():
            try:
                if target.read_bytes() == content:
                    continue
            except OSError as exc:
                raise AdapterError(
                    "cannot read generated adapter destination",
                    {"path": path, "error": str(exc)},
                ) from exc
        _atomic_write(root, path, content)

    for path, expected_hash in stale:
        target = _target(root, path)
        if not target.exists() and not target.is_symlink():
            continue
        if target.is_symlink() or not target.is_file():
            raise AdapterError(
                "stale generated adapter changed during generation",
                {"stale_modified": [path]},
            )
        current = sha256_bytes(target.read_bytes())
        if current != expected_hash:
            raise AdapterError(
                "stale generated adapter changed during generation",
                {"stale_modified": [path]},
            )
        target.unlink()

    _atomic_write(root, MANIFEST_PATH, manifest_bytes)
    return tuple(path for path, _ in stale)


def _read_previous_manifest(root: Path) -> dict[str, Any] | None:
    path = _target(root, MANIFEST_PATH)
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file():
        raise AdapterError("adapter manifest is not a regular file", {"path": MANIFEST_PATH})
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AdapterError(
            "adapter manifest is unreadable or invalid",
            {"path": MANIFEST_PATH, "error": str(exc)},
        ) from exc
    _owned_paths(value)
    return value


def _owned_paths(manifest: Mapping[str, Any]) -> dict[str, str]:
    if manifest.get("schema_version") != ADAPTER_SCHEMA_VERSION:
        raise AdapterError(
            "unsupported adapter manifest schema",
            {"path": MANIFEST_PATH, "schema_version": manifest.get("schema_version")},
        )
    generated = manifest.get("generated")
    if not isinstance(generated, list):
        raise AdapterError("adapter manifest has no generated path list", {"path": MANIFEST_PATH})
    owned: dict[str, str] = {}
    for item in generated:
        if not isinstance(item, Mapping):
            raise AdapterError(
                "adapter manifest has an invalid generated entry",
                {"path": MANIFEST_PATH},
            )
        path = item.get("path")
        digest = item.get("sha256")
        try:
            normalized = normalize_relative_path(path)
        except (TypeError, ValueError) as exc:
            raise AdapterError(
                "adapter manifest contains an unsafe path",
                {"path": path, "error": str(exc)},
            ) from exc
        if normalized == MANIFEST_PATH or normalized in owned:
            raise AdapterError(
                "adapter manifest contains a duplicate or self-owned path",
                {"path": normalized},
            )
        if not _is_managed_adapter_path(normalized):
            raise AdapterError(
                "adapter manifest contains a path outside generated adapter locations",
                {"path": normalized},
            )
        target = item.get("target")
        if target != _target_for_path(normalized):
            raise AdapterError(
                "adapter manifest target does not match its generated path",
                {"path": normalized, "target": target},
            )
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise AdapterError(
                "adapter manifest contains an invalid content hash",
                {"path": normalized, "sha256": digest},
            )
        owned[normalized] = digest
    return owned


def _preflight_generation(
    root: Path,
    rendered: Mapping[str, bytes],
    previous: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    owned = {} if previous is None else _owned_paths(previous)
    expected = set(rendered)
    conflicts: dict[str, Any] = {}
    unowned = []
    unsafe = []
    for path in sorted(expected):
        target = _target(root, path)
        problem = _unsafe_existing_path(root, target)
        if problem is not None:
            unsafe.append({"path": path, "reason": problem})
        elif (target.exists() or target.is_symlink()) and path not in owned:
            unowned.append(path)

    unexpected = sorted(_managed_paths(root) - expected - set(owned))
    if unexpected:
        unowned.extend(path for path in unexpected if path not in unowned)

    stale: list[tuple[str, str]] = []
    stale_modified = []
    for path in sorted(set(owned) - expected):
        target = _target(root, path)
        if not target.exists() and not target.is_symlink():
            continue
        problem = _unsafe_existing_path(root, target)
        if problem is not None or target.is_symlink() or not target.is_file():
            stale_modified.append(path)
            continue
        try:
            current_hash = sha256_bytes(target.read_bytes())
        except OSError:
            stale_modified.append(path)
            continue
        if current_hash == owned[path]:
            stale.append((path, owned[path]))
        else:
            stale_modified.append(path)

    if unowned:
        conflicts["unowned"] = sorted(unowned)
    if unsafe:
        conflicts["unsafe"] = unsafe
    if stale_modified:
        conflicts["stale_modified"] = stale_modified
    return conflicts, stale


def _compare(
    root: Path, rendered: Mapping[str, bytes], manifest_bytes: bytes
) -> dict[str, Any]:
    missing = []
    modified = []
    for path, expected in (*rendered.items(), (MANIFEST_PATH, manifest_bytes)):
        target = _target(root, path)
        if not target.exists() and not target.is_symlink():
            missing.append(path)
            continue
        if target.is_symlink() or not target.is_file():
            modified.append(path)
            continue
        try:
            actual = target.read_bytes()
        except OSError:
            modified.append(path)
            continue
        if actual != expected:
            modified.append(path)
    unexpected = sorted(_managed_paths(root) - set(rendered))
    return {
        "missing": sorted(missing),
        "modified": sorted(modified),
        "unexpected": unexpected,
    }


def _has_drift(drift: Mapping[str, Any]) -> bool:
    return any(bool(value) for value in drift.values())


def _managed_paths(root: Path) -> set[str]:
    paths: set[str] = set()
    singles = (".claude/CLAUDE.md", ".github/copilot-instructions.md")
    for path in singles:
        target = root / path
        if target.exists() or target.is_symlink():
            paths.add(path)
    scans = (
        (root / ".agents" / "skills", "specromancy-*/SKILL.md"),
        (root / ".claude" / "skills", "*/SKILL.md"),
        (root / ".claude" / "commands" / "specromancy", "*.md"),
        (root / ".github" / "prompts", "specromancy-*.prompt.md"),
        (root / ".opencode" / "commands", "specromancy-*.md"),
    )
    for directory, pattern in scans:
        if not directory.is_dir() or directory.is_symlink():
            continue
        for candidate in directory.glob(pattern):
            if candidate.is_file() or candidate.is_symlink():
                try:
                    paths.add(candidate.relative_to(root).as_posix())
                except ValueError:
                    continue
    return paths


def _is_managed_adapter_path(path: str) -> bool:
    parts = Path(path).parts
    if path in {".claude/CLAUDE.md", ".github/copilot-instructions.md"}:
        return True
    if len(parts) == 4 and parts[:2] == (".agents", "skills"):
        return parts[2].startswith("specromancy-") and parts[3] == "SKILL.md"
    if len(parts) == 4 and parts[:2] == (".claude", "skills"):
        return parts[3] == "SKILL.md"
    if len(parts) == 4 and parts[:3] == (".claude", "commands", "specromancy"):
        return parts[3].endswith(".md")
    if len(parts) == 3 and parts[:2] == (".github", "prompts"):
        return parts[2].startswith("specromancy-") and parts[2].endswith(
            ".prompt.md"
        )
    if len(parts) == 3 and parts[:2] == (".opencode", "commands"):
        return parts[2].startswith("specromancy-") and parts[2].endswith(".md")
    return False


def _unsafe_existing_path(root: Path, target: Path) -> str | None:
    current = root
    for part in target.relative_to(root).parts[:-1]:
        current = current / part
        if current.is_symlink():
            return "parent-is-symlink"
        if current.exists() and not current.is_dir():
            return "parent-is-not-directory"
    if target.is_symlink():
        return "target-is-symlink"
    if target.exists() and not target.is_file():
        return "target-is-not-file"
    return None


def _target(root: Path, relative: str) -> Path:
    normalized = normalize_relative_path(relative)
    return root / normalized


def _atomic_write(root: Path, relative: str, content: bytes) -> None:
    target = _target(root, relative)
    problem = _unsafe_existing_path(root, target)
    if problem is not None:
        raise AdapterError(
            "generated adapter destination is unsafe",
            {"path": relative, "reason": problem},
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
