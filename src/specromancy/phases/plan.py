"""Plan lifecycle, validation, approval binding, and revocation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..artifacts.plan import PlanArtifact, validate_plan
from ..clock import Clock, SystemClock
from ..errors import (
    ApprovalRequiredError,
    InvalidInputError,
    InvalidTransitionError,
    SpecromancyError,
    ValidationError,
)
from ..io import append_json_line, read_text, sha256_file
from ..locking import locked_run
from ..paths import RepositoryPaths
from ..state import apply_transition
from .research import (
    _append_failure,
    _event,
    _load_manifest,
    _request_digest,
    _scope_snapshot,
    _timestamp,
    validate_research_file,
)


@dataclass(frozen=True)
class PlanPhaseResult:
    run_id: str
    status: str
    artifact_path: str
    artifact_sha256: str | None = None
    replayed: bool = False


@dataclass(frozen=True)
class PlanApprovalResult:
    run_id: str
    status: str
    approver: str
    artifact_sha256: str
    approved_at: str
    note: str | None = None
    replayed: bool = False


@dataclass(frozen=True)
class PlanRevocationResult:
    run_id: str
    status: str
    revoked_by: str
    revoked_at: str
    reason: str


def _research_digest(
    paths: RepositoryPaths, run_id: str, manifest: Mapping[str, Any]
) -> tuple[str, tuple[str, ...]]:
    record = manifest.get("artifacts", {}).get("research")
    if not isinstance(record, dict):
        raise ValidationError(
            "The run has no completed research artifact.",
            hint="Complete and validate research before starting a plan.",
        )
    target = paths.run_artifact(run_id, "research.md")
    if not target.is_file():
        raise ValidationError(
            "The recorded research artifact is missing.",
            hint="Restore the validated research.md before planning.",
            path=paths.serialize(target),
        )
    artifact = validate_research_file(paths.root, run_id, record_event=False)
    digest = sha256_file(target)
    request_digest = _request_digest(paths, run_id, manifest)
    if record.get("sha256") != digest or record.get("bindings") != {
        "request": request_digest
    }:
        raise ValidationError(
            "Research is stale or no longer matches its recorded inputs.",
            hint="Restore the accepted research artifact or complete fresh research.",
        )
    return digest, tuple(row.evidence_id for row in artifact.evidence)


def _requirements(manifest: Mapping[str, Any]) -> list[Mapping[str, object]]:
    requirements = manifest.get("requirements")
    if not isinstance(requirements, list) or not all(
        isinstance(item, dict) for item in requirements
    ):
        raise ValidationError(
            "Run requirements are missing or malformed.",
            hint="Reinitialize the request requirements before planning.",
        )
    return requirements


def _active_approvals(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    approvals = manifest.get("approvals")
    if not isinstance(approvals, list):
        raise ValidationError(
            "Run approvals are malformed.",
            hint="Repair run.json from its append-only event history.",
        )
    return [
        approval
        for approval in approvals
        if isinstance(approval, dict)
        and approval.get("subject") == "plan"
        and approval.get("status") == "active"
    ]


def _plan_start_snapshot(paths: RepositoryPaths, run_id: str) -> str:
    events = paths.run_events(run_id)
    if not events.is_file():
        raise ValidationError(
            "Plan start event is missing.",
            hint="Restart planning from a valid research-ready run.",
        )
    latest: str | None = None
    try:
        lines = events.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValidationError("Run event log could not be read.") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "Run event log contains malformed JSON.",
                hint=f"Repair events.jsonl line {line_number} before completing the plan.",
            ) from exc
        if (
            isinstance(event, dict)
            and event.get("event_type") == "transition"
            and event.get("transition_id") in {"plan.start", "plan.restart"}
            and isinstance(event.get("write_scope_snapshot"), str)
        ):
            latest = event["write_scope_snapshot"]
    if latest is None:
        raise ValidationError(
            "Plan start event has no write-scope snapshot.",
            hint="Restart planning from a valid research-ready run.",
        )
    return latest


def plan_artifact_path(repository_root: str | Path, run_id: str) -> Path:
    paths = RepositoryPaths(Path(repository_root))
    _load_manifest(paths, run_id)
    return paths.run_artifact(run_id, "plan.md")


@locked_run("validate_plan")
def validate_plan_file(
    repository_root: str | Path,
    run_id: str,
    *,
    record_event: bool = True,
    clock: Clock | None = None,
    implementation_context: bool = False,
) -> PlanArtifact:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    manifest = _load_manifest(paths, run_id)
    artifact_path = paths.run_artifact(run_id, "plan.md")
    try:
        _, evidence_ids = _research_digest(paths, run_id, manifest)
        if not artifact_path.is_file():
            raise ValidationError(
                "Plan artifact is missing.",
                hint="Create plan.md from the canonical plan template and retry.",
                path=paths.serialize(artifact_path),
            )
        artifact = validate_plan(
            read_text(artifact_path),
            paths.root,
            run_id,
            _requirements(manifest),
            evidence_ids,
            implementation_context=implementation_context,
        )
    except SpecromancyError as exc:
        if record_event:
            _append_failure(paths, run_id, exc, action="validate_plan", clock=clock)
        raise
    if record_event:
        append_json_line(
            paths.run_events(run_id),
            _event(
                event_type="validation",
                run_id=run_id,
                occurred_at=_timestamp(clock),
                phase="plan",
                action="validate_plan",
                outcome="passed",
                artifact="plan",
                artifact_sha256=sha256_file(artifact_path),
            ),
        )
    return artifact


@locked_run("start_plan")
def start_plan(
    repository_root: str | Path,
    run_id: str,
    *,
    clock: Clock | None = None,
) -> PlanPhaseResult:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    manifest = _load_manifest(paths, run_id)
    status = manifest.get("status")
    if status not in {"research_ready", "plan_ready"}:
        error = InvalidTransitionError(
            f"Plan cannot start while the run is '{status}'.",
            hint="Start planning from research_ready, or reopen an unapproved plan_ready run.",
            details={"status": status},
        )
        _append_failure(paths, run_id, error, action="start_plan", clock=clock)
        raise error
    try:
        if status == "plan_ready" and _active_approvals(manifest):
            raise ApprovalRequiredError(
                "An active plan approval must be revoked before replanning.",
                hint="Run approval revoke for the current plan before reopening it.",
            )
        _research_digest(paths, run_id, manifest)
        snapshot = _scope_snapshot(paths, run_id)
    except SpecromancyError as exc:
        _append_failure(paths, run_id, exc, action="start_plan", clock=clock)
        raise
    now = _timestamp(clock)
    transition_id = "plan.start" if status == "research_ready" else "plan.restart"
    event = _event(
        event_type="transition",
        run_id=run_id,
        occurred_at=now,
        phase="plan",
        action="start_plan",
        transition_id=transition_id,
        from_status=status,
        to_status="plan_in_progress",
        write_scope_snapshot=snapshot,
    )
    apply_transition(paths, run_id, manifest, event)
    return PlanPhaseResult(
        run_id=run_id,
        status="plan_in_progress",
        artifact_path=paths.serialize(paths.run_artifact(run_id, "plan.md")),
    )


@locked_run("complete_plan")
def complete_plan(
    repository_root: str | Path,
    run_id: str,
    *,
    clock: Clock | None = None,
) -> PlanPhaseResult:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    manifest = _load_manifest(paths, run_id)
    artifact_path = paths.run_artifact(run_id, "plan.md")
    if manifest.get("status") == "plan_ready":
        validate_plan_file(paths.root, run_id, record_event=False, clock=clock)
        digest = sha256_file(artifact_path)
        research_digest, _ = _research_digest(paths, run_id, manifest)
        record = manifest.get("artifacts", {}).get("plan")
        if (
            isinstance(record, dict)
            and record.get("sha256") == digest
            and record.get("bindings") == {"research": research_digest}
        ):
            return PlanPhaseResult(
                run_id=run_id,
                status="plan_ready",
                artifact_path=paths.serialize(artifact_path),
                artifact_sha256=digest,
                replayed=True,
            )
        error = ValidationError(
            "Completed plan no longer matches its recorded digest or research binding.",
            hint="Restore the accepted plan or reopen planning before completing it again.",
        )
        _append_failure(paths, run_id, error, action="complete_plan", clock=clock)
        raise error
    if manifest.get("status") != "plan_in_progress":
        error = InvalidTransitionError(
            f"Plan cannot complete while the run is '{manifest.get('status')}'.",
            hint="Complete the plan only after a successful plan start.",
            details={"status": manifest.get("status")},
        )
        _append_failure(paths, run_id, error, action="complete_plan", clock=clock)
        raise error
    try:
        validate_plan_file(paths.root, run_id, clock=clock)
        start_snapshot = _plan_start_snapshot(paths, run_id)
        current_snapshot = _scope_snapshot(paths, run_id)
        if current_snapshot != start_snapshot:
            raise ValidationError(
                "Repository files outside the active run changed during planning.",
                hint="Restore those changes or restart planning from the new repository state.",
            )
        research_digest, _ = _research_digest(paths, run_id, manifest)
    except SpecromancyError as exc:
        _append_failure(paths, run_id, exc, action="complete_plan", clock=clock)
        raise
    digest = sha256_file(artifact_path)
    now = _timestamp(clock)
    event = _event(
        event_type="transition",
        run_id=run_id,
        occurred_at=now,
        phase="plan",
        action="complete_plan",
        transition_id="plan.complete",
        from_status="plan_in_progress",
        to_status="plan_ready",
        artifact="plan",
        artifact_sha256=digest,
        bindings={"research": research_digest},
    )
    record = {
        "path": paths.serialize(artifact_path),
        "sha256": digest,
        "validated_at": now,
        "schema_version": "1",
        "bindings": {"research": research_digest},
    }
    apply_transition(
        paths,
        run_id,
        manifest,
        event,
        artifact_name="plan",
        artifact_record=record,
    )
    return PlanPhaseResult(
        run_id=run_id,
        status="plan_ready",
        artifact_path=paths.serialize(artifact_path),
        artifact_sha256=digest,
    )


def _current_recorded_plan(
    paths: RepositoryPaths,
    run_id: str,
    manifest: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any]]:
    target = paths.run_artifact(run_id, "plan.md")
    if not target.is_file():
        raise ApprovalRequiredError(
            "The completed plan artifact is missing.",
            hint="Restore the approved plan or revoke approval and replan.",
        )
    digest = sha256_file(target)
    research_digest, _ = _research_digest(paths, run_id, manifest)
    record = manifest.get("artifacts", {}).get("plan")
    if (
        not isinstance(record, dict)
        or record.get("sha256") != digest
        or record.get("bindings") != {"research": research_digest}
    ):
        raise ApprovalRequiredError(
            "The current plan does not match the completed plan record.",
            hint="Restore the completed plan, or reopen and complete planning before approval.",
        )
    validate_plan_file(paths.root, run_id, record_event=False)
    return digest, record


@locked_run("approve_plan")
def approve_plan(
    repository_root: str | Path,
    run_id: str,
    *,
    approver: str,
    note: str | None = None,
    clock: Clock | None = None,
) -> PlanApprovalResult:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    manifest = _load_manifest(paths, run_id)
    identity = approver.strip()
    if not identity or len(identity) > 200:
        raise InvalidInputError(
            "Plan approver identity must contain 1 to 200 characters.",
            hint="Pass a concise auditable identity with --by.",
        )
    normalized_note = note.strip() if note is not None else None
    if normalized_note == "":
        normalized_note = None
    if normalized_note is not None and len(normalized_note) > 1000:
        raise InvalidInputError("Plan approval note cannot exceed 1000 characters.")
    status = manifest.get("status")
    if status not in {"plan_ready", "plan_approved"}:
        error = InvalidTransitionError(
            f"Plan cannot be approved while the run is '{status}'.",
            hint="Complete and validate the plan before approving it.",
            details={"status": status},
        )
        _append_failure(paths, run_id, error, action="approve_plan", clock=clock)
        raise error
    try:
        digest, _ = _current_recorded_plan(paths, run_id, manifest)
        active = _active_approvals(manifest)
        if len(active) > 1:
            raise ValidationError(
                "Run contains more than one active plan approval.",
                hint="Repair the approval projection from events before continuing.",
            )
        if status == "plan_approved":
            if (
                len(active) == 1
                and active[0].get("artifact_sha256") == digest
                and active[0].get("approver") == identity
            ):
                return PlanApprovalResult(
                    run_id=run_id,
                    status="plan_approved",
                    approver=identity,
                    artifact_sha256=digest,
                    approved_at=str(active[0]["approved_at"]),
                    note=active[0].get("note"),
                    replayed=True,
                )
            raise ApprovalRequiredError(
                "The existing plan approval cannot be reused for these inputs.",
                hint="Use the original approval inputs, or revoke approval before replanning.",
            )
        if active:
            raise ValidationError(
                "A plan-ready run unexpectedly has an active approval.",
                hint="Repair or revoke the inconsistent approval before continuing.",
            )
    except SpecromancyError as exc:
        _append_failure(paths, run_id, exc, action="approve_plan", clock=clock)
        raise
    now = _timestamp(clock)
    approval = {
        "subject": "plan",
        "approver": identity,
        "approved_at": now,
        "artifact_sha256": digest,
        "note": normalized_note,
        "status": "active",
        "revoked_at": None,
        "revoked_by": None,
        "revocation_reason": None,
    }
    approvals = [*manifest.get("approvals", []), approval]
    event = _event(
        event_type="transition",
        run_id=run_id,
        occurred_at=now,
        phase="approval",
        action="approve_plan",
        transition_id="plan.approve",
        from_status="plan_ready",
        to_status="plan_approved",
        artifact="plan",
        artifact_sha256=digest,
        approver=identity,
        note=normalized_note,
    )
    apply_transition(
        paths,
        run_id,
        manifest,
        event,
        manifest_updates={"approvals": approvals},
    )
    return PlanApprovalResult(
        run_id=run_id,
        status="plan_approved",
        approver=identity,
        artifact_sha256=digest,
        approved_at=now,
        note=normalized_note,
    )


@locked_run("revoke_plan_approval")
def revoke_plan_approval(
    repository_root: str | Path,
    run_id: str,
    *,
    revoked_by: str,
    reason: str,
    clock: Clock | None = None,
) -> PlanRevocationResult:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    manifest = _load_manifest(paths, run_id)
    actor = revoked_by.strip()
    explanation = reason.strip()
    if not actor or len(actor) > 200 or not explanation or len(explanation) > 1000:
        raise InvalidInputError(
            "Approval revocation requires a valid actor and nonempty reason.",
            hint="Pass --by with 1-200 characters and --reason with 1-1000 characters.",
        )
    if manifest.get("status") != "plan_approved":
        error = InvalidTransitionError(
            f"Plan approval cannot be revoked while the run is '{manifest.get('status')}'.",
            hint="Revoke only an active approval on a plan_approved run.",
        )
        _append_failure(paths, run_id, error, action="revoke_plan_approval", clock=clock)
        raise error
    active = _active_approvals(manifest)
    if len(active) != 1:
        error = ValidationError(
            "The run does not contain exactly one active plan approval.",
            hint="Repair the approval projection from events before revoking it.",
        )
        _append_failure(paths, run_id, error, action="revoke_plan_approval", clock=clock)
        raise error
    now = _timestamp(clock)
    target = active[0]
    approvals: list[dict[str, Any]] = []
    for approval in manifest.get("approvals", []):
        replacement = dict(approval)
        if approval is target:
            replacement.update(
                status="revoked",
                revoked_at=now,
                revoked_by=actor,
                revocation_reason=explanation,
            )
        approvals.append(replacement)
    event = _event(
        event_type="transition",
        run_id=run_id,
        occurred_at=now,
        phase="approval",
        action="revoke_plan_approval",
        transition_id="plan.revoke_approval",
        from_status="plan_approved",
        to_status="plan_ready",
        artifact="plan",
        artifact_sha256=target.get("artifact_sha256"),
        revoked_by=actor,
        reason=explanation,
    )
    apply_transition(
        paths,
        run_id,
        manifest,
        event,
        manifest_updates={"approvals": approvals},
    )
    return PlanRevocationResult(
        run_id=run_id,
        status="plan_ready",
        revoked_by=actor,
        revoked_at=now,
        reason=explanation,
    )


def require_current_plan_approval(
    repository_root: str | Path, run_id: str
) -> Mapping[str, Any]:
    """Return the active approval or reject stale/missing approval before implementation."""

    paths = RepositoryPaths(Path(repository_root))
    manifest = _load_manifest(paths, run_id)
    if manifest.get("status") != "plan_approved":
        raise ApprovalRequiredError(
            "Implementation requires a plan_approved run.",
            hint="Complete and explicitly approve the current plan first.",
        )
    digest, _ = _current_recorded_plan(paths, run_id, manifest)
    active = _active_approvals(manifest)
    if len(active) != 1 or active[0].get("artifact_sha256") != digest:
        raise ApprovalRequiredError(
            "The active approval does not match the current plan digest.",
            hint="Restore the approved plan or revoke, replan, and approve the new digest.",
        )
    return active[0]


check_plan_approval = require_current_plan_approval
validate_plan_approval = require_current_plan_approval
ensure_plan_approval_current = require_current_plan_approval
approve = approve_plan
revoke_approval = revoke_plan_approval
start = start_plan
complete = complete_plan
