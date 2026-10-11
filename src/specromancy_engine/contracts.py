"""Small public constants shared across configuration and CLI boundaries."""

from __future__ import annotations


RESERVED_COMMANDS = frozenset(
    {
        "init",
        "phase",
        "validate",
        "approve",
        "request-approval",
        "block",
        "status",
        "resume",
        "run",
        "adapters",
    }
)

