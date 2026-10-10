"""Recoverable, disk-backed run manifests and append-only audit events."""

from __future__ import annotations

import copy
import os
import secrets
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from .artifacts import (
    ArtifactError,
    artifact_record,
    render_output_path,
    resolve_input_reference,
    verify_manifest_artifacts,
    write_artifact_atomic,
)
from ._config.config_models import PipelineConfig
from .exit_codes import ExitCode
from .hashing import (
    relative_path,
    resolve_relative_path,
    sha256_file,
)
from .locking import RunLock
from ._runs.run_persistence import RunPersistence
from ._engine import approvals
from ._runs import run_validation, visit_preparation, visit_transitions
from ._runs.run_errors import RunCorruptionError, RunNotFoundError, RunStoreError
from ._runs.run_identity import (
    RUN_ID_PATTERN, format_timestamp, generate_run_id, is_valid_run_id,
    utc_now, validate_run_id,
)
from ._runs.run_records import (
    EVENT_SCHEMA_VERSION, EVENT_TYPE_PATTERN, RUN_SCHEMA_VERSION,
    RUN_STATUSES, VISIT_STATUSES, EventRecord, RunRecord, VisitRecord, visit_by_number,
)


class RunStore:
    """Own run directories and make each manifest mutation durable and audited."""

    def __init__(
        self,
        repository_root: str | os.PathLike[str],
        *,
        clock: Callable[[], datetime] = utc_now,
        random_source: Callable[..., bytes | str] = secrets.token_bytes,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        root = Path(repository_root).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError(f"repository root is not a directory: {root}")
        self.repository_root = root
        self.runs_root = root / ".specromancy" / "runs"
        self._clock = clock
        self._random_source = random_source
        self._fault_injector = fault_injector
        self._persistence = RunPersistence(
            clock=lambda: self._clock(), timestamp=self._timestamp, fault=self._fault
        )

    def new_run_id(self) -> str:
        return generate_run_id(clock=self._clock, random_source=self._random_source)

    def run_directory(self, run_id: str, *, must_exist: bool = True) -> Path:
        validate_run_id(run_id)
        candidate = self.runs_root / run_id
        if must_exist and not candidate.is_dir():
            raise RunNotFoundError(run_id)
        if candidate.exists():
            try:
                resolved = candidate.resolve(strict=True)
                runs_root = self.runs_root.resolve(strict=True)
            except OSError as exc:
                raise RunCorruptionError(
                    "run directory cannot be resolved",
                    run_id=run_id,
                    details={"path": str(candidate)},
                ) from exc
            if not resolved.is_relative_to(runs_root) or resolved != candidate.absolute():
                raise RunCorruptionError(
                    "run directory is a symlink or escapes run storage",
                    run_id=run_id,
                    details={"path": str(candidate)},
                )
        return candidate

    def lock(self, run_id: str) -> RunLock:
        directory = self.run_directory(run_id)
        return self._persistence.lock(directory)

    def create(
        self,
        pipeline: PipelineConfig,
        request: str,
        *,
        run_id: str | None = None,
        git_base: Any = None,
        git_head: Any = None,
    ) -> RunRecord:
        """Create a run, its immutable request, manifest, and first event."""

        if pipeline.repository_root.resolve() != self.repository_root:
            raise RunStoreError(
                "pipeline and run store use different repository roots",
                diagnostic_code="repository-root-mismatch",
                details={
                    "pipeline_root": str(pipeline.repository_root),
                    "store_root": str(self.repository_root),
                },
            )
        chosen_id = self.new_run_id() if run_id is None else validate_run_id(run_id)
        self._prepare_runs_root()
        directory = self.runs_root / chosen_id
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise RunStoreError(
                f"run already exists: {chosen_id}",
                diagnostic_code="run-already-exists",
                details={"run_id": chosen_id},
            ) from exc

        with self._persistence.lock(directory):
            (directory / "artifacts").mkdir(mode=0o700)
            (directory / "commands").mkdir(mode=0o700)
            (directory / "events.jsonl").touch(mode=0o600)
            request_path = "artifacts/000-request.md"
            request_content = request if request.endswith("\n") else request + "\n"
            request_hash = write_artifact_atomic(
                directory, request_path, request_content, replace=False
            )
            timestamp = self._timestamp()
            manifest: RunRecord = {
                "schema_version": RUN_SCHEMA_VERSION,
                "revision": 1,
                "run_id": chosen_id,
                "pipeline": {
                    "id": pipeline.id,
                    "version": pipeline.version,
                    "path": relative_path(pipeline.path, self.repository_root),
                    "sha256": pipeline.config_hash,
                },
                "status": "awaiting-agent",
                "current_visit": None,
                "request": {"path": request_path, "sha256": request_hash},
                "git": {"base": git_base, "head": git_head},
                "created_at": timestamp,
                "updated_at": timestamp,
                "visits": [],
                "approvals": [],
                "terminal_result": None,
                "block_reason": None,
            }
            self._persistence.commit_locked(
                directory, manifest, [], "run-created", None, {"pipeline_id": pipeline.id}
            )
        return copy.deepcopy(manifest)

    create_run = create

    def load(
        self,
        run_id: str,
        *,
        recover: bool = True,
        verify_artifacts: bool = True,
    ) -> RunRecord:
        """Reconstruct current state from disk, optionally repairing an event gap."""

        directory = self.run_directory(run_id)
        with self._persistence.locked(directory, run_id, recover=recover) as (
            manifest, _events
        ):
            if verify_artifacts:
                try:
                    verify_manifest_artifacts(manifest, directory)
                except ArtifactError:
                    raise
        return copy.deepcopy(manifest)

    load_run = load

    def read_events(self, run_id: str, *, recover: bool = True) -> list[EventRecord]:
        directory = self.run_directory(run_id)
        with self._persistence.locked(directory, run_id, recover=recover):
            return copy.deepcopy(self._persistence._read_events(directory, run_id))

    def start_visit(
        self,
        run_id: str,
        pipeline: PipelineConfig,
        phase_id: str,
        *,
        mutation_baseline: Any = None,
        deviations: list[Any] | None = None,
    ) -> VisitRecord:
        """Resolve visit inputs now and persist their literal immutable records."""

        directory = self.run_directory(run_id)
        with self._persistence.locked(directory, run_id) as (manifest, events):
            self._require_pipeline(manifest, pipeline)
            visit = self._new_visit(
                directory,
                manifest,
                pipeline,
                phase_id,
                status="active",
                mutation_baseline=mutation_baseline,
                deviations=deviations,
            )
            self._apply_decision_locked(
                directory, manifest, events, visit_transitions.append_visit(manifest, visit)
            )
            return copy.deepcopy(visit)

    create_visit = start_visit

    def prepare_visit(
        self,
        run_id: str,
        pipeline: PipelineConfig,
        phase_id: str,
        *,
        deviations: list[Any] | None = None,
    ) -> VisitRecord:
        """Create the next pending visit and resolve its immutable inputs."""

        directory = self.run_directory(run_id)
        with self._persistence.locked(directory, run_id) as (manifest, events):
            self._require_pipeline(manifest, pipeline)
            visit = self._new_visit(
                directory,
                manifest,
                pipeline,
                phase_id,
                status="pending",
                mutation_baseline=None,
                deviations=deviations,
            )
            self._apply_decision_locked(
                directory, manifest, events, visit_transitions.append_visit(manifest, visit)
            )
            return copy.deepcopy(visit)

    def activate_visit(
        self,
        run_id: str,
        pipeline: PipelineConfig,
        visit_number: int,
        *,
        mutation_baseline: Any = None,
    ) -> VisitRecord:
        """Activate a pending visit, returning an active visit unchanged on retry."""

        directory = self.run_directory(run_id)
        with self._persistence.locked(directory, run_id) as (manifest, events):
            self._require_pipeline(manifest, pipeline)
            needed = visit_transitions.activation_needed(manifest, visit_number)
            decision = visit_transitions.activate_visit(
                manifest, visit_number, mutation_baseline=mutation_baseline,
                started_at=self._timestamp() if needed else None,
            )
            updated = self._apply_decision_locked(directory, manifest, events, decision)
            return copy.deepcopy(self._visit(updated, visit_number))

    def write_visit_output(
        self, run_id: str, visit_number: int, content: str | bytes
    ) -> str:
        """Write an active visit output; completed outputs are immutable."""

        directory = self.run_directory(run_id)
        with self._persistence.locked(directory, run_id) as (manifest, _events):
            visit = self._visit(manifest, visit_number)
            if visit["status"] == "completed":
                raise ArtifactError(
                    "completed visit artifacts are immutable",
                    diagnostic_code="immutable-artifact",
                    details={"visit_number": visit_number},
                )
            return write_artifact_atomic(
                directory,
                visit["output"]["path"],
                content,
                replace=(directory / visit["output"]["path"]).exists(),
            )

    def record_validation_attempt(
        self,
        run_id: str,
        visit_number: int,
        *,
        validation_checks: list[Any] | None = None,
        command_results: list[Any] | None = None,
        mutation_result: Any = None,
        diagnostic: Mapping[str, Any] | None = None,
    ) -> RunRecord:
        """Persist resumable validation evidence without completing a visit."""

        def change(manifest: RunRecord) -> None:
            visit = self._visit(manifest, visit_number)
            if visit["status"] not in {"active", "awaiting-approval"}:
                raise RunStoreError(
                    "validation evidence can be recorded only for an active visit",
                    diagnostic_code="illegal-visit-status",
                    details={"visit_number": visit_number, "status": visit["status"]},
                    code=ExitCode.ILLEGAL_TRANSITION,
                )
            visit["validation_checks"] = list(validation_checks or [])
            visit["command_results"] = list(command_results or [])
            visit["mutation_result"] = mutation_result

        return self.mutate(
            run_id,
            "validation-failed",
            change,
            visit_number=visit_number,
            payload=dict(diagnostic or {}),
        )

    def complete_visit(
        self,
        run_id: str,
        visit_number: int,
        *,
        outcome: str | None = None,
        transition_target: str | None = None,
        mutation_result: Any = None,
        validation_checks: list[Any] | None = None,
        command_results: list[Any] | None = None,
        deviations: list[Any] | None = None,
    ) -> VisitRecord:
        """Seal an output hash and mark a visit completed without overwriting it."""

        directory = self.run_directory(run_id)
        with self._persistence.locked(directory, run_id) as (manifest, events):
            visit_transitions.require_incomplete(manifest, visit_number)
            existing = self._visit(manifest, visit_number)
            output = artifact_record(directory, existing["output"]["path"])
            sealed = visit_transitions.seal_visit(
                manifest, visit_number, output_sha256=output["sha256"],
                outcome=outcome, transition_target=transition_target,
                completed_at=self._timestamp(), mutation_result=mutation_result,
                validation_checks=validation_checks, command_results=command_results,
                deviations=deviations,
            )
            updated = self._apply_decision_locked(
                directory, manifest, events,
                visit_transitions.completion_decision(sealed, visit_number),
            )
            return copy.deepcopy(self._visit(updated, visit_number))

    def transition_visit(
        self,
        run_id: str,
        pipeline: PipelineConfig,
        visit_number: int,
        *,
        outcome: str,
        transition_target: str | None,
        terminal_result: Any = None,
        validation_checks: list[Any] | None = None,
        command_results: list[Any] | None = None,
        mutation_result: Any = None,
    ) -> RunRecord:
        """Complete a visit and atomically prepare its configured successor."""

        directory = self.run_directory(run_id)
        with self._persistence.locked(directory, run_id) as (manifest, events):
            self._require_pipeline(manifest, pipeline)
            if not visit_transitions.transition_needed(
                manifest, visit_number, outcome, transition_target
            ):
                return self._apply_decision_locked(
                    directory, manifest, events,
                    visit_transitions.Decision(copy.deepcopy(manifest)),
                )
            existing = self._visit(manifest, visit_number)
            output = artifact_record(directory, existing["output"]["path"])
            transition = next(
                item
                for item in pipeline.phase(existing["phase_id"]).transitions
                if item.outcome == outcome
            )
            limit_block = self._transition_limit_block(
                manifest, pipeline, existing, outcome, transition_target
            )
            if limit_block is not None:
                decision = visit_transitions.blocked_transition(
                    manifest, visit_number, limit_block,
                    mutation_result=mutation_result, validation_checks=validation_checks,
                    command_results=command_results,
                )
            else:
                sealed = visit_transitions.seal_visit(
                    manifest, visit_number, output_sha256=output["sha256"],
                    outcome=outcome, transition_target=transition_target,
                    completed_at=self._timestamp(), mutation_result=mutation_result,
                    validation_checks=validation_checks, command_results=command_results,
                )
                # Resolve latest/visit inputs against the sealed proposal while
                # retaining the lock. Completion and successor commit only once.
                next_visit = None
                if transition_target is not None:
                    next_visit = self._new_visit(
                        directory, sealed, pipeline, transition_target,
                        status="pending", mutation_baseline=None,
                    )
                decision = visit_transitions.finish_transition(
                    sealed, visit_number, next_visit=next_visit,
                    pause=transition.pause, terminal_result=terminal_result,
                )
            return self._apply_decision_locked(directory, manifest, events, decision)

    def resume_paused(self, run_id: str, pipeline: PipelineConfig) -> RunRecord:
        """Release a durable checkpoint without starting its pending visit."""

        directory = self.run_directory(run_id)
        with self._persistence.locked(directory, run_id) as (manifest, events):
            self._require_pipeline(manifest, pipeline)
            return self._apply_decision_locked(
                directory, manifest, events, visit_transitions.resume_paused(manifest)
            )

    def decide_approval(
        self, run_id: str,
        decide: Callable[[RunRecord], approvals.ApprovalDecision],
    ) -> approvals.ApprovalDecision:
        """Resolve a bound approval against current state under one run lock."""

        directory = self.run_directory(run_id)
        with self._persistence.locked(directory, run_id) as (manifest, events):
            decision = decide(copy.deepcopy(manifest))
            decision.manifest = self._apply_decision_locked(
                directory, manifest, events, decision,
            )
            return copy.deepcopy(decision)

    def _apply_decision_locked(
        self, directory: Path, previous: RunRecord, events: list[EventRecord],
        decision: visit_transitions.Decision | approvals.ApprovalDecision,
    ) -> RunRecord:
        """Stamp and commit a proposal under the caller's existing run lock."""

        updated = decision.manifest
        if decision.event_type is not None:
            self._persistence.advance_revision(updated, previous["revision"])
            self._persistence.commit_locked(
                directory, updated, events, decision.event_type,
                decision.visit_number, decision.payload,
            )
        return copy.deepcopy(updated)

    def _transition_limit_block(
        self,
        manifest: RunRecord,
        pipeline: PipelineConfig,
        visit: VisitRecord,
        outcome: str,
        transition_target: str | None,
    ) -> dict[str, Any] | None:
        return visit_transitions.transition_limit_block(
            manifest, pipeline, visit, outcome, transition_target,
            timestamp=self._timestamp(),
        )

    def mutate(
        self,
        run_id: str,
        event_type: str,
        mutator: Callable[[RunRecord], None],
        *,
        visit_number: int | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> RunRecord:
        """Apply a validated in-memory mutation using the store's commit protocol."""

        if not EVENT_TYPE_PATTERN.fullmatch(event_type):
            raise ValueError(f"invalid event type: {event_type!r}")
        directory = self.run_directory(run_id)
        with self._persistence.locked(directory, run_id) as (manifest, events):
            updated = copy.deepcopy(manifest)
            mutator(updated)
            self._persistence.advance_revision(updated, manifest["revision"])
            self._persistence.commit_locked(
                directory,
                updated,
                events,
                event_type,
                visit_number,
                dict(payload or {}),
            )
            return copy.deepcopy(updated)

    update = mutate

    def block(self, run_id: str, reason: Any) -> RunRecord:
        def change(manifest: RunRecord) -> None:
            manifest["status"] = "blocked"
            manifest["block_reason"] = reason

        return self.mutate(
            run_id, "run-blocked", change, payload={"reason": reason}
        )

    def complete(self, run_id: str, result: Any) -> RunRecord:
        def change(manifest: RunRecord) -> None:
            manifest["status"] = "completed"
            manifest["terminal_result"] = result

        return self.mutate(
            run_id, "run-completed", change, payload={"result": result}
        )

    def _new_visit(
        self,
        directory: Path,
        manifest: RunRecord,
        pipeline: PipelineConfig,
        phase_id: str,
        *,
        status: str,
        mutation_baseline: Any,
        deviations: list[Any] | None = None,
    ) -> VisitRecord:
        if status not in {"pending", "active"}:
            raise ValueError(f"invalid initial visit status: {status!r}")
        try:
            phase = pipeline.phase(phase_id)
        except KeyError as exc:
            raise RunStoreError(
                f"pipeline has no phase {phase_id!r}",
                diagnostic_code="phase-not-found",
                details={"phase": phase_id},
                code=ExitCode.NOT_FOUND,
            ) from exc
        ordinal = len(manifest["visits"]) + 1
        attempt = sum(
            visit["phase_id"] == phase_id for visit in manifest["visits"]
        ) + 1
        resources = visit_preparation.collect_resources(
            directory, manifest, pipeline, phase,
            repository_root=self.repository_root, ordinal=ordinal,
        )
        return visit_transitions.new_visit(
            phase_id=phase_id, ordinal=ordinal, attempt=attempt, status=status,
            inputs=resources.inputs, output_path=resources.output_path,
            mutation_policy=phase.mutation, mutation_baseline=mutation_baseline,
            skill=resources.skill, template=resources.template,
            started_at=self._timestamp() if status == "active" else None,
            deviations=deviations,
        )

    def _prepare_runs_root(self) -> None:
        self.runs_root.mkdir(parents=True, exist_ok=True)
        resolved = self.runs_root.resolve(strict=True)
        if not resolved.is_relative_to(self.repository_root) or resolved != self.runs_root.absolute():
            raise RunStoreError(
                "run storage is a symlink or escapes the repository",
                diagnostic_code="unsafe-run-storage",
                details={"path": str(self.runs_root)},
            )

    def _timestamp(self) -> str:
        return format_timestamp(self._clock())

    def _fault(self, point: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(point)

    def _require_pipeline(
        self, manifest: RunRecord, pipeline: PipelineConfig
    ) -> None:
        expected = manifest["pipeline"]
        actual_path = relative_path(pipeline.path, self.repository_root)
        if (
            expected["id"] != pipeline.id
            or expected["version"] != pipeline.version
            or expected["path"] != actual_path
            or expected["sha256"] != pipeline.config_hash
        ):
            raise RunStoreError(
                "pipeline configuration changed after the run was created",
                diagnostic_code="pipeline-hash-mismatch",
                details={
                    "expected": expected,
                    "actual": {
                        "id": pipeline.id,
                        "version": pipeline.version,
                        "path": actual_path,
                        "sha256": pipeline.config_hash,
                    },
                },
                code=ExitCode.INVALID_PIPELINE,
            )

    _visit = staticmethod(visit_by_number)

    def _validate_manifest(self, value: dict[str, Any], run_id: str) -> None:
        run_validation.validate_manifest(value, run_id)

    def _validate_visit(
        self, visit: dict[str, Any], run_id: str, expected_ordinal: int
    ) -> None:
        run_validation.validate_visit(visit, run_id, expected_ordinal)

    def _validate_artifact_record(
        self,
        value: Any,
        run_id: str,
        *,
        hash_required: bool,
        reference: bool = False,
    ) -> None:
        run_validation.validate_artifact_record(
            value, run_id, hash_required=hash_required, reference=reference
        )

    def _validate_provenance(self, value: dict[str, Any], run_id: str) -> None:
        run_validation.validate_provenance(value, run_id)

    def _validate_event(self, event: dict[str, Any], run_id: str) -> None:
        run_validation.validate_event(event, run_id)

    @staticmethod
    def _validate_timestamp(value: Any, run_id: str) -> None:
        run_validation.validate_timestamp(value, run_id)

    @staticmethod
    def _validate_path(value: Any, run_id: str) -> None:
        run_validation.validate_path(value, run_id)

    @staticmethod
    def _invalid_manifest(run_id: str, message: str) -> None:
        run_validation.invalid_manifest(run_id, message)


new_run_id = generate_run_id
CorruptRunError = RunCorruptionError
