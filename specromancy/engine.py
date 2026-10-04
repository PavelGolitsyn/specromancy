"""Generic, deterministic state-machine execution."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import responses
from .approvals import (
    approval_integrity_errors, approved_for_phase, approved_record,
    build_approval_record, granted_state, invalidated_state, pending_approval,
    requested_state,
)
from .artifacts import ArtifactError, artifact_record, verify_manifest_artifacts
from .config_models import PhaseConfig, PipelineConfig
from .engine_errors import EngineError
from .errors import UsageError
from .exit_codes import ExitCode
from .git import GitError, capture_repository_snapshot
from .provenance import observe_provenance, pipeline_identity, pipeline_matches
from .responses import RESPONSE_SCHEMA_VERSION  # Backward-compatible re-export.
from .run_store import RunStore, format_timestamp, utc_now
from .run_records import (
    ApprovalRecord, RunRecord, VisitRecord, current_visit,
)
from .validation_service import ValidationResult, perform_validation


class Engine:
    """Advance runs using only configured outcomes and persisted state."""

    def __init__(
        self,
        pipeline: PipelineConfig,
        store: RunStore | None = None,
        *,
        command_fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.store = store or RunStore(pipeline.repository_root)
        self._command_fault_injector = command_fault_injector

    def initialize(self, description: str) -> dict[str, Any]:
        if not description.strip():
            raise UsageError("DESCRIPTION must not be empty")
        try:
            git = capture_repository_snapshot(
                self.pipeline.repository_root,
                allow_non_git=self.pipeline.allow_non_git,
            )
        except GitError as exc:
            raise EngineError(
                ExitCode.INVALID_PIPELINE,
                exc.message,
                exc.diagnostic_code,
                **exc.details,
            ) from exc
        manifest = self.store.create(
            self.pipeline,
            description,
            git_base=git,
            git_head=git,
        )
        visit = self.store.prepare_visit(
            manifest["run_id"], self.pipeline, self.pipeline.start
        )
        manifest = self.store.load(manifest["run_id"])
        return responses.action_response(
            self.pipeline,
            manifest,
            visit,
            f"run {manifest['run_id']} initialized; agent action is required",
        )

    def start_phase(self, run_id: str, phase_id: str) -> dict[str, Any]:
        manifest = self._load(run_id)
        if manifest["status"] == "paused":
            return responses.paused_response(
                self.pipeline, manifest, "run is paused; resume it first"
            )
        visit = self._current_visit(manifest)
        if visit is None or visit["phase_id"] != phase_id:
            expected = visit["phase_id"] if visit is not None else None
            raise EngineError(
                ExitCode.ILLEGAL_TRANSITION,
                f"cannot start phase {phase_id!r}; expected {expected!r}",
                "unexpected-phase",
                requested=phase_id,
                expected=expected,
                status=manifest["status"],
            )
        if visit["status"] == "pending":
            try:
                baseline = capture_repository_snapshot(
                    self.pipeline.repository_root,
                    allow_non_git=self.pipeline.allow_non_git,
                )
            except GitError as exc:
                raise EngineError(
                    ExitCode.VALIDATION_FAILED,
                    exc.message,
                    exc.diagnostic_code,
                    **exc.details,
                ) from exc
            visit = self.store.activate_visit(
                run_id,
                self.pipeline,
                visit["ordinal"],
                mutation_baseline=baseline,
            )
            manifest = self.store.load(run_id)
        elif visit["status"] != "active":
            raise EngineError(
                ExitCode.ILLEGAL_TRANSITION,
                f"phase {phase_id!r} cannot start from {visit['status']}",
                "illegal-visit-status",
                phase=phase_id,
                status=visit["status"],
            )
        return responses.action_response(
            self.pipeline,
            manifest, visit, f"phase {phase_id} is active; agent action is required"
        )

    def validate(
        self,
        run_id: str,
        phase_id: str | None = None,
        *,
        outcome: str | None = None,
    ) -> dict[str, Any]:
        manifest = self._load(run_id)
        if manifest["status"] == "completed":
            return responses.status_response(
                self.pipeline, manifest, "run is already completed"
            )
        if manifest["status"] == "paused":
            return responses.paused_response(
                self.pipeline, manifest, "run is paused; resume it first"
            )
        visit = self._current_visit(manifest)
        if visit is None:
            raise self._illegal("run has no current visit", manifest)
        if visit["status"] == "pending":
            previous = manifest["visits"][-2] if len(manifest["visits"]) > 1 else None
            if previous is not None and previous["status"] == "completed" and (
                phase_id is None or phase_id == previous["phase_id"]
            ):
                return responses.action_response(
                    self.pipeline,
                    manifest,
                    visit,
                    "validation was already recorded; the next phase requires agent action",
                )
            raise self._illegal(
                f"phase {visit['phase_id']!r} must be started before validation",
                manifest,
                expected_phase=visit["phase_id"],
            )
        if visit["status"] != "active":
            raise self._illegal(
                f"visit cannot be validated from {visit['status']}", manifest
            )
        self._require_phase(visit, phase_id)
        phase = self.pipeline.phase(visit["phase_id"])
        selected = self._select_outcome(phase, outcome)
        transition = next(item for item in phase.transitions if item.outcome == selected)
        evidence = self._perform_validation(manifest, visit, phase)
        updated = self.store.transition_visit(
            run_id,
            self.pipeline,
            visit["ordinal"],
            outcome=selected,
            transition_target=transition.target,
            terminal_result={
                "outcome": selected,
                "phase": phase.id,
                "visit_number": visit["ordinal"],
            },
            validation_checks=evidence.checks,
            mutation_result=evidence.mutation_result,
            command_results=evidence.command_results,
        )
        return responses.after_transition(self.pipeline, updated, selected)

    def request_approval(
        self,
        run_id: str,
        *,
        reason: str | None,
        details: str | None = None,
        outcome: str | None = None,
    ) -> dict[str, Any]:
        manifest = self._load(run_id)
        visit = self._current_visit(manifest)
        if visit is None or visit["status"] not in {"active", "awaiting-approval"}:
            raise self._illegal("only an active visit can request approval", manifest)
        phase = self.pipeline.phase(visit["phase_id"])
        chosen_reason = _declared_reason(reason, phase.approval_conditions, "approval")
        selected_outcome = self._select_outcome(phase, outcome)
        evidence = self._perform_validation(manifest, visit, phase)
        check = evidence.checks[0]
        existing = pending_approval(manifest, visit["ordinal"])
        if existing is not None:
            if (
                existing["reason"] == chosen_reason
                and existing["details"] == details
                and existing["artifact_sha256"] == check["sha256"]
                and existing["outcome"] == selected_outcome
            ):
                return responses.approval_response(
                    self.pipeline,
                    manifest, existing, "approval is already pending"
                )
            raise self._illegal("a different approval is already pending", manifest)
        approved = approved_record(manifest, visit["ordinal"])
        if approved is not None:
            return self._advance_approved(manifest, visit, approved)

        requested_at = format_timestamp(utc_now())
        approval = build_approval_record(
            run_id=run_id,
            phase_id=phase.id,
            visit_number=visit["ordinal"],
            reason=chosen_reason,
            details=details,
            artifact_sha256=check["sha256"],
            pipeline_sha256=self.pipeline.config_hash,
            outcome=selected_outcome,
            requested_at=requested_at,
        )

        def change(value: RunRecord) -> None:
            value.update(requested_state(
                value,
                approval,
                validation_checks=evidence.checks,
                mutation_result=evidence.mutation_result,
                command_results=evidence.command_results,
            ))

        manifest = self.store.mutate(
            run_id,
            "approval-requested",
            change,
            visit_number=visit["ordinal"],
            payload={"reason": chosen_reason, "outcome": selected_outcome},
        )
        return responses.approval_response(
            self.pipeline, manifest, approval, "approval is required"
        )

    def approve(self, run_id: str, phase_id: str) -> dict[str, Any]:
        # Approval verification intentionally loads persisted state before
        # enforcing the current pipeline hash so drift can be recorded as a
        # stale approval instead of becoming an unaudited early error.
        manifest = self.store.load(run_id)
        visit = self._current_visit(manifest)
        if visit is None:
            return self._idempotent_approval_result(manifest, phase_id)
        if visit["phase_id"] != phase_id or visit["status"] != "awaiting-approval":
            return self._idempotent_approval_result(manifest, phase_id)
        approval = pending_approval(manifest, visit["ordinal"])
        if approval is None:
            approved = approved_record(manifest, visit["ordinal"])
            if approved is not None:
                return self._advance_approved(manifest, visit, approved)
            raise self._illegal("visit has no pending approval request", manifest)
        try:
            current_hash = self._artifact_hash(manifest, visit)
        except EngineError:
            current_hash = ""
        mismatches = approval_integrity_errors(
            approval,
            artifact_sha256=current_hash,
            pipeline_sha256=self.pipeline.config_hash,
        )
        if mismatches:
            self._invalidate_approval(manifest, visit, approval, mismatches)
            raise EngineError(
                ExitCode.APPROVAL_REQUIRED,
                "approval request is stale because its artifact or pipeline changed",
                "stale-approval",
                phase=phase_id,
                visit_number=visit["ordinal"],
                mismatches=mismatches,
            )
        provenance_warnings = observe_provenance(self.pipeline, manifest)
        if provenance_warnings:
            warning = provenance_warnings[0]
            raise EngineError(
                ExitCode.INTERNAL_ERROR,
                warning["message"],
                warning["code"],
                **warning.get("details", {}),
            )
        decided_at = format_timestamp(utc_now())

        def decide(value: RunRecord) -> None:
            value.update(granted_state(value, visit["ordinal"], decided_at=decided_at))

        manifest = self.store.mutate(
            run_id,
            "approval-granted",
            decide,
            visit_number=visit["ordinal"],
            payload={"phase_id": phase_id, "actor": "user"},
        )
        return self._advance_approved(manifest, visit, approval)

    def block(
        self,
        run_id: str,
        *,
        reason: str | None,
        details: str | None = None,
    ) -> dict[str, Any]:
        manifest = self._load(run_id)
        if manifest["status"] == "blocked":
            recorded = manifest["block_reason"] or {}
            if reason is not None and reason != recorded.get("reason"):
                raise self._illegal(
                    "run is already blocked for a different reason", manifest
                )
            if details is not None and details != recorded.get("details"):
                raise self._illegal(
                    "run is already blocked with different details", manifest
                )
            return responses.blocked_response(
                self.pipeline, manifest, "run is already blocked"
            )
        visit = self._current_visit(manifest)
        if visit is None or visit["status"] != "active":
            raise self._illegal("only an active visit can be blocked", manifest)
        phase = self.pipeline.phase(visit["phase_id"])
        chosen_reason = _declared_reason(reason, phase.stop_conditions, "stop")
        block = {
            "phase_id": phase.id,
            "visit_number": visit["ordinal"],
            "reason": chosen_reason,
            "details": details,
            "recorded_at": format_timestamp(utc_now()),
        }

        def change(value: RunRecord) -> None:
            current = self._current_visit(value)
            assert current is not None
            current["status"] = "blocked"
            value["status"] = "blocked"
            value["block_reason"] = block

        manifest = self.store.mutate(
            run_id,
            "run-blocked",
            change,
            visit_number=visit["ordinal"],
            payload={"reason": chosen_reason, "details": details},
        )
        return responses.blocked_response(self.pipeline, manifest, "run is blocked")

    def status(self, run_id: str) -> dict[str, Any]:
        manifest = self.store.load(run_id, verify_artifacts=False)
        warnings: list[dict[str, Any]] = []
        if not pipeline_matches(self.pipeline, manifest):
            warnings.append(
                {
                    "code": "pipeline-drift",
                    "message": "pipeline configuration differs from the run provenance",
                }
            )
        try:
            verify_manifest_artifacts(manifest, self.store.run_directory(run_id))
        except ArtifactError as exc:
            warnings.append(
                {
                    "code": exc.diagnostic_code,
                    "message": exc.message,
                    "details": exc.details,
                }
            )
        warnings.extend(observe_provenance(self.pipeline, manifest))
        return responses.status_response(
            self.pipeline, manifest, "run status", warnings=warnings
        )

    def resume(self, run_id: str) -> dict[str, Any]:
        manifest = self._load(run_id)
        if manifest["status"] == "paused":
            manifest = self.store.resume_paused(run_id, self.pipeline)
        return responses.response_for_state(self.pipeline, manifest, "run resumed")

    def run(self, run_id: str) -> dict[str, Any]:
        manifest = self._load(run_id)
        visit = self._current_visit(manifest)
        if manifest["status"] == "awaiting-approval" and visit is not None:
            approved = approved_record(manifest, visit["ordinal"])
            if approved is not None:
                return self._advance_approved(manifest, visit, approved)
        if visit is not None and visit["status"] == "pending":
            return self.start_phase(run_id, visit["phase_id"])
        return responses.response_for_state(
            self.pipeline, manifest, "run reached a boundary"
        )

    def _advance_approved(
        self,
        manifest: RunRecord,
        visit: VisitRecord,
        approval: ApprovalRecord,
    ) -> dict[str, Any]:
        try:
            current_hash = self._artifact_hash(manifest, visit)
        except EngineError:
            current_hash = ""
        mismatches = approval_integrity_errors(
            approval,
            artifact_sha256=current_hash,
            pipeline_sha256=self.pipeline.config_hash,
        )
        if mismatches:
            self._invalidate_approval(manifest, visit, approval, mismatches)
            raise EngineError(
                ExitCode.APPROVAL_REQUIRED,
                "approval is stale because its artifact or pipeline changed",
                "stale-approval",
                phase=visit["phase_id"],
                visit_number=visit["ordinal"],
                mismatches=mismatches,
            )
        phase = self.pipeline.phase(visit["phase_id"])
        evidence = self._perform_validation(manifest, visit, phase)
        transition = next(
            item for item in phase.transitions if item.outcome == approval["outcome"]
        )
        updated = self.store.transition_visit(
            manifest["run_id"],
            self.pipeline,
            visit["ordinal"],
            outcome=approval["outcome"],
            transition_target=transition.target,
            terminal_result={
                "outcome": approval["outcome"],
                "phase": phase.id,
                "visit_number": visit["ordinal"],
                "approval_reason": approval["reason"],
            },
            validation_checks=evidence.checks,
            mutation_result=evidence.mutation_result,
            command_results=evidence.command_results,
        )
        return responses.after_transition(self.pipeline, updated, approval["outcome"])

    def _load(self, run_id: str) -> RunRecord:
        manifest = self.store.load(run_id)
        if not pipeline_matches(self.pipeline, manifest):
            raise EngineError(
                ExitCode.INVALID_PIPELINE,
                "pipeline configuration changed after the run was created",
                "pipeline-hash-mismatch",
                expected=manifest["pipeline"],
                actual=pipeline_identity(self.pipeline),
            )
        provenance_warnings = observe_provenance(self.pipeline, manifest)
        if provenance_warnings:
            warning = provenance_warnings[0]
            raise EngineError(
                ExitCode.INTERNAL_ERROR,
                warning["message"],
                warning["code"],
                **warning.get("details", {}),
            )
        return manifest

    def _perform_validation(
        self,
        manifest: RunRecord,
        visit: VisitRecord,
        phase: PhaseConfig,
    ) -> ValidationResult:
        # Keep this orchestration seam for overlapping-attempt fault injection.
        result = perform_validation(
            self.pipeline,
            self.store.run_directory(manifest["run_id"]),
            visit,
            phase,
            command_fault_injector=self._command_fault_injector,
        )
        if result.failure is not None:
            self.store.record_validation_attempt(
                manifest["run_id"],
                visit["ordinal"],
                validation_checks=result.checks,
                command_results=result.command_results,
                mutation_result=result.mutation_result,
                diagnostic={"error_code": result.failure.diagnostic_code},
            )
            raise result.failure from result.cause
        return result

    def _artifact_hash(
        self, manifest: RunRecord, visit: VisitRecord
    ) -> str:
        try:
            return artifact_record(
                self.store.run_directory(manifest["run_id"]),
                visit["output"]["path"],
            )["sha256"]
        except (ArtifactError, OSError) as exc:
            details = dict(getattr(exc, "details", None) or {"error": str(exc)})
            details.pop("error_code", None)
            raise EngineError(
                ExitCode.VALIDATION_FAILED,
                "output artifact is missing or unreadable",
                "invalid-output",
                **details,
            ) from exc

    def _invalidate_approval(
        self,
        manifest: RunRecord,
        visit: VisitRecord,
        approval: ApprovalRecord,
        mismatches: list[str],
    ) -> None:
        decided_at = format_timestamp(utc_now())

        def invalidate(value: RunRecord) -> None:
            value.update(invalidated_state(
                value, visit["ordinal"], approval, decided_at=decided_at
            ))

        self.store.mutate(
            manifest["run_id"],
            "approval-invalidated",
            invalidate,
            visit_number=visit["ordinal"],
            payload={"mismatches": mismatches},
        )

    def _select_outcome(self, phase: PhaseConfig, requested: str | None) -> str:
        outcomes = [
            transition.outcome
            for transition in phase.transitions
            if transition.outcome != "blocked"
        ]
        if requested is not None:
            if requested not in outcomes:
                raise EngineError(
                    ExitCode.ILLEGAL_TRANSITION,
                    f"outcome {requested!r} is not declared by phase {phase.id!r}",
                    "undeclared-outcome",
                    phase=phase.id,
                    requested=requested,
                    declared=outcomes,
                )
            if len(outcomes) <= 1:
                raise EngineError(
                    ExitCode.ILLEGAL_TRANSITION,
                    "--outcome is valid only when the phase has multiple successful outcomes",
                    "unnecessary-outcome",
                    phase=phase.id,
                    declared=outcomes,
                )
            return requested
        if len(outcomes) != 1:
            raise EngineError(
                ExitCode.ILLEGAL_TRANSITION,
                f"phase {phase.id!r} requires one of {outcomes!r}",
                "outcome-required",
                phase=phase.id,
                declared=outcomes,
            )
        return outcomes[0]

    @staticmethod
    def _current_visit(manifest: RunRecord) -> VisitRecord | None:
        return current_visit(manifest)

    # Preserve selector entry points used by existing callers and tests.
    _pending_approval = staticmethod(pending_approval)
    _approved_record = staticmethod(approved_record)

    @staticmethod
    def _require_phase(visit: VisitRecord, requested: str | None) -> None:
        if requested is not None and requested != visit["phase_id"]:
            raise EngineError(
                ExitCode.ILLEGAL_TRANSITION,
                f"requested phase {requested!r}; expected {visit['phase_id']!r}",
                "unexpected-phase",
                requested=requested,
                expected=visit["phase_id"],
            )

    @staticmethod
    def _illegal(
        message: str, manifest: RunRecord, **details: Any
    ) -> EngineError:
        return EngineError(
            ExitCode.ILLEGAL_TRANSITION,
            message,
            "illegal-transition",
            status=manifest["status"],
            **details,
        )

    def _idempotent_approval_result(
        self, manifest: RunRecord, phase_id: str
    ) -> dict[str, Any]:
        approved = approved_for_phase(manifest, phase_id)
        if approved is None:
            raise self._illegal(
                f"phase {phase_id!r} has no pending approval", manifest
            )
        return responses.response_for_state(
            self.pipeline, manifest, "approval was already recorded"
        )


def capture_git_metadata(root: Path, *, include_status: bool = False) -> dict[str, Any]:
    """Backward-compatible alias for content-level repository capture."""

    snapshot = capture_repository_snapshot(root, allow_non_git=True)
    if include_status:
        return {**snapshot, "status": []}
    return {
        "is_worktree": snapshot["is_worktree"],
        "head": snapshot["head"],
        "branch": snapshot["branch"],
        "status": [],
    }


def _declared_reason(
    requested: str | None, declared: tuple[str, ...], kind: str
) -> str:
    if requested is None:
        if len(declared) == 1:
            return declared[0]
        raise UsageError(
            f"--reason is required; declared {kind} reasons: {', '.join(declared) or 'none'}",
            {"declared": list(declared)},
        )
    if requested not in declared:
        raise EngineError(
            ExitCode.ILLEGAL_TRANSITION,
            f"{kind} reason {requested!r} is not declared",
            f"undeclared-{kind}-reason",
            requested=requested,
            declared=list(declared),
        )
    return requested
