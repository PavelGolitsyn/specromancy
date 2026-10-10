"""Path-safe run identities and injectable UTC time/random helpers."""

from __future__ import annotations

import inspect
import re
import secrets
from collections.abc import Callable
from datetime import datetime, timezone


RUN_ID_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def validate_run_id(run_id: str) -> str:
    """Return a valid path-safe run ID or raise ``ValueError``."""

    if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(f"invalid run ID: {run_id!r}")
    try:
        datetime.strptime(run_id[:16], "%Y%m%dT%H%M%SZ")
    except ValueError as exc:
        raise ValueError(f"invalid run ID timestamp: {run_id!r}") from exc
    return run_id


def is_valid_run_id(run_id: str) -> bool:
    try:
        validate_run_id(run_id)
    except (TypeError, ValueError):
        return False
    return True


def generate_run_id(
    *,
    clock: Callable[[], datetime] = utc_now,
    random_source: Callable[..., bytes | str] = secrets.token_bytes,
) -> str:
    """Generate a UTC timestamp plus four cryptographically random bytes."""

    now = clock()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    timestamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        inspect.signature(random_source).bind(4)
    except (TypeError, ValueError):
        random_value = random_source()
    else:
        random_value = random_source(4)
    suffix = random_value.hex() if isinstance(random_value, bytes) else random_value
    run_id = f"{timestamp}-{suffix}"
    return validate_run_id(run_id)
