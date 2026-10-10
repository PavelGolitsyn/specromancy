"""Load pipeline TOML and assemble configuration with graph validation."""

from __future__ import annotations

import hashlib
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .config_errors import PipelineConfigError, _MISSING
from .config_fields import FieldContext, IDENTIFIER_PATTERN, _safe_declared_path
from .config_models import (
    PhaseConfig,
    PipelineConfig,
    TransitionConfig,
    ValidationCommand,
    ValidatorConfig,
)
from .config_phase_parser import (
    MUTATION_POLICIES,
    VALIDATOR_TYPES,
    _validate_inputs,
    _validate_output_pattern,
    parse_commands,
    parse_phase,
    parse_transition,
    parse_validator,
)
from .config_serialization import _canonical_document, _encode_canonical_document
from ..graph import validate_graph


SUPPORTED_SCHEMA_VERSION = 1


def _discover_root(path: Path) -> Path | None:
    for candidate in (path.parent, *path.parent.parents):
        if (candidate / ".git").exists():
            return candidate.resolve()
    return None


class _Loader(FieldContext):
    """Pipeline assembly with inherited field helpers and legacy parser delegates."""

    def parse(self, raw: Mapping[str, Any]) -> PipelineConfig:
        allowed_top = {
            "schema_version",
            "id",
            "version",
            "start",
            "terminal_outcomes",
            "artifact_pattern",
            "allow_non_git",
            "phases",
        }
        self.check_unknown(raw, allowed_top)
        schema_version = self.require_integer(
            raw.get("schema_version"), "schema_version", minimum=1
        )
        if schema_version != SUPPORTED_SCHEMA_VERSION:
            self.fail(
                "unsupported-schema-version",
                f"schema_version {schema_version} is not supported",
                field="schema_version",
                value=schema_version,
                remediation=f"set schema_version to {SUPPORTED_SCHEMA_VERSION}",
            )
        pipeline_id = self.require_identifier(raw.get("id"), "id")
        version = self.require_integer(raw.get("version"), "version", minimum=1)
        start = self.require_identifier(raw.get("start"), "start")
        terminal_outcomes = self.string_list(
            raw.get("terminal_outcomes"),
            "terminal_outcomes",
            allow_empty=False,
            identifiers=True,
        )
        artifact_pattern = self.require_string(
            raw.get("artifact_pattern"), "artifact_pattern"
        )
        allow_non_git = raw.get("allow_non_git", False)
        if not isinstance(allow_non_git, bool):
            self.fail(
                "invalid-field-type",
                "allow_non_git must be a boolean",
                field="allow_non_git",
                value=allow_non_git,
                remediation="use true or false",
            )
        _validate_output_pattern(
            artifact_pattern, "artifact_pattern", self.fail, output_name="output.md"
        )
        raw_phases = raw.get("phases")
        if not isinstance(raw_phases, list) or not raw_phases:
            self.fail(
                "invalid-field-type",
                "phases must be a non-empty array of tables",
                field="phases",
                value=raw_phases,
                remediation="declare one or more [[phases]] tables",
            )
        phases = tuple(self.parse_phase(item) for item in raw_phases)
        for phase in phases:
            if phase.id in terminal_outcomes:
                self.fail(
                    "terminal-outcome-phase",
                    f"terminal outcome {phase.id!r} cannot also be a phase id",
                    phase=phase.id,
                    field="id",
                    value=phase.id,
                    remediation="rename the phase or terminal outcome",
                )
        validate_graph(phases, start, frozenset(terminal_outcomes), self.fail)
        canonical = _canonical_document(
            schema_version,
            pipeline_id,
            version,
            start,
            terminal_outcomes,
            artifact_pattern,
            allow_non_git,
            phases,
        )
        canonical_json = _encode_canonical_document(canonical)
        config_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        return PipelineConfig(
            schema_version=schema_version,
            id=pipeline_id,
            version=version,
            start=start,
            terminal_outcomes=terminal_outcomes,
            artifact_pattern=artifact_pattern,
            allow_non_git=allow_non_git,
            phases=phases,
            path=self.path,
            repository_root=self.repository_root,
            canonical_json=canonical_json,
            config_hash=config_hash,
        )

    def parse_phase(self, value: Any) -> PhaseConfig:
        return parse_phase(self, value)

    def parse_validator(
        self, phase_raw: Mapping[str, Any], phase_id: str
    ) -> ValidatorConfig:
        return parse_validator(self, phase_raw, phase_id)

    def parse_commands(
        self, raw: Mapping[str, Any], phase_id: str
    ) -> tuple[ValidationCommand, ...]:
        return parse_commands(self, raw, phase_id)

    def parse_transition(self, value: Any, phase_id: str) -> TransitionConfig:
        return parse_transition(self, value, phase_id)


def load_pipeline(
    path: str | Path,
    repository_root: str | Path | None = None,
    *,
    root: str | Path | None = None,
) -> PipelineConfig:
    """Load and fully validate a pipeline TOML file.

    ``root`` is accepted as a concise alias for ``repository_root``. Supplying
    both is rejected to keep path authority unambiguous.
    """

    source = Path(path).expanduser()
    try:
        source = source.resolve(strict=True)
    except OSError as exc:
        unresolved = source.resolve()
        raise PipelineConfigError(
            "pipeline-not-found",
            f"cannot read pipeline configuration: {unresolved}",
            path=unresolved,
            field="pipeline",
            value=str(unresolved),
            remediation="provide the path to an existing pipeline TOML file",
        ) from exc
    if not source.is_file():
        raise PipelineConfigError(
            "pipeline-not-file",
            f"pipeline configuration is not a file: {source}",
            path=source,
            field="pipeline",
            value=str(source),
            remediation="provide the path to a regular TOML file",
        )
    if repository_root is not None and root is not None:
        raise TypeError("pass repository_root or root, not both")
    requested_root = repository_root if repository_root is not None else root
    if requested_root is None:
        discovered = _discover_root(source)
        if discovered is None:
            raise PipelineConfigError(
                "repository-root-not-found",
                "could not discover a repository root for the pipeline",
                path=source,
                field="repository_root",
                remediation="pass repository_root for non-Git fixture repositories",
            )
        resolved_root = discovered
    else:
        resolved_root = Path(requested_root).expanduser().resolve()
    if not resolved_root.is_dir():
        raise PipelineConfigError(
            "invalid-repository-root",
            f"repository root is not a directory: {resolved_root}",
            path=source,
            field="repository_root",
            value=str(resolved_root),
            remediation="pass an existing repository directory",
        )
    if not source.is_relative_to(resolved_root):
        raise PipelineConfigError(
            "pipeline-outside-repository",
            "pipeline configuration resolves outside the repository",
            path=source,
            field="pipeline",
            value=str(source),
            remediation="place the pipeline inside the repository",
        )
    try:
        with source.open("rb") as stream:
            raw = tomllib.load(stream)
    except tomllib.TOMLDecodeError as exc:
        raise PipelineConfigError(
            "invalid-toml",
            f"pipeline configuration is not valid TOML: {exc}",
            path=source,
            field="pipeline",
            remediation="correct the TOML syntax",
        ) from exc
    except OSError as exc:
        raise PipelineConfigError(
            "pipeline-unreadable",
            f"cannot read pipeline configuration: {exc}",
            path=source,
            field="pipeline",
            remediation="make the file readable and try again",
        ) from exc
    return _Loader(source, resolved_root).parse(raw)
