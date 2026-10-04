"""Canonical pipeline documents and their compatibility-sensitive encoding."""

from __future__ import annotations

import json
from typing import Any

from .config_models import PhaseConfig


def _canonical_document(
    schema_version: int,
    pipeline_id: str,
    version: int,
    start: str,
    terminal_outcomes: tuple[str, ...],
    artifact_pattern: str,
    allow_non_git: bool,
    phases: tuple[PhaseConfig, ...],
) -> dict[str, Any]:
    return {
        "allow_non_git": allow_non_git,
        "artifact_pattern": artifact_pattern,
        "id": pipeline_id,
        "phases": [
            {
                "allowlist": list(phase.allowlist),
                "approval_conditions": list(phase.approval_conditions),
                "commands": [
                    {
                        "argv": list(command.argv),
                        "required": command.required,
                        "timeout_seconds": command.timeout_seconds,
                    }
                    for command in phase.commands
                ],
                "completion_criteria": list(phase.completion_criteria),
                "id": phase.id,
                "inputs": list(phase.inputs),
                "max_visits": phase.max_visits,
                "mutation": phase.mutation,
                "output_name": phase.output_name,
                "output_template": phase.output_template,
                "skill": phase.skill,
                "stop_conditions": list(phase.stop_conditions),
                "transitions": [
                    {
                        "max_traversals": transition.max_traversals,
                        "outcome": transition.outcome,
                        "target": transition.target,
                        **({"pause": True} if transition.pause else {}),
                    }
                    for transition in sorted(
                        phase.transitions, key=lambda item: item.outcome
                    )
                ],
                "validator": {
                    "heading_occurrence": phase.validator.heading_occurrence,
                    "path": phase.validator.declared_path,
                    "required_headings": list(phase.validator.required_headings),
                    "type": phase.validator.type,
                },
            }
            for phase in phases
        ],
        "schema_version": schema_version,
        "start": start,
        "terminal_outcomes": sorted(terminal_outcomes),
        "version": version,
    }


def _encode_canonical_document(document: dict[str, Any]) -> str:
    """Preserve pipeline ASCII escaping, unlike generic run JSON hashing."""

    return json.dumps(document, sort_keys=True, separators=(",", ":"))
