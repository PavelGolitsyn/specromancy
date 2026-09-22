"""Contract-driven, locked manifest transition engine."""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import pipeline_contract
from .errors import InvalidTransitionError, ValidationError
from .events import append_event
from .io import atomic_write_json
from .locking import RunLock
from .paths import RepositoryPaths
from .run import load_manifest


def _transition_contract(transition_id: str) -> Mapping[str, Any]:
    transitions = pipeline_contract().get("transitions", [])
    for transition in transitions:
        if isinstance(transition, dict) and transition.get("id") == transition_id:
            return transition
    raise ValidationError(
        "State engine received an unknown transition ID.",
        details={"transition_id": transition_id},
    )


def apply_transition(
    paths: RepositoryPaths,
    run_id: str,
    manifest: dict[str, Any],
    event: Mapping[str, Any],
    *,
    artifact_name: str | None = None,
    artifact_record: Mapping[str, Any] | None = None,
    manifest_updates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate, append, and project one state transition under the run lock."""

    if event.get("event_type") != "transition":
        raise ValidationError(
            "State engine received a non-transition event.",
            hint="Pass an accepted transition event to the state engine.",
        )
    transition_id = event.get("transition_id")
    if not isinstance(transition_id, str):
        raise ValidationError("Transition event is missing its transition ID.")
    contract = _transition_contract(transition_id)
    source = event.get("from_status")
    target = event.get("to_status")
    occurred_at = event.get("occurred_at")
    if not isinstance(target, str) or not isinstance(occurred_at, str):
        raise ValidationError(
            "Transition event is missing its target status or timestamp.",
            hint="Re-run the phase action with a complete version 1 transition event.",
        )
    allowed_sources = (
        [contract.get("from")]
        if "from" in contract
        else contract.get("allowed_from", [])
    )
    if (
        source not in allowed_sources
        or target != contract.get("to")
        or event.get("action") != contract.get("action")
        or event.get("phase") != contract.get("phase")
    ):
        raise ValidationError(
            "Transition event does not match the packaged state contract.",
            details={"transition_id": transition_id},
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

    with RunLock(paths, run_id, f"transition:{transition_id}"):
        current = load_manifest(paths, run_id)
        if current.get("status") != source:
            raise InvalidTransitionError(
                "Run status changed before the transition could be applied.",
                hint="Reload the run and retry the phase action.",
                details={"expected": source, "actual": current.get("status")},
            )
        # A stale caller must not overwrite other non-status manifest updates.
        if current != manifest:
            raise InvalidTransitionError(
                "Run manifest changed before the transition could be applied.",
                hint="Reload the run and retry the phase action.",
            )
        updated = dict(current)
        if manifest_updates is not None:
            protected = {"status", "current_phase", "updated_at", "last_error"}
            overlap = protected.intersection(manifest_updates)
            if overlap:
                raise ValidationError(
                    "Transition manifest updates contain state-engine-owned fields.",
                    hint="Pass status projection fields through the transition event only.",
                    details={"fields": sorted(overlap)},
                )
            updated.update(manifest_updates)
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
        append_event(paths.run_events(run_id), dict(event))
        atomic_write_json(paths.run_manifest(run_id), updated)
        return updated
