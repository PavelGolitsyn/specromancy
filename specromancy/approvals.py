"""Pure approval selectors, integrity checks, and detached state changes.

Callers supply timestamps and retain the durable store mutation boundary.
"""

from __future__ import annotations

import copy
from typing import Any

from .run_records import ApprovalRecord, RunRecord, current_visit, latest_approval


def build_approval_record(
    *,
    run_id: str,
    phase_id: str,
    visit_number: int,
    reason: str,
    details: str | None,
    artifact_sha256: str,
    pipeline_sha256: str,
    outcome: str,
    requested_at: str,
) -> ApprovalRecord:
    return {
        "run_id": run_id,
        "phase_id": phase_id,
        "visit_number": visit_number,
        "reason": reason,
        "details": details,
        "artifact_sha256": artifact_sha256,
        "pipeline_sha256": pipeline_sha256,
        "outcome": outcome,
        "status": "pending",
        "decision": None,
        "actor": None,
        "requested_at": requested_at,
        "decided_at": None,
    }


def approval_integrity_errors(
    approval: ApprovalRecord, *, artifact_sha256: str, pipeline_sha256: str
) -> list[str]:
    """Return stable mismatch labels for an approval's bound inputs."""

    errors: list[str] = []
    if approval.get("artifact_sha256") != artifact_sha256:
        errors.append("artifact")
    if approval.get("pipeline_sha256") != pipeline_sha256:
        errors.append("pipeline")
    return errors


def pending_approval(manifest: RunRecord, visit_number: int) -> ApprovalRecord | None:
    return latest_approval(manifest, "pending", visit_number=visit_number)


def approved_record(manifest: RunRecord, visit_number: int) -> ApprovalRecord | None:
    return latest_approval(manifest, "approved", visit_number=visit_number)


def approved_for_phase(manifest: RunRecord, phase_id: str) -> ApprovalRecord | None:
    return next(
        (
            item
            for item in reversed(manifest["approvals"])
            if item.get("phase_id") == phase_id and item.get("status") == "approved"
        ),
        None,
    )


def requested_state(
    manifest: RunRecord,
    approval: ApprovalRecord,
    *,
    validation_checks: list[dict[str, Any]],
    command_results: list[dict[str, Any]],
    mutation_result: dict[str, Any] | None,
) -> RunRecord:
    """Return a detached pending state using already collected evidence."""

    updated = copy.deepcopy(manifest)
    current = current_visit(updated)
    assert current is not None
    current["status"] = "awaiting-approval"
    current["validation_checks"] = copy.deepcopy(validation_checks)
    current["mutation_result"] = copy.deepcopy(mutation_result)
    current["command_results"] = copy.deepcopy(command_results)
    updated["status"] = "awaiting-approval"
    updated["approvals"].append(copy.deepcopy(approval))
    return updated


def granted_state(
    manifest: RunRecord, visit_number: int, *, decided_at: str
) -> RunRecord:
    """Grant the latest pending record without advancing or revalidating."""

    updated = copy.deepcopy(manifest)
    record = pending_approval(updated, visit_number)
    assert record is not None
    record["status"] = "approved"
    record["decision"] = "approved"
    record["actor"] = "user"
    record["decided_at"] = decided_at
    return updated


def invalidated_state(
    manifest: RunRecord,
    visit_number: int,
    approval: ApprovalRecord,
    *,
    decided_at: str,
) -> RunRecord:
    """Invalidate the identified request, retaining its binding and audit data."""

    updated = copy.deepcopy(manifest)
    record = next(
        item
        for item in updated["approvals"]
        if item.get("visit_number") == visit_number
        and item.get("requested_at") == approval.get("requested_at")
    )
    record["status"] = "stale"
    record["decision"] = "invalidated"
    record["actor"] = "system"
    record["decided_at"] = decided_at
    current = current_visit(updated)
    assert current is not None
    current["status"] = "awaiting-approval"
    updated["status"] = "awaiting-approval"
    return updated
