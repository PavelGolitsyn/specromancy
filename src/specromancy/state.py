"""Central manifest transition write primitive.

Stage 2 uses this narrow engine for research transitions. Later stages can add
locking and the remaining pipeline guards without allowing phase modules to
write ``run.json`` directly.
"""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import pipeline_contract
from .errors import InvalidTransitionError, ValidationError
from .io import append_json_line, atomic_write_json
from .paths import RepositoryPaths


def apply_transition(
    paths: RepositoryPaths,
    run_id: str,
    manifest: dict[str, Any],
    event: Mapping[str, Any],
    *,
    artifact_name: str | None = None,
    artifact_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one accepted transition and atomically replace its projection."""

    if event.get("event_type") != "transition":
        raise ValidationError(
            "State engine received a non-transition event.",
            hint="Pass an accepted transition event to the state engine.",
        )
    source = event.get("from_status")
    target = event.get("to_status")
    occurred_at = event.get("occurred_at")
    if manifest.get("status") != source:
        raise InvalidTransitionError(
            "Run status changed before the transition could be applied.",
            hint="Reload the run and retry the phase action.",
            details={"expected": source, "actual": manifest.get("status")},
        )
    if not isinstance(target, str) or not isinstance(occurred_at, str):
        raise ValidationError(
            "Transition event is missing its target status or timestamp.",
            hint="Re-run the phase action with a complete version 1 transition event.",
        )
    phase_by_status = pipeline_contract().get("status_current_phase", {})
    if target not in phase_by_status:
        raise ValidationError(
            "Transition event names an unknown target status.",
            hint="Use a target status declared by the packaged pipeline contract.",
        )
    if (artifact_name is None) != (artifact_record is None):
        raise ValidationError(
            "Artifact transition data is incomplete.",
            hint="Provide both the artifact name and validated artifact record.",
        )

    updated = dict(manifest)
    if artifact_name is not None and artifact_record is not None:
        artifacts = dict(updated.get("artifacts", {}))
        artifacts[artifact_name] = dict(artifact_record)
        updated["artifacts"] = artifacts
    updated.update(
        status=target,
        current_phase=phase_by_status[target],
        updated_at=occurred_at,
        last_error=None,
    )
    append_json_line(paths.run_events(run_id), dict(event))
    atomic_write_json(paths.run_manifest(run_id), updated)
    return updated
