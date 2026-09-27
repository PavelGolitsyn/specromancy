"""Creation and integrity checks for approval records."""

from __future__ import annotations

from typing import Any


def build_approval_record(
    *,
    run_id: str,
    phase_id: str,
    visit_number: int,
    reason: str,
    details: str | None,
    artifact_sha256: str,
    pipeline_sha256: str,
    repository_sha256: str,
    outcome: str,
    requested_at: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "phase_id": phase_id,
        "visit_number": visit_number,
        "reason": reason,
        "details": details,
        "artifact_sha256": artifact_sha256,
        "pipeline_sha256": pipeline_sha256,
        "repository_sha256": repository_sha256,
        "outcome": outcome,
        "status": "pending",
        "decision": None,
        "actor": None,
        "requested_at": requested_at,
        "decided_at": None,
    }


def approval_integrity_errors(
    approval: dict[str, Any],
    *,
    artifact_sha256: str,
    pipeline_sha256: str,
    repository_sha256: str | None = None,
) -> list[str]:
    """Return stable mismatch labels for an approval's bound inputs."""

    errors: list[str] = []
    if approval.get("artifact_sha256") != artifact_sha256:
        errors.append("artifact")
    pipeline_changed = approval.get("pipeline_sha256") != pipeline_sha256
    if pipeline_changed:
        errors.append("pipeline")
    # Runs created before repository binding was introduced remain resumable.
    # New approval records always contain this field and therefore protect the
    # repository content that the reviewer actually inspected.
    expected_repository = approval.get("repository_sha256")
    if (
        expected_repository is not None
        and not pipeline_changed
        and expected_repository != repository_sha256
    ):
        errors.append("repository")
    return errors
