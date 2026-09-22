"""Harness adapter registry and public lifecycle helpers."""

from __future__ import annotations

from pathlib import Path

from ..errors import InvalidInputError
from .base import Adapter, check_adapters, clean_adapters, generate_adapters
from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .copilot import CopilotAdapter
from .hermes import HermesAdapter
from .opencode import OpenCodeAdapter


ADAPTERS: tuple[Adapter, ...] = (
    ClaudeAdapter(),
    CodexAdapter(),
    CopilotAdapter(),
    HermesAdapter(),
    OpenCodeAdapter(),
)
ADAPTER_NAMES = tuple(adapter.name for adapter in ADAPTERS)


def select_adapters(name: str | None) -> tuple[Adapter, ...]:
    if name is None:
        return ADAPTERS
    selected = tuple(adapter for adapter in ADAPTERS if adapter.name == name)
    if not selected:
        raise InvalidInputError(
            f"Unknown harness adapter '{name}'.", details={"supported": ADAPTER_NAMES}
        )
    return selected


def generate(root: Path, *, harness: str | None = None, force: bool = False) -> dict:
    return generate_adapters(
        root, ADAPTERS, selected=select_adapters(harness), force=force
    )


def check(root: Path, *, harness: str | None = None) -> dict:
    return check_adapters(root, selected=select_adapters(harness))


def clean(root: Path, *, harness: str | None = None) -> dict:
    return clean_adapters(root, ADAPTERS, selected=select_adapters(harness))


def list_adapters() -> list[dict]:
    return [
        {
            "name": adapter.name,
            "version": adapter.version,
            "native": adapter.native,
            "minimum_harness_version": adapter.minimum_harness_version,
        }
        for adapter in ADAPTERS
    ]


__all__ = [
    "ADAPTERS",
    "ADAPTER_NAMES",
    "check",
    "clean",
    "generate",
    "list_adapters",
    "select_adapters",
]
