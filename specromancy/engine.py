"""Generic, deterministic state-machine execution."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .actions import build_action_packet
from .artifacts import ArtifactError, artifact_record, verify_manifest_artifacts
from .config import PhaseConfig, PipelineConfig
from .errors import SpecromancyError, UsageError
from .exit_codes import ExitCode
from .hashing import relative_path, sha256_file
from .run_store import RunStore, format_timestamp, utc_now
from .status import build_status


RESPONSE_SCHEMA_VERSION = 1


class EngineError(SpecromancyError):
    """An expected state-machine rejection with a stable diagnostic."""

    def __init__(
        self,
        code: ExitCode,
        message: str,
        diagnostic_code: str,
        **details: Any,
    ) -> None:
        super().__init__(code, message, {"error_code": diagnostic_code, **details})
        self.diagnostic_code = diagnostic_code


class Engine:
    """Advance runs using only configured outcomes and persisted state."""

    def __init__(self, pipeline: PipelineConfig, store: RunStore | None = None) -> None:
        self.pipeline = pipeline
        self.store = store or RunStore(pipeline.repository_root)

    def initialize(self, description: str) -> dict[str, Any]:
        if not description.strip():
            raise UsageError("DESCRIPTION must not be empty")
        git = capture_git_metadata(self.pipeline.repository_root)
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
        return self._action_response(
            manifest,
            visit,
            f"run {manifest['run_id']} initialized; agent action is required",
        )

    def start_phase(self, run_id: str, phase_id: str) -> dict[str, Any]:
        manifest = self._load(run_id)
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
            visit = self.store.activate_visit(
                run_id,
                self.pipeline,
                visit["ordinal"],
                mutation_baseline=capture_git_metadata(
                    self.pipeline.repository_root, include_status=True
                ),
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
        return self._action_response(
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
            return self._status_response(manifest, "run is already completed")
        visit = self._current_visit(manifest)
        if visit is None:
            raise self._illegal("run has no current visit", manifest)
        if visit["status"] == "pending":
            previous = manifest["visits"][-2] if len(manifest["visits"]) > 1 else None
            if previous is not None and previous["status"] == "completed" and (
                phase_id is None or phase_id == previous["phase_id"]
            ):
                return self._action_response(
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
        check = self._validate_output(manifest, visit)
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
            validation_checks=[check],
        )
        return self._after_transition(updated, selected)

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
        check = self._validate_output(manifest, visit)
        existing = self._pending_approval(manifest, visit["ordinal"])
        if existing is not None:
            if (
                existing["reason"] == chosen_reason
                and existing["details"] == details
                and existing["artifact_sha256"] == check["sha256"]
                and existing["outcome"] == selected_outcome
            ):
                return self._approval_response(
                    manifest, existing, "approval is already pending"
                )
            raise self._illegal("a different approval is already pending", manifest)
        approved = self._approved_record(manifest, visit["ordinal"])
        if approved is not None:
            return self._advance_approved(manifest, visit, approved)

        requested_at = format_timestamp(utc_now())
        approval = {
            "run_id": run_id,
            "phase_id": phase.id,
            "visit_number": visit["ordinal"],
            "reason": chosen_reason,
            "details": details,
            "artifact_sha256": check["sha256"],
            "pipeline_sha256": self.pipeline.config_hash,
            "outcome": selected_outcome,
            "status": "pending",
            "decision": None,
            "actor": None,
            "requested_at": requested_at,
            "decided_at": None,
        }

        def change(value: dict[str, Any]) -> None:
            current = self._current_visit(value)
            assert current is not None
            current["status"] = "awaiting-approval"
            value["status"] = "awaiting-approval"
            value["approvals"].append(approval)

        manifest = self.store.mutate(
            run_id,
            "approval-requested",
            change,
            visit_number=visit["ordinal"],
            payload={"reason": chosen_reason, "outcome": selected_outcome},
        )
        return self._approval_response(manifest, approval, "approval is required")

    def approve(self, run_id: str, phase_id: str) -> dict[str, Any]:
        manifest = self._load(run_id)
        visit = self._current_visit(manifest)
        if visit is None:
            return self._idempotent_approval_result(manifest, phase_id)
        if visit["phase_id"] != phase_id or visit["status"] != "awaiting-approval":
            return self._idempotent_approval_result(manifest, phase_id)
        approval = self._pending_approval(manifest, visit["ordinal"])
        if approval is None:
            approved = self._approved_record(manifest, visit["ordinal"])
            if approved is not None:
                return self._advance_approved(manifest, visit, approved)
            raise self._illegal("visit has no pending approval request", manifest)
        current_hash = self._validate_output(manifest, visit)["sha256"]
        if (
            current_hash != approval["artifact_sha256"]
            or approval["pipeline_sha256"] != self.pipeline.config_hash
        ):
            raise EngineError(
                ExitCode.APPROVAL_REQUIRED,
                "approval request is stale because its artifact or pipeline changed",
                "stale-approval",
                phase=phase_id,
                visit_number=visit["ordinal"],
            )
        decided_at = format_timestamp(utc_now())

        def decide(value: dict[str, Any]) -> None:
            record = self._pending_approval(value, visit["ordinal"])
            assert record is not None
            record["status"] = "approved"
            record["decision"] = "approved"
            record["actor"] = "user"
            record["decided_at"] = decided_at

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
            return self._blocked_response(manifest, "run is already blocked")
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

        def change(value: dict[str, Any]) -> None:
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
        return self._blocked_response(manifest, "run is blocked")

    def status(self, run_id: str) -> dict[str, Any]:
        manifest = self.store.load(run_id, verify_artifacts=False)
        warnings: list[dict[str, Any]] = []
        if not self._pipeline_matches(manifest):
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
        warnings.extend(self._provenance_warnings(manifest))
        return self._status_response(manifest, "run status", warnings=warnings)

    def resume(self, run_id: str) -> dict[str, Any]:
        manifest = self._load(run_id)
        return self._response_for_state(manifest, "run resumed")

    def run(self, run_id: str) -> dict[str, Any]:
        manifest = self._load(run_id)
        visit = self._current_visit(manifest)
        if manifest["status"] == "awaiting-approval" and visit is not None:
            approved = next(
                (
                    item
                    for item in reversed(manifest["approvals"])
                    if item.get("visit_number") == visit["ordinal"]
                    and item.get("status") == "approved"
                ),
                None,
            )
            if approved is not None:
                return self._advance_approved(manifest, visit, approved)
        if visit is not None and visit["status"] == "pending":
            return self.start_phase(run_id, visit["phase_id"])
        return self._response_for_state(manifest, "run reached a boundary")

    def _advance_approved(
        self,
        manifest: dict[str, Any],
        visit: dict[str, Any],
        approval: dict[str, Any],
    ) -> dict[str, Any]:
        phase = self.pipeline.phase(visit["phase_id"])
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
            validation_checks=[
                {
                    "type": "file",
                    "status": "passed",
                    "sha256": approval["artifact_sha256"],
                }
            ],
        )
        return self._after_transition(updated, approval["outcome"])

    def _after_transition(
        self, manifest: dict[str, Any], outcome: str
    ) -> dict[str, Any]:
        if manifest["status"] == "completed":
            return self._status_response(
                manifest, f"run completed with outcome {outcome!r}"
            )
        visit = self._current_visit(manifest)
        assert visit is not None
        return self._action_response(
            manifest,
            visit,
            f"outcome {outcome!r} recorded; next phase requires agent action",
        )

    def _response_for_state(
        self, manifest: dict[str, Any], message: str
    ) -> dict[str, Any]:
        visit = self._current_visit(manifest)
        if manifest["status"] in {"awaiting-agent", "active"} and visit is not None:
            return self._action_response(manifest, visit, message)
        if manifest["status"] == "awaiting-approval":
            approval = self._pending_approval(
                manifest, visit["ordinal"] if visit is not None else -1
            )
            return self._approval_response(manifest, approval, "approval is required")
        if manifest["status"] == "blocked":
            return self._blocked_response(manifest, message)
        return self._status_response(manifest, message)

    def _load(self, run_id: str) -> dict[str, Any]:
        manifest = self.store.load(run_id)
        if not self._pipeline_matches(manifest):
            raise EngineError(
                ExitCode.INVALID_PIPELINE,
                "pipeline configuration changed after the run was created",
                "pipeline-hash-mismatch",
                expected=manifest["pipeline"],
                actual={
                    "id": self.pipeline.id,
                    "version": self.pipeline.version,
                    "path": relative_path(
                        self.pipeline.path, self.pipeline.repository_root
                    ),
                    "sha256": self.pipeline.config_hash,
                },
            )
        provenance_warnings = self._provenance_warnings(manifest)
        if provenance_warnings:
            warning = provenance_warnings[0]
            raise EngineError(
                ExitCode.INTERNAL_ERROR,
                warning["message"],
                warning["code"],
                **warning.get("details", {}),
            )
        return manifest

    def _provenance_warnings(
        self, manifest: dict[str, Any]
    ) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []
        for visit in manifest["visits"]:
            for kind in ("skill", "template"):
                record = visit[kind]
                if record is None:
                    continue
                path = self.pipeline.repository_root / record["path"]
                try:
                    actual = sha256_file(path)
                except OSError as exc:
                    warnings.append(
                        {
                            "code": "provenance-missing",
                            "message": f"visit {visit['ordinal']} {kind} provenance is missing",
                            "details": {"path": record["path"], "error": str(exc)},
                        }
                    )
                    continue
                if actual != record["sha256"]:
                    warnings.append(
                        {
                            "code": "provenance-hash-mismatch",
                            "message": f"visit {visit['ordinal']} {kind} changed after preparation",
                            "details": {
                                "path": record["path"],
                                "expected": record["sha256"],
                                "actual": actual,
                            },
                        }
                    )
        return warnings

    def _pipeline_matches(self, manifest: dict[str, Any]) -> bool:
        saved = manifest["pipeline"]
        return saved == {
            "id": self.pipeline.id,
            "version": self.pipeline.version,
            "path": relative_path(self.pipeline.path, self.pipeline.repository_root),
            "sha256": self.pipeline.config_hash,
        }

    def _validate_output(
        self, manifest: dict[str, Any], visit: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            record = artifact_record(
                self.store.run_directory(manifest["run_id"]), visit["output"]["path"]
            )
            path = self.store.run_directory(manifest["run_id"]) / record["path"]
            if not path.read_bytes().strip():
                raise EngineError(
                    ExitCode.VALIDATION_FAILED,
                    f"output artifact is empty: {record['path']}",
                    "empty-output",
                    path=record["path"],
                )
        except EngineError:
            raise
        except (ArtifactError, OSError) as exc:
            details = dict(getattr(exc, "details", None) or {"error": str(exc)})
            details.pop("error_code", None)
            raise EngineError(
                ExitCode.VALIDATION_FAILED,
                "output artifact is missing or unreadable",
                "invalid-output",
                **details,
            ) from exc
        return {"type": "file", "status": "passed", "sha256": record["sha256"]}

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
    def _current_visit(manifest: dict[str, Any]) -> dict[str, Any] | None:
        ordinal = manifest["current_visit"]
        if ordinal is None:
            return None
        return next(
            (visit for visit in manifest["visits"] if visit["ordinal"] == ordinal),
            None,
        )

    @staticmethod
    def _pending_approval(
        manifest: dict[str, Any], visit_number: int
    ) -> dict[str, Any] | None:
        return next(
            (
                approval
                for approval in reversed(manifest["approvals"])
                if approval.get("visit_number") == visit_number
                and approval.get("status") == "pending"
            ),
            None,
        )

    @staticmethod
    def _approved_record(
        manifest: dict[str, Any], visit_number: int
    ) -> dict[str, Any] | None:
        return next(
            (
                approval
                for approval in reversed(manifest["approvals"])
                if approval.get("visit_number") == visit_number
                and approval.get("status") == "approved"
            ),
            None,
        )

    @staticmethod
    def _require_phase(visit: dict[str, Any], requested: str | None) -> None:
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
        message: str, manifest: dict[str, Any], **details: Any
    ) -> EngineError:
        return EngineError(
            ExitCode.ILLEGAL_TRANSITION,
            message,
            "illegal-transition",
            status=manifest["status"],
            **details,
        )

    def _idempotent_approval_result(
        self, manifest: dict[str, Any], phase_id: str
    ) -> dict[str, Any]:
        approved = next(
            (
                item
                for item in reversed(manifest["approvals"])
                if item.get("phase_id") == phase_id and item.get("status") == "approved"
            ),
            None,
        )
        if approved is None:
            raise self._illegal(
                f"phase {phase_id!r} has no pending approval", manifest
            )
        return self._response_for_state(manifest, "approval was already recorded")

    def _action_response(
        self, manifest: dict[str, Any], visit: dict[str, Any], message: str
    ) -> dict[str, Any]:
        return {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "kind": "action",
            "code": int(ExitCode.AGENT_ACTION_REQUIRED),
            "message": message,
            "action": build_action_packet(self.pipeline, manifest, visit),
        }

    def _approval_response(
        self,
        manifest: dict[str, Any],
        approval: dict[str, Any] | None,
        message: str,
    ) -> dict[str, Any]:
        return {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "kind": "approval",
            "code": int(ExitCode.APPROVAL_REQUIRED),
            "message": message,
            "approval": approval,
            "status": build_status(manifest, self.pipeline),
        }

    def _blocked_response(
        self, manifest: dict[str, Any], message: str
    ) -> dict[str, Any]:
        return {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "kind": "status",
            "code": int(ExitCode.RUN_BLOCKED),
            "message": message,
            "status": build_status(manifest, self.pipeline),
        }

    def _status_response(
        self,
        manifest: dict[str, Any],
        message: str,
        *,
        warnings: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "kind": "status",
            "code": int(ExitCode.SUCCESS),
            "message": message,
            "status": build_status(manifest, self.pipeline, warnings=warnings),
        }


def capture_git_metadata(root: Path, *, include_status: bool = False) -> dict[str, Any]:
    """Capture the small Git baseline needed by Stage 04 without mutating Git."""

    def git(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

    try:
        worktree = git("rev-parse", "--is-inside-work-tree")
    except (OSError, subprocess.TimeoutExpired):
        return {"is_worktree": False, "head": None, "branch": None, "status": []}
    if worktree.returncode != 0 or worktree.stdout.strip() != "true":
        return {"is_worktree": False, "head": None, "branch": None, "status": []}
    head = git("rev-parse", "HEAD")
    branch = git("symbolic-ref", "--quiet", "--short", "HEAD")
    status: list[str] = []
    if include_status:
        result = git("status", "--short", "--untracked-files=all")
        if result.returncode == 0:
            status = result.stdout.splitlines()
    return {
        "is_worktree": True,
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "branch": branch.stdout.strip() if branch.returncode == 0 else None,
        "status": status,
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
