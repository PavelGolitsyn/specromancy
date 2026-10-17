"""Shared source discovery for architecture and dependency contract checks."""

from pathlib import Path


def runtime_sources(package: Path) -> list[Path]:
    if not package.is_dir():
        raise AssertionError(f"Runtime source root does not exist: {package}")
    sources = sorted(package.rglob("*.py"))
    if not sources:
        raise AssertionError(f"Runtime source root contains no Python files: {package}")
    return sources
