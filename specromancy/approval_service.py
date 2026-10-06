"""Coordinate approval requests, grants, invalidation, and continuation.

The caller supplies a strictly loaded manifest for requests. Grants deliberately
load persisted state here before checking bindings, so drift can be audited.
Validation collects evidence and records expected failures through an explicit
collaborator; successful evidence is committed with the request or transition.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import responses
from .approvals import (
    approval_integrity_errors, approved_for_phase, approved_record,
    build_approval_record, conflict, grant_decision, invalidate_decision,
    pending_approval, request_decision, require_binding,
)
from .artifacts import ArtifactError, artifact_record
from .command_decisions import declared_reason, illegal_transition, select_outcome
from .config_models import PhaseConfig, PipelineConfig
from .engine_errors import EngineError
from .exit_codes import ExitCode
from .provenance import observe_provenance
from .run_records import ApprovalRecord, RunRecord, VisitRecord, current_visit
from .run_store import RunStore
from .validation_service import ValidationResult


class ApprovalService:
    """Own approval ordering with explicit validation and timestamp seams."""

    def __init__(
        self,
        pipeline: PipelineConfig,
        store: RunStore,
        *,
        validate: Callable[[RunRecord, VisitRecord, PhaseConfig], ValidationResult],
        timestamp: Callable[[], str],
    ) -> None:
        self.pipeline = pipeline
        self.store = store
        self._perform_validation = validate
        self._timestamp = timestamp

    def invalidate_approval(
        self,
        manifest: RunRecord,
        visit: VisitRecord,
        approval: ApprovalRecord,
        mismatches: list[str],
    ) -> None:
        decided_at = self._timestamp()

        self.store.decide_approval(
            manifest["run_id"],
            lambda value: invalidate_decision(
                value, approval, decided_at=decided_at, mismatches=mismatches,
            ),
        )

    def advance_approved(
        self,
        manifest: RunRecord,
        visit: VisitRecord,
        approval: ApprovalRecord,
    ) -> dict[str, Any]:
        require_binding(manifest, approval)
        transition = next((
            item for item in self.pipeline.phase(visit["phase_id"]).transitions
            if item.outcome == approval["outcome"]
        ), None)
        decision = self.store.decide_approval(
            manifest["run_id"], lambda value: grant_decision(
                value, approval, transition_target=transition.target if transition else None,
                decided_at=None,
            ),
        )
        manifest, approval = decision.manifest, decision.approval
        if decision.disposition == "completed":
            return responses.response_for_state(
                self.pipeline, manifest, "approval was already recorded"
            )
        visit = current_visit(manifest)
        try:
            current_hash = self.artifact_hash(manifest, visit)
        except EngineError:
            current_hash = ""
        mismatches = approval_integrity_errors(
            approval,
            artifact_sha256=current_hash,
            pipeline_sha256=self.pipeline.config_hash,
        )
        if mismatches:
            self.invalidate_approval(manifest, visit, approval, mismatches)
            raise EngineError(
                ExitCode.APPROVAL_REQUIRED,
                "approval is stale because its artifact or pipeline changed",
                "stale-approval",
                phase=visit["phase_id"],
                visit_number=visit["ordinal"],
                mismatches=mismatches,
            )
        if transition is None:
            raise conflict(approval)
        phase = self.pipeline.phase(visit["phase_id"])
        evidence = self._perform_validation(manifest, visit, phase)
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

    def request_approval(
        self,
        manifest: RunRecord,
        *,
        reason: str | None,
        details: str | None = None,
        outcome: str | None = None,
    ) -> dict[str, Any]:
        run_id = manifest["run_id"]
        visit = current_visit(manifest)
        if visit is None or visit["status"] not in {"active", "awaiting-approval"}:
            raise illegal_transition("only an active visit can request approval", manifest)
        phase = self.pipeline.phase(visit["phase_id"])
        chosen_reason = declared_reason(reason, phase.approval_conditions, "approval")
        selected_outcome = select_outcome(phase, outcome)
        evidence = self._perform_validation(manifest, visit, phase)
        check = evidence.checks[0]
        existing = pending_approval(manifest, visit["ordinal"])
        if existing is not None:
            require_binding(manifest, existing)
            if not (
                existing["reason"] == chosen_reason
                and existing["details"] == details
                and existing["artifact_sha256"] == check["sha256"]
                and existing["outcome"] == selected_outcome
            ):
                raise illegal_transition("a different approval is already pending", manifest)
        approved = approved_record(manifest, visit["ordinal"])
        if approved is not None:
            return self.advance_approved(manifest, visit, approved)

        requested_at = existing["requested_at"] if existing else self._timestamp()
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

        decision = self.store.decide_approval(
            run_id, lambda value: request_decision(
                value, approval, validation_checks=evidence.checks,
                mutation_result=evidence.mutation_result,
                command_results=evidence.command_results,
            ),
        )
        return responses.approval_response(
            self.pipeline, decision.manifest, decision.approval,
            "approval is required" if decision.disposition == "requested"
            else "approval is already pending",
        )

    def approve(self, run_id: str, phase_id: str) -> dict[str, Any]:
        # Approval verification intentionally loads persisted state before
        # enforcing the current pipeline hash so drift can be recorded as a
        # stale approval instead of becoming an unaudited early error.
        manifest = self.store.load(run_id)
        visit = current_visit(manifest)
        if visit is None:
            return self.idempotent_approval_result(manifest, phase_id)
        if visit["phase_id"] != phase_id or visit["status"] != "awaiting-approval":
            return self.idempotent_approval_result(manifest, phase_id)
        approval = pending_approval(manifest, visit["ordinal"])
        if approval is None:
            approved = approved_record(manifest, visit["ordinal"])
            if approved is not None:
                return self.advance_approved(manifest, visit, approved)
            raise illegal_transition("visit has no pending approval request", manifest)
        require_binding(manifest, approval)
        try:
            current_hash = self.artifact_hash(manifest, visit)
        except EngineError:
            current_hash = ""
        mismatches = approval_integrity_errors(
            approval,
            artifact_sha256=current_hash,
            pipeline_sha256=self.pipeline.config_hash,
        )
        if mismatches:
            self.invalidate_approval(manifest, visit, approval, mismatches)
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
        decided_at = self._timestamp()

        transition = next((
            item for item in self.pipeline.phase(phase_id).transitions
            if item.outcome == approval["outcome"]
        ), None)
        if transition is None:
            raise conflict(approval)
        decision = self.store.decide_approval(
            run_id, lambda value: grant_decision(
                value, approval, decided_at=decided_at, transition_target=transition.target,
            ),
        )
        if decision.disposition == "completed":
            return responses.response_for_state(
                self.pipeline, decision.manifest, "approval was already recorded"
            )
        return self.advance_approved(
            decision.manifest, current_visit(decision.manifest), decision.approval,
        )

    def artifact_hash(
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

    def idempotent_approval_result(
        self, manifest: RunRecord, phase_id: str
    ) -> dict[str, Any]:
        approved = approved_for_phase(manifest, phase_id)
        if approved is None:
            raise illegal_transition(
                f"phase {phase_id!r} has no pending approval", manifest
            )
        return responses.response_for_state(
            self.pipeline, manifest, "approval was already recorded"
        )
