"""UTC time and run identifier helpers with deterministic injection points."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current timezone-aware instant."""


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True)
class FixedClock:
    instant: datetime

    def __post_init__(self) -> None:
        if self.instant.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware datetime")

    def now(self) -> datetime:
        return self.instant


def utc_timestamp(value: datetime) -> str:
    """Serialize an instant as stable second-precision UTC."""

    if value.tzinfo is None:
        raise ValueError("UTC timestamps require a timezone-aware datetime")
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "run"


@dataclass
class RunIdGenerator:
    """Generate human-readable IDs; inject ``token_factory`` in tests."""

    clock: Clock = SystemClock()
    token_factory: Callable[[], str] = lambda: secrets.token_hex(3)

    def generate(self, title: str) -> str:
        day = self.clock.now().astimezone(timezone.utc).strftime("%Y%m%d")
        token = re.sub(r"[^a-z0-9]", "", self.token_factory().lower())
        if not token:
            raise ValueError("run ID token must contain an ASCII letter or digit")
        suffix = f"-{token[:12]}"
        available = 80 - len(day) - len(suffix) - 1
        slug = _slugify(title)[:available].strip("-") or "run"
        return f"{day}-{slug}{suffix}"

