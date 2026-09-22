"""Cross-platform exclusive run locks and explicit stale-lock recovery."""

from __future__ import annotations

import json
import os
import secrets
import socket
import threading
from functools import wraps
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

from .clock import Clock, SystemClock, utc_timestamp
from .errors import ConcurrencyError, InvalidInputError, SpecromancyError
from .io import canonical_json, read_text
from .paths import RepositoryPaths


DEFAULT_STALE_AFTER_SECONDS = 60 * 60
_LOCAL_GUARD = threading.Lock()
_HELD_LOCKS: dict[str, tuple[int, str, int]] = {}
_T = TypeVar("_T")


@dataclass(frozen=True)
class RunLockInfo:
    run_id: str
    owner_id: str
    pid: int
    hostname: str
    created_at: str
    command: str


def _decode_lock(paths: RepositoryPaths, run_id: str) -> RunLockInfo:
    target = paths.run_lock(run_id)
    try:
        value = json.loads(read_text(target))
    except json.JSONDecodeError as exc:
        raise ConcurrencyError(
            "The run lock is malformed.", path=paths.serialize(target)
        ) from exc
    required = {"run_id", "owner_id", "pid", "hostname", "created_at", "command"}
    if not isinstance(value, dict) or not required.issubset(value):
        raise ConcurrencyError(
            "The run lock is missing ownership diagnostics.",
            path=paths.serialize(target),
        )
    if value.get("run_id") != run_id:
        raise ConcurrencyError(
            "The run lock belongs to a different run ID.", path=paths.serialize(target)
        )
    try:
        return RunLockInfo(
            run_id=str(value["run_id"]),
            owner_id=str(value["owner_id"]),
            pid=int(value["pid"]),
            hostname=str(value["hostname"]),
            created_at=str(value["created_at"]),
            command=str(value["command"]),
        )
    except (TypeError, ValueError) as exc:
        raise ConcurrencyError(
            "The run lock has invalid ownership diagnostics.",
            path=paths.serialize(target),
        ) from exc


class RunLock:
    """Exclusive lock implemented with atomic file creation.

    The lock is re-entrant only for the same thread. This lets the central state
    engine enforce locking even when a phase wraps its guard checks in a wider
    critical section.
    """

    def __init__(
        self,
        paths: RepositoryPaths,
        run_id: str,
        command: str,
        clock: Clock | None = None,
    ) -> None:
        self.paths = paths
        self.run_id = run_id
        self.command = command
        self.clock = clock or SystemClock()
        self.owner_id = secrets.token_hex(16)
        self.acquired = False
        self.reentrant = False

    def __enter__(self) -> "RunLock":
        target = self.paths.run_lock(self.run_id)
        key = str(target)
        thread_id = threading.get_ident()
        with _LOCAL_GUARD:
            held = _HELD_LOCKS.get(key)
            if held is not None and held[0] == thread_id:
                self.owner_id = held[1]
                _HELD_LOCKS[key] = (thread_id, held[1], held[2] + 1)
                self.acquired = True
                self.reentrant = True
                return self

        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1",
            "run_id": self.run_id,
            "owner_id": self.owner_id,
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "created_at": utc_timestamp(self.clock.now()),
            "command": self.command,
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            descriptor = os.open(target, flags, 0o600)
        except FileExistsError as exc:
            details: dict[str, Any] = {"lock_path": self.paths.serialize(target)}
            try:
                observed = _decode_lock(self.paths, self.run_id)
                details.update(
                    owner_id=observed.owner_id,
                    pid=observed.pid,
                    hostname=observed.hostname,
                    created_at=observed.created_at,
                    command=observed.command,
                )
            except SpecromancyError as diagnostic:
                details["diagnostic"] = diagnostic.message
            raise ConcurrencyError(
                f"Run '{self.run_id}' is locked by another writer.",
                hint=(
                    "Inspect the lock and use explicit lock recovery only after "
                    "confirming the owner is gone or the lock is stale."
                ),
                details=details,
            ) from exc
        try:
            os.write(descriptor, canonical_json(payload).encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        with _LOCAL_GUARD:
            _HELD_LOCKS[key] = (thread_id, self.owner_id, 1)
        self.acquired = True
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if not self.acquired:
            return
        target = self.paths.run_lock(self.run_id)
        key = str(target)
        thread_id = threading.get_ident()
        with _LOCAL_GUARD:
            held = _HELD_LOCKS.get(key)
            if held is None or held[0] != thread_id or held[1] != self.owner_id:
                return
            if held[2] > 1:
                _HELD_LOCKS[key] = (held[0], held[1], held[2] - 1)
                return
            del _HELD_LOCKS[key]
        try:
            observed = _decode_lock(self.paths, self.run_id)
        except SpecromancyError:
            return
        if observed.owner_id == self.owner_id:
            try:
                target.unlink()
            except FileNotFoundError:
                pass


def locked_run(command: str) -> Callable[[Callable[..., _T]], Callable[..., _T]]:
    """Hold a run lock around a phase operation, preserving injected clocks."""

    def decorate(function: Callable[..., _T]) -> Callable[..., _T]:
        @wraps(function)
        def wrapped(
            repository_root: str | Path,
            run_id: str,
            *args: Any,
            **kwargs: Any,
        ) -> _T:
            paths = RepositoryPaths(Path(repository_root))
            clock = kwargs.get("clock") or SystemClock()
            with RunLock(paths, run_id, command, clock):
                return function(repository_root, run_id, *args, **kwargs)

        return wrapped

    return decorate


def inspect_run_lock(
    repository_root: str | Path, run_id: str
) -> RunLockInfo | None:
    paths = RepositoryPaths(Path(repository_root))
    target = paths.run_lock(run_id)
    if not target.exists():
        return None
    return _decode_lock(paths, run_id)


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def lock_is_stale(
    info: RunLockInfo,
    *,
    now: datetime | None = None,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> tuple[bool, str]:
    current = now or datetime.now(timezone.utc)
    try:
        created = datetime.fromisoformat(info.created_at.replace("Z", "+00:00"))
    except ValueError:
        return True, "the lock timestamp is invalid"
    age = max(0.0, (current.astimezone(timezone.utc) - created).total_seconds())
    if info.hostname == socket.gethostname() and not _pid_is_alive(info.pid):
        return True, "the local owner process is no longer alive"
    if age >= stale_after_seconds:
        return True, f"the lock is {int(age)} seconds old"
    return False, "the recorded owner may still be active"


def recover_run_lock(
    repository_root: str | Path,
    run_id: str,
    *,
    clock: Clock | None = None,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> RunLockInfo:
    """Remove a demonstrably stale lock and return its former owner."""

    paths = RepositoryPaths(Path(repository_root))
    info = inspect_run_lock(paths.root, run_id)
    if info is None:
        raise InvalidInputError(
            f"Run '{run_id}' has no lock to recover.",
            hint="Inspect the run lock before requesting recovery.",
        )
    now = (clock or SystemClock()).now()
    stale, reason = lock_is_stale(
        info, now=now, stale_after_seconds=stale_after_seconds
    )
    if not stale:
        raise ConcurrencyError(
            f"Run '{run_id}' lock is not stale.",
            hint="Wait for the owner to finish or retry recovery after the stale-lock age.",
            details={"pid": info.pid, "hostname": info.hostname, "reason": reason},
        )
    target = paths.run_lock(run_id)
    observed = _decode_lock(paths, run_id)
    if observed.owner_id != info.owner_id:
        raise ConcurrencyError(
            "The run lock changed while recovery was being evaluated.",
            hint="Inspect the new lock owner before retrying recovery.",
        )
    target.unlink()
    return info
