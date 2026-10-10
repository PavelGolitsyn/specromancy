"""Pure approval selectors, integrity checks, and detached state changes.

Callers supply timestamps and observations; decisions run against locked state.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from .engine_errors import EngineError
from .exit_codes import ExitCode
from .run_records import ApprovalRecord, RunRecord, VisitRecord, current_visit, latest_approval


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


IDENTITY_FIELDS = (
    "run_id", "visit_number", "phase_id", "reason", "details", "requested_at",
    "outcome", "pipeline_sha256", "artifact_sha256",
)


@dataclass
class ApprovalDecision:
    """A detached approval result; absent event means no durable change."""

    manifest: RunRecord
    approval: ApprovalRecord
    disposition: str
    event_type: str | None = None
    visit_number: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)


def conflict(observed: ApprovalRecord) -> EngineError:
    return EngineError(
        ExitCode.ILLEGAL_TRANSITION,
        "approval state changed before the command could be applied",
        "approval-state-changed",
        run_id=observed.get("run_id"), phase=observed.get("phase_id"),
        visit_number=observed.get("visit_number"),
    )


def require_binding(manifest: RunRecord, observed: ApprovalRecord) -> VisitRecord:
    """Reject incomplete identities or a mismatched containing run/visit."""

    if any(key not in observed for key in IDENTITY_FIELDS):
        raise conflict(observed)
    visits = [v for v in manifest["visits"]
              if v["ordinal"] == observed["visit_number"]]
    if (manifest["run_id"] != observed["run_id"] or len(visits) != 1
            or visits[0]["phase_id"] != observed["phase_id"]):
        raise conflict(observed)
    return visits[0]


def _matches(
    record: ApprovalRecord, observed: ApprovalRecord, *, creation: bool = False,
) -> bool:
    return all(key in record and record[key] == observed[key]
               for key in IDENTITY_FIELDS if not (creation and key == "requested_at"))


def _eligible(
    manifest: RunRecord, visit: VisitRecord, *, creation: bool = False,
) -> bool:
    statuses = ("active", "awaiting-approval") if creation else ("awaiting-approval",)
    return (manifest["current_visit"] == visit["ordinal"]
            and manifest["status"] in statuses and visit["status"] in statuses)


def request_decision(
    manifest: RunRecord, approval: ApprovalRecord, *,
    validation_checks: list[dict[str, Any]], command_results: list[dict[str, Any]],
    mutation_result: dict[str, Any] | None,
) -> ApprovalDecision:
    """Create once, or reuse the winning pending request without new evidence."""

    visit = require_binding(manifest, approval)
    if not _eligible(manifest, visit, creation=True):
        raise conflict(approval)
    records = [a for a in manifest["approvals"]
               if a.get("visit_number") == visit["ordinal"]
               and a.get("status") in ("pending", "approved")]
    if records:
        if (len(records) != 1 or records[0].get("status") != "pending"
                or any(key not in records[0] for key in IDENTITY_FIELDS)
                or not _matches(records[0], approval, creation=True)):
            raise conflict(approval)
        return ApprovalDecision(copy.deepcopy(manifest), copy.deepcopy(records[0]), "pending")
    updated = requested_state(
        manifest, approval, validation_checks=validation_checks,
        command_results=command_results, mutation_result=mutation_result,
    )
    return ApprovalDecision(
        updated, copy.deepcopy(approval), "requested", "approval-requested",
        visit["ordinal"], {"reason": approval["reason"], "outcome": approval["outcome"]},
    )


def _identified(
    manifest: RunRecord, observed: ApprovalRecord,
) -> tuple[VisitRecord, ApprovalRecord]:
    visit = require_binding(manifest, observed)
    records = [a for a in manifest["approvals"] if _matches(a, observed)]
    # A replacement on the same visit must not inherit an earlier decision.
    competing = [a for a in manifest["approvals"]
                 if a.get("visit_number") == visit["ordinal"]
                 and a.get("status") in ("pending", "approved")
                 and not _matches(a, observed)]
    if len(records) != 1 or competing:
        raise conflict(observed)
    record = records[0]
    if any(a.get("visit_number") == visit["ordinal"]
           for a in manifest["approvals"][manifest["approvals"].index(record) + 1:]):
        raise conflict(observed)
    return visit, record


def grant_decision(
    manifest: RunRecord, observed: ApprovalRecord, *,
    transition_target: str | None, decided_at: str | None,
) -> ApprovalDecision:
    """Grant exactly the observed request; None permits only existing grants."""

    updated = copy.deepcopy(manifest)
    visit, record = _identified(updated, observed)
    if record.get("status") == "approved" and visit["status"] == "completed":
        if (visit["chosen_outcome"] != record["outcome"]
                or visit["transition_target"] != transition_target):
            raise conflict(observed)
        return ApprovalDecision(updated, copy.deepcopy(record), "completed")
    if not _eligible(updated, visit):
        raise conflict(observed)
    if record.get("status") == "approved":
        return ApprovalDecision(updated, copy.deepcopy(record), "granted")
    if record.get("status") != "pending" or decided_at is None:
        raise conflict(observed)
    record.update(status="approved", decision="approved", actor="user", decided_at=decided_at)
    return ApprovalDecision(
        updated, copy.deepcopy(record), "granted", "approval-granted",
        visit["ordinal"], {"phase_id": visit["phase_id"], "actor": "user"},
    )


def invalidate_decision(
    manifest: RunRecord, observed: ApprovalRecord, *, decided_at: str,
    mismatches: list[str],
) -> ApprovalDecision:
    """Invalidate only the eligible observed request, including stale retries."""

    updated = copy.deepcopy(manifest)
    visit, record = _identified(updated, observed)
    if not _eligible(updated, visit):
        raise conflict(observed)
    if record.get("status") == "stale" and record.get("decision") == "invalidated":
        return ApprovalDecision(updated, copy.deepcopy(record), "stale")
    if record.get("status") not in ("pending", "approved"):
        raise conflict(observed)
    record.update(status="stale", decision="invalidated", actor="system", decided_at=decided_at)
    return ApprovalDecision(
        updated, copy.deepcopy(record), "stale", "approval-invalidated",
        visit["ordinal"], {"mismatches": list(mismatches)},
    )
