"""Deterministic, safely owned adapters for supported agent harnesses."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ._adapters.adapter_contracts import (
    ADAPTER_COMMANDS, ADAPTER_SCHEMA_VERSION, GENERATOR_VERSION, HARNESS_MODES,
    MANIFEST_PATH, REGENERATION_COMMAND, AdapterCommand, AdapterError,
)
from ._adapters.adapter_ownership import _compare, _has_drift, write_adapters
from ._adapters.adapter_rendering import expected_manifest, render_sources
from ._adapters.adapter_sources import capture_sources
from .exit_codes import ExitCode
from .hashing import canonical_json_bytes
from .registry import PipelineRegistry


def generate_adapters(
    repository_root: Path,
    registry: PipelineRegistry,
    command_metadata: Mapping[str, Any] | None = None,
    *,
    check: bool = False,
) -> dict[str, Any]:
    """Generate adapters or compare the worktree to deterministic output.

    Omitted metadata is derived from the graphs captured for this invocation.
    Explicit caller-supplied metadata retains its existing hash contract.
    """

    root = repository_root.resolve(strict=True)
    sources = capture_sources(root, registry, command_metadata)
    rendered = render_sources(sources)
    manifest = expected_manifest(sources, rendered)
    manifest_bytes = canonical_json_bytes(manifest) + b"\n"

    if check:
        drift = _compare(root, rendered, manifest_bytes)
        if _has_drift(drift):
            raise AdapterError("generated adapter drift detected", drift)
        return _result(
            "generated adapters are up to date",
            checked=True,
            paths=tuple(rendered),
            canonical_source_sha256=manifest["canonical_source"][
                "sha256"
            ],
        )

    removed = write_adapters(root, rendered, manifest_bytes)
    return _result(
        f"generated {len(rendered)} harness adapter files",
        checked=False,
        paths=tuple(rendered),
        canonical_source_sha256=manifest["canonical_source"]["sha256"],
        removed=removed,
    )


def render_adapters(
    repository_root: Path,
    registry: PipelineRegistry,
    command_metadata: Mapping[str, Any],
) -> dict[str, bytes]:
    """Render all generated adapter files in stable path order."""

    root = repository_root.resolve(strict=True)
    sources = capture_sources(
        root, registry, command_metadata, include_manifest_inputs=False
    )
    return render_sources(sources)


def _result(
    message: str,
    *,
    checked: bool,
    paths: tuple[str, ...],
    canonical_source_sha256: str,
    removed: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "adapters",
        "code": int(ExitCode.SUCCESS),
        "message": message,
        "adapters": {
            "checked": checked,
            "manifest": MANIFEST_PATH,
            "canonical_source_sha256": canonical_source_sha256,
            "paths": list(paths),
            "removed": list(removed),
        },
    }
