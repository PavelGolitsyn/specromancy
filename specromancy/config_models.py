"""Immutable configuration records shared by runtime components."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ValidationCommand:
    """A deterministic command invoked without a shell."""

    argv: tuple[str, ...]
    timeout_seconds: float = 300.0
    required: bool = True


@dataclass(frozen=True, slots=True)
class ValidatorConfig:
    """Rules for validating a phase's primary output."""

    type: str
    required_headings: tuple[str, ...] = ()
    declared_path: str | None = None
    resolved_path: Path | None = None
    heading_occurrence: str = "exactly-once"
    json_schema: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class TransitionConfig:
    outcome: str
    target: str | None = None
    max_traversals: int | None = None
    pause: bool = False


@dataclass(frozen=True, slots=True)
class PhaseConfig:
    id: str
    skill: str
    skill_path: Path
    inputs: tuple[str, ...]
    output_name: str
    output_template: str | None
    output_template_path: Path | None
    mutation: str
    allowlist: tuple[str, ...]
    completion_criteria: tuple[str, ...]
    validator: ValidatorConfig
    commands: tuple[ValidationCommand, ...]
    approval_conditions: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    transitions: tuple[TransitionConfig, ...]
    max_visits: int | None = None

    @property
    def validation_commands(self) -> tuple[ValidationCommand, ...]:
        """Descriptive alias used by action-packet code in later stages."""

        return self.commands


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    schema_version: int
    id: str
    version: int
    start: str
    terminal_outcomes: tuple[str, ...]
    artifact_pattern: str
    allow_non_git: bool
    phases: tuple[PhaseConfig, ...]
    path: Path
    repository_root: Path
    canonical_json: str
    config_hash: str

    def phase(self, phase_id: str) -> PhaseConfig:
        """Return a configured phase by id."""

        for phase in self.phases:
            if phase.id == phase_id:
                return phase
        raise KeyError(phase_id)

    @property
    def phase_ids(self) -> tuple[str, ...]:
        return tuple(phase.id for phase in self.phases)

    @property
    def hash(self) -> str:
        """Compatibility-friendly shorthand for the canonical config hash."""

        return self.config_hash
