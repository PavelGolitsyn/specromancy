"""Creation and integrity checks for approval records."""

from __future__ import annotations

from .run_records import ApprovalRecord


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
