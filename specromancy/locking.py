"""Per-run lock files implemented with exclusive standard-library creation."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import SpecromancyError
from .exit_codes import ExitCode


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class LockHeldError(SpecromancyError):
    """Raised when another process owns a run's lock file."""

    def __init__(self, path: Path, owner: dict[str, Any] | None = None) -> None:
        details: dict[str, Any] = {
            "lock_path": str(path),
            "remediation": (
                "verify that the recorded process is no longer running, then remove "
                "the lock file manually"
            ),
        }
        if owner is not None:
            details["owner"] = owner
        super().__init__(ExitCode.LOCK_HELD, f"run lock is already held: {path}", details)


class RunLock:
    """An exclusive lock that records PID and acquisition time for diagnosis."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.path = Path(path)
        self._clock = clock
        self._fd: int | None = None

    def acquire(self) -> "RunLock":
        if self._fd is not None:
            raise RuntimeError("lock is already acquired by this object")
        payload = {
            "pid": os.getpid(),
            "acquired_at": _timestamp(self._clock()),
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            descriptor = os.open(self.path, flags, 0o600)
        except FileExistsError as exc:
            raise LockHeldError(self.path, _read_owner(self.path)) from exc
        try:
            content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            os.write(descriptor, (content + "\n").encode("utf-8"))
            os.fsync(descriptor)
        except BaseException:
            os.close(descriptor)
            self.path.unlink(missing_ok=True)
            raise
        self._fd = descriptor
        return self

    def release(self) -> None:
        if self._fd is None:
            return
        descriptor = self._fd
        self._fd = None
        os.close(descriptor)
        try:
            self.path.unlink()
        except FileNotFoundError:
            # Losing an owned lock is unsafe: another writer could already be active.
            raise RuntimeError(f"owned lock disappeared before release: {self.path}")

    def __enter__(self) -> "RunLock":
        return self.acquire()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.release()


def _read_owner(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    return value


FileLock = RunLock
