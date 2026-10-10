"""Shared source discovery for architecture and dependency contract checks."""

from pathlib import Path


def runtime_sources(package: Path) -> list[Path]:
    return sorted(package.rglob("*.py"))
