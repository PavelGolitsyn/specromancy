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
    build_approval_record, granted_state, invalidated_state, pending_approval,
    requested_state,
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

    def advance_approved(
        self,
        manifest: RunRecord,
        visit: VisitRecord,
        approval: ApprovalRecord,
    ) -> dict[str, Any]:
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
            raise illegal_transition("a different approval is already pending", manifest)
        approved = approved_record(manifest, visit["ordinal"])
        if approved is not None:
            return self.advance_approved(manifest, visit, approved)

        requested_at = self._timestamp()
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

        def decide(value: RunRecord) -> None:
            value.update(granted_state(value, visit["ordinal"], decided_at=decided_at))

        manifest = self.store.mutate(
            run_id,
            "approval-granted",
            decide,
            visit_number=visit["ordinal"],
            payload={"phase_id": phase_id, "actor": "user"},
        )
        return self.advance_approved(manifest, visit, approval)

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
