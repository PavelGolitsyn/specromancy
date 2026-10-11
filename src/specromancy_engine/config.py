"""Public compatibility facade for declarative pipeline configuration.

Parsing, immutable records, diagnostics, and canonical encoding live in separate
internal modules. Existing imports here continue to reference those same objects.
"""

from __future__ import annotations

from pathlib import Path

from ._config.config_errors import PipelineConfigError, _MISSING, _json_value
from ._config.config_loader import (
    IDENTIFIER_PATTERN,
    MUTATION_POLICIES,
    SUPPORTED_SCHEMA_VERSION,
    VALIDATOR_TYPES,
    _Loader,
    _discover_root,
    _safe_declared_path,
    _validate_inputs,
    _validate_output_pattern,
    load_pipeline,
)
from ._config.config_models import (
    PhaseConfig,
    PipelineConfig,
    TransitionConfig,
    ValidationCommand,
    ValidatorConfig,
)
from ._config.config_serialization import _canonical_document
from .contracts import RESERVED_COMMANDS


def load_config(
    path: str | Path,
    repository_root: str | Path | None = None,
) -> PipelineConfig:
    """Backward-compatible descriptive alias for :func:`load_pipeline`."""

    return load_pipeline(path, repository_root)


def canonicalize_pipeline(pipeline: PipelineConfig) -> str:
    return pipeline.canonical_json


def hash_pipeline(pipeline: PipelineConfig) -> str:
    return pipeline.config_hash


def require_pipeline_hash(pipeline: PipelineConfig, expected_hash: str) -> None:
    """Reject configuration drift for a persisted in-progress run."""

    if pipeline.config_hash != expected_hash:
        raise PipelineConfigError(
            "pipeline-hash-mismatch",
            "pipeline configuration changed after the run was created",
            path=pipeline.path,
            field="config_hash",
            value={"expected": expected_hash, "actual": pipeline.config_hash},
            remediation="restore the original pipeline or start a new run",
        )
