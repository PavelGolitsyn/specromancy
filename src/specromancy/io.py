"""Safe, deterministic file I/O primitives."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import ValidationError


DEFAULT_TEXT_LIMIT = 2 * 1024 * 1024


def read_text(path: str | Path, *, max_bytes: int = DEFAULT_TEXT_LIMIT) -> str:
    """Read bounded UTF-8 text, rejecting oversized managed inputs."""

    target = Path(path)
    if max_bytes < 1:
        raise ValidationError("Text read limit must be positive.", path=str(target))
    try:
        size = target.stat().st_size
        if size > max_bytes:
            raise ValidationError(
                f"Managed text exceeds the {max_bytes}-byte safety limit.",
                path=str(target),
                details={"size_bytes": size, "limit_bytes": max_bytes},
            )
        data = target.read_bytes()
        if len(data) > max_bytes:
            raise ValidationError(
                f"Managed text exceeds the {max_bytes}-byte safety limit.",
                path=str(target),
                details={"size_bytes": len(data), "limit_bytes": max_bytes},
            )
        return data.decode("utf-8")
    except ValidationError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ValidationError(
            f"Could not read UTF-8 text from {target}.", path=str(target)
        ) from exc


def read_text_bounded(path: str | Path, max_bytes: int) -> str:
    """Compatibility-friendly explicit bounded-read helper."""

    return read_text(path, max_bytes=max_bytes)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def atomic_write_text(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, raw_temporary = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(raw_temporary)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
        _sync_directory(target.parent)
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"Could not atomically write {target}.", path=str(target)) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def atomic_write_json(path: str | Path, value: Any) -> None:
    atomic_write_text(path, canonical_json(value))


def normalized_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(normalized_text(text).encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    target = Path(path)
    digest = hashlib.sha256()
    try:
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ValidationError(f"Could not hash {target}.", path=str(target)) from exc
    return digest.hexdigest()


def append_json_line(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    try:
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"Could not append to {target}.", path=str(target)) from exc
