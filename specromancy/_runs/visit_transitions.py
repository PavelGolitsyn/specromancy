"""Pure visit decisions over validated records and explicitly collected evidence.

No clocks, artifact reads, locks, revisions, or durable writes belong here.
These internal helpers preserve the distinct RunStore operation contracts.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from .._config.config_models import PipelineConfig
from ..exit_codes import ExitCode
from .run_errors import RunCorruptionError, RunStoreError
from .run_records import (
    InputArtifactRecord, RunRecord, SealedArtifactRecord, VisitRecord, visit_by_number,
)


def transition_limit_block(
    manifest: RunRecord,
    pipeline: PipelineConfig,
    visit: VisitRecord,
    outcome: str,
    transition_target: str | None,
    *,
    timestamp: str,
) -> dict[str, Any] | None:
    """Return a persisted block record before a disallowed loop traversal."""

    phase = pipeline.phase(visit["phase_id"])
    transition = next(
        item for item in phase.transitions if item.outcome == outcome
    )
    if transition.max_traversals is not None:
        traversals = sum(
            item["phase_id"] == phase.id
            and item.get("chosen_outcome") == outcome
            for item in manifest["visits"]
        )
        if traversals >= transition.max_traversals:
            return {
                "reason": "transition-traversal-limit",
                "phase_id": phase.id,
                "visit_number": visit["ordinal"],
                "outcome": outcome,
                "target": transition_target,
                "limit": transition.max_traversals,
                "recorded_at": timestamp,
                "required_action": "new-run",
                "remediation": "start a new run; this pipeline declares no counter-reset approval",
            }
    if transition_target is not None:
        target_phase = pipeline.phase(transition_target)
        if target_phase.max_visits is not None:
            visits = sum(
                item["phase_id"] == transition_target
                for item in manifest["visits"]
            )
            if visits >= target_phase.max_visits:
                return {
                    "reason": "phase-visit-limit",
                    "phase_id": transition_target,
                    "source_phase": phase.id,
                    "visit_number": visit["ordinal"],
                    "outcome": outcome,
                    "limit": target_phase.max_visits,
                    "recorded_at": timestamp,
                    "required_action": "new-run",
                    "remediation": "start a new run; this pipeline declares no counter-reset approval",
                }
    return None


@dataclass(frozen=True)
class Decision:
    """A detached proposed record and event, or an explicit unchanged result."""

    manifest: RunRecord
    event_type: str | None = None
    visit_number: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)


def new_visit(
    *,
    phase_id: str,
    ordinal: int,
    attempt: int,
    status: str,
    inputs: list[InputArtifactRecord],
    output_path: str,
    mutation_policy: str,
    mutation_baseline: Any,
    skill: SealedArtifactRecord,
    template: SealedArtifactRecord | None,
    started_at: str | None,
    deviations: list[Any] | None = None,
) -> VisitRecord:
    """Construct a visit from literal evidence collected at preparation time."""

    if status not in {"pending", "active"}:
        raise ValueError(f"invalid initial visit status: {status!r}")
    return copy.deepcopy({
        "phase_id": phase_id,
        "ordinal": ordinal,
        "attempt": attempt,
        "status": status,
        "inputs": inputs,
        "output": {"path": output_path, "sha256": None},
        "mutation_policy": mutation_policy,
        "mutation_baseline": mutation_baseline,
        "mutation_result": None,
        "validation_checks": [],
        "command_results": [],
        "chosen_outcome": None,
        "transition_target": None,
        "skill": skill,
        "template": template,
        "started_at": started_at,
        "completed_at": None,
        "deviations": list(deviations or []),
    })


def append_visit(manifest: RunRecord, visit: VisitRecord) -> Decision:
    updated = copy.deepcopy(manifest)
    updated["status"] = "active" if visit["status"] == "active" else "awaiting-agent"
    updated["current_visit"] = visit["ordinal"]
    updated["visits"].append(copy.deepcopy(visit))
    return Decision(
        updated,
        "visit-started" if visit["status"] == "active" else "visit-prepared",
        visit["ordinal"],
        {"phase_id": visit["phase_id"], "attempt": visit["attempt"]},
    )


def activation_needed(manifest: RunRecord, visit_number: int) -> bool:
    """Preflight before the store observes the activation clock."""

    if manifest["status"] == "paused":
        raise RunStoreError(
            "paused run must be resumed before its next visit can start",
            diagnostic_code="run-paused",
            details={"run_id": manifest["run_id"], "visit_number": visit_number},
            code=ExitCode.RUN_PAUSED,
        )
    existing = visit_by_number(manifest, visit_number)
    if existing["status"] == "active":
        return False
    if existing["status"] != "pending":
        raise RunStoreError(
            f"visit {visit_number} cannot be activated from {existing['status']}",
            diagnostic_code="illegal-visit-status",
            details={"visit_number": visit_number, "status": existing["status"],
                     "expected": "pending"},
            code=ExitCode.ILLEGAL_TRANSITION,
        )
    return True


def activate_visit(
    manifest: RunRecord, visit_number: int, *,
    mutation_baseline: Any, started_at: str | None,
) -> Decision:
    updated = copy.deepcopy(manifest)
    if not activation_needed(manifest, visit_number):
        return Decision(updated)
    visit = visit_by_number(updated, visit_number)
    visit["status"] = "active"
    visit["mutation_baseline"] = copy.deepcopy(mutation_baseline)
    visit["started_at"] = started_at
    updated["status"] = "active"
    return Decision(updated, "visit-activated", visit_number,
                    {"phase_id": visit["phase_id"]})


def require_incomplete(manifest: RunRecord, visit_number: int) -> None:
    if visit_by_number(manifest, visit_number)["status"] == "completed":
        raise RunStoreError(
            f"visit {visit_number} is already completed",
            diagnostic_code="visit-already-completed",
            details={"visit_number": visit_number},
            code=ExitCode.ILLEGAL_TRANSITION,
        )


def transition_needed(
    manifest: RunRecord, visit_number: int, outcome: str, target: str | None,
) -> bool:
    """Check retry/status before reading output or observing clocks."""

    existing = visit_by_number(manifest, visit_number)
    if existing["status"] == "completed":
        if (existing["chosen_outcome"] == outcome
                and existing["transition_target"] == target):
            return False
        raise RunStoreError(
            f"visit {visit_number} already completed with another transition",
            diagnostic_code="visit-already-completed",
            details={"visit_number": visit_number},
            code=ExitCode.ILLEGAL_TRANSITION,
        )
    if existing["status"] not in {"active", "awaiting-approval"}:
        raise RunStoreError(
            f"visit {visit_number} cannot complete from {existing['status']}",
            diagnostic_code="illegal-visit-status",
            details={"visit_number": visit_number, "status": existing["status"]},
            code=ExitCode.ILLEGAL_TRANSITION,
        )
    return True


def _record_evidence(
    manifest: RunRecord, visit: VisitRecord, *, mutation_result: Any,
    validation_checks: list[Any] | None, command_results: list[Any] | None,
) -> None:
    visit["mutation_result"] = copy.deepcopy(mutation_result)
    visit["validation_checks"] = copy.deepcopy(list(validation_checks or []))
    visit["command_results"] = copy.deepcopy(list(command_results or []))
    if isinstance(mutation_result, dict) and isinstance(mutation_result.get("head"), dict):
        manifest["git"]["head"] = copy.deepcopy(mutation_result["head"])


def seal_visit(
    manifest: RunRecord, visit_number: int, *, output_sha256: str,
    outcome: str | None, transition_target: str | None, completed_at: str,
    mutation_result: Any = None, validation_checks: list[Any] | None = None,
    command_results: list[Any] | None = None, deviations: list[Any] | None = None,
) -> RunRecord:
    """Propose a sealed record for completion or successor input resolution.

    This intermediate record is never committed by a graph transition: the
    store gathers successor evidence under the same lock, then finishes it.
    """

    require_incomplete(manifest, visit_number)
    updated = copy.deepcopy(manifest)
    visit = visit_by_number(updated, visit_number)
    visit["status"] = "completed"
    visit["output"]["sha256"] = output_sha256
    _record_evidence(updated, visit, mutation_result=mutation_result,
                     validation_checks=validation_checks, command_results=command_results)
    visit["chosen_outcome"] = outcome
    visit["transition_target"] = transition_target
    visit["completed_at"] = completed_at
    if deviations is not None:
        visit["deviations"] = copy.deepcopy(list(deviations))
    return updated


def completion_decision(sealed: RunRecord, visit_number: int) -> Decision:
    visit = visit_by_number(sealed, visit_number)
    return Decision(copy.deepcopy(sealed), "visit-completed", visit_number,
                    {"phase_id": visit["phase_id"], "outcome": visit["chosen_outcome"]})


def blocked_transition(
    manifest: RunRecord, visit_number: int, reason: dict[str, Any], *,
    mutation_result: Any = None, validation_checks: list[Any] | None = None,
    command_results: list[Any] | None = None,
) -> Decision:
    updated = copy.deepcopy(manifest)
    visit = visit_by_number(updated, visit_number)
    visit["status"] = "blocked"
    _record_evidence(updated, visit, mutation_result=mutation_result,
                     validation_checks=validation_checks, command_results=command_results)
    updated["status"] = "blocked"
    updated["block_reason"] = copy.deepcopy(reason)
    return Decision(updated, "loop-limit-exceeded", visit_number, copy.deepcopy(reason))


def finish_transition(
    sealed: RunRecord, visit_number: int, *, next_visit: VisitRecord | None,
    pause: bool, terminal_result: Any = None,
) -> Decision:
    updated = copy.deepcopy(sealed)
    visit = visit_by_number(updated, visit_number)
    if next_visit is None:
        updated["status"] = "completed"
        updated["terminal_result"] = copy.deepcopy(
            terminal_result if terminal_result is not None
            else {"outcome": visit["chosen_outcome"], "visit_number": visit_number}
        )
    else:
        updated["visits"].append(copy.deepcopy(next_visit))
        updated["current_visit"] = next_visit["ordinal"]
        updated["status"] = "paused" if pause else "awaiting-agent"
    return Decision(updated, "visit-transitioned", visit_number, {
        "phase_id": visit["phase_id"], "outcome": visit["chosen_outcome"],
        "target": visit["transition_target"], "paused": pause,
        "next_visit": next_visit["ordinal"] if next_visit is not None else None,
    })


def resume_paused(manifest: RunRecord) -> Decision:
    updated = copy.deepcopy(manifest)
    if manifest["status"] != "paused":
        return Decision(updated)
    visit_number = manifest["current_visit"]
    if visit_number is None:
        raise RunCorruptionError("paused run has no current visit", run_id=manifest["run_id"])
    current = visit_by_number(manifest, visit_number)
    if current["status"] != "pending":
        raise RunCorruptionError(
            "paused run does not point to a pending visit", run_id=manifest["run_id"]
        )
    updated["status"] = "awaiting-agent"
    return Decision(updated, "run-resumed", visit_number, {"phase_id": current["phase_id"]})
