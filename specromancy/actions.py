"""Stable action packets for harness-neutral phase execution."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import Any

from .config import PipelineConfig


ACTION_PACKET_SCHEMA_VERSION = 1


def build_action_packet(
    pipeline: PipelineConfig,
    manifest: dict[str, Any],
    visit: dict[str, Any],
) -> dict[str, Any]:
    """Return a fully resolved, versioned packet for one visit."""

    phase = pipeline.phase(visit["phase_id"])
    run_directory = (
        pipeline.repository_root / ".specromancy" / "runs" / manifest["run_id"]
    )
    validate_command = [
        sys.executable,
        "-m",
        "specromancy",
        "--root",
        str(pipeline.repository_root),
        "--pipeline",
        str(pipeline.path),
        "validate",
        manifest["run_id"],
        phase.id,
    ]
    return {
        "schema_version": ACTION_PACKET_SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "visit_id": visit["ordinal"],
        "visit_attempt": visit["attempt"],
        "visit_status": visit["status"],
        "phase": phase.id,
        "skill": _repository_record(pipeline.repository_root, visit["skill"]),
        "inputs": [
            {
                **record,
                "absolute_path": str(run_directory / record["path"]),
            }
            for record in visit["inputs"]
        ],
        "output": {
            **visit["output"],
            "absolute_path": str(run_directory / visit["output"]["path"]),
        },
        "template": (
            _repository_record(pipeline.repository_root, visit["template"])
            if visit["template"] is not None
            else None
        ),
        "mutation": {
            "policy": phase.mutation,
            "allowlist": list(phase.allowlist),
        },
        "completion_criteria": list(phase.completion_criteria),
        "validation": {
            "type": phase.validator.type,
            "required_headings": list(phase.validator.required_headings),
            "heading_occurrence": phase.validator.heading_occurrence,
            "schema": phase.validator.declared_path,
            "commands": [
                {
                    "argv": list(command.argv),
                    "timeout_seconds": command.timeout_seconds,
                    "required": command.required,
                }
                for command in phase.validation_commands
            ],
        },
        "approval_conditions": list(phase.approval_conditions),
        "stop_conditions": list(phase.stop_conditions),
        "outcomes": [transition.outcome for transition in phase.transitions],
        "final_validation_command": validate_command,
    }


def render_action_packet(packet: dict[str, Any]) -> str:
    """Render a concise terminal representation without losing exact paths."""

    inputs = "\n".join(
        f"- {item['reference']}: {item['absolute_path']} ({item['sha256']})"
        for item in packet["inputs"]
    )
    criteria = "\n".join(
        f"- {criterion}" for criterion in packet["completion_criteria"]
    )
    mutation = packet["mutation"]["policy"]
    allowlist = packet["mutation"]["allowlist"]
    if allowlist:
        mutation += f" ({', '.join(allowlist)})"
    return "\n".join(
        (
            f"Run: {packet['run_id']}",
            f"Visit: {packet['visit_id']} ({packet['visit_status']})",
            f"Phase: {packet['phase']}",
            f"Skill: {packet['skill']['absolute_path']}",
            "Inputs:",
            inputs or "- none",
            f"Output: {packet['output']['absolute_path']}",
            f"Mutation: {mutation}",
            "Completion criteria:",
            criteria or "- none",
            "Validate: "
            + shlex.join(str(part) for part in packet["final_validation_command"]),
        )
    )


def _repository_record(root: Path, record: dict[str, Any]) -> dict[str, Any]:
    return {**record, "absolute_path": str(root / record["path"])}
