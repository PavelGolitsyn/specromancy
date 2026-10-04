"""Recoverable, disk-backed run manifests and append-only audit events."""

from __future__ import annotations

import copy
import json
import os
import secrets
import tempfile
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
from .config_models import PipelineConfig
from .exit_codes import ExitCode
from .hashing import (
    relative_path,
    resolve_relative_path,
    sha256_file,
    sha256_json,
)
from .locking import RunLock
from . import run_validation
from .run_errors import RunCorruptionError, RunNotFoundError, RunStoreError
from .run_identity import (
    RUN_ID_PATTERN, format_timestamp, generate_run_id, is_valid_run_id,
    utc_now, validate_run_id,
)
from .run_records import (
    EVENT_SCHEMA_VERSION, EVENT_TYPE_PATTERN, RUN_SCHEMA_VERSION,
    RUN_STATUSES, VISIT_STATUSES, EventRecord, RunRecord, VisitRecord,
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
        return RunLock(directory / ".lock", clock=self._clock)

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

        with RunLock(directory / ".lock", clock=self._clock):
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
            self._validate_manifest(manifest, chosen_id)
            self._write_manifest_atomic(directory, manifest)
            event = self._event(
                manifest,
                sequence=1,
                event_type="run-created",
                visit_number=None,
                payload={"pipeline_id": pipeline.id},
            )
            self._append_event(directory, event)
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
        with RunLock(directory / ".lock", clock=self._clock):
            manifest = self._read_manifest(directory, run_id)
            if recover:
                self._ensure_event_consistency(directory, manifest)
            else:
                self._assert_event_consistency(directory, manifest)
            if verify_artifacts:
                try:
                    verify_manifest_artifacts(manifest, directory)
                except ArtifactError:
                    raise
        return copy.deepcopy(manifest)

    load_run = load

    def read_events(self, run_id: str, *, recover: bool = True) -> list[EventRecord]:
        directory = self.run_directory(run_id)
        with RunLock(directory / ".lock", clock=self._clock):
            manifest = self._read_manifest(directory, run_id)
            if recover:
                self._ensure_event_consistency(directory, manifest)
            else:
                self._assert_event_consistency(directory, manifest)
            return copy.deepcopy(self._read_events(directory, run_id))

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
        with RunLock(directory / ".lock", clock=self._clock):
            manifest = self._read_manifest(directory, run_id)
            events = self._ensure_event_consistency(directory, manifest)
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
            ordinal = visit["ordinal"]
            updated = copy.deepcopy(manifest)
            updated["revision"] += 1
            updated["updated_at"] = self._timestamp()
            updated["status"] = "active"
            updated["current_visit"] = ordinal
            updated["visits"].append(visit)
            self._commit_locked(
                directory,
                updated,
                events,
                "visit-started",
                ordinal,
                {"phase_id": phase_id, "attempt": visit["attempt"]},
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
        with RunLock(directory / ".lock", clock=self._clock):
            manifest = self._read_manifest(directory, run_id)
            events = self._ensure_event_consistency(directory, manifest)
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
            updated = copy.deepcopy(manifest)
            updated["revision"] += 1
            updated["updated_at"] = self._timestamp()
            updated["status"] = "awaiting-agent"
            updated["current_visit"] = visit["ordinal"]
            updated["visits"].append(visit)
            self._commit_locked(
                directory,
                updated,
                events,
                "visit-prepared",
                visit["ordinal"],
                {"phase_id": phase_id, "attempt": visit["attempt"]},
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
        with RunLock(directory / ".lock", clock=self._clock):
            manifest = self._read_manifest(directory, run_id)
            events = self._ensure_event_consistency(directory, manifest)
            self._require_pipeline(manifest, pipeline)
            if manifest["status"] == "paused":
                raise RunStoreError(
                    "paused run must be resumed before its next visit can start",
                    diagnostic_code="run-paused",
                    details={"run_id": run_id, "visit_number": visit_number},
                    code=ExitCode.RUN_PAUSED,
                )
            existing = self._visit(manifest, visit_number)
            if existing["status"] == "active":
                return copy.deepcopy(existing)
            if existing["status"] != "pending":
                raise RunStoreError(
                    f"visit {visit_number} cannot be activated from {existing['status']}",
                    diagnostic_code="illegal-visit-status",
                    details={
                        "visit_number": visit_number,
                        "status": existing["status"],
                        "expected": "pending",
                    },
                    code=ExitCode.ILLEGAL_TRANSITION,
                )
            updated = copy.deepcopy(manifest)
            visit = self._visit(updated, visit_number)
            visit["status"] = "active"
            visit["mutation_baseline"] = mutation_baseline
            visit["started_at"] = self._timestamp()
            updated["revision"] += 1
            updated["updated_at"] = self._timestamp()
            updated["status"] = "active"
            self._commit_locked(
                directory,
                updated,
                events,
                "visit-activated",
                visit_number,
                {"phase_id": visit["phase_id"]},
            )
            return copy.deepcopy(visit)

    def write_visit_output(
        self, run_id: str, visit_number: int, content: str | bytes
    ) -> str:
        """Write an active visit output; completed outputs are immutable."""

        directory = self.run_directory(run_id)
        with RunLock(directory / ".lock", clock=self._clock):
            manifest = self._read_manifest(directory, run_id)
            self._ensure_event_consistency(directory, manifest)
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
        with RunLock(directory / ".lock", clock=self._clock):
            manifest = self._read_manifest(directory, run_id)
            events = self._ensure_event_consistency(directory, manifest)
            existing = self._visit(manifest, visit_number)
            if existing["status"] == "completed":
                raise RunStoreError(
                    f"visit {visit_number} is already completed",
                    diagnostic_code="visit-already-completed",
                    details={"visit_number": visit_number},
                    code=ExitCode.ILLEGAL_TRANSITION,
                )
            output = artifact_record(directory, existing["output"]["path"])
            updated = copy.deepcopy(manifest)
            visit = self._visit(updated, visit_number)
            visit["status"] = "completed"
            visit["output"]["sha256"] = output["sha256"]
            visit["mutation_result"] = mutation_result
            visit["validation_checks"] = list(validation_checks or [])
            visit["command_results"] = list(command_results or [])
            visit["chosen_outcome"] = outcome
            visit["transition_target"] = transition_target
            visit["completed_at"] = self._timestamp()
            if isinstance(mutation_result, dict) and isinstance(
                mutation_result.get("head"), dict
            ):
                updated["git"]["head"] = mutation_result["head"]
            if deviations is not None:
                visit["deviations"] = list(deviations)
            updated["revision"] += 1
            updated["updated_at"] = self._timestamp()
            self._commit_locked(
                directory,
                updated,
                events,
                "visit-completed",
                visit_number,
                {"phase_id": visit["phase_id"], "outcome": outcome},
            )
            return copy.deepcopy(visit)

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
        with RunLock(directory / ".lock", clock=self._clock):
            manifest = self._read_manifest(directory, run_id)
            events = self._ensure_event_consistency(directory, manifest)
            self._require_pipeline(manifest, pipeline)
            existing = self._visit(manifest, visit_number)
            if existing["status"] == "completed":
                if (
                    existing["chosen_outcome"] == outcome
                    and existing["transition_target"] == transition_target
                ):
                    return copy.deepcopy(manifest)
                raise RunStoreError(
                    f"visit {visit_number} already completed with another transition",
                    diagnostic_code="visit-already-completed",
                    details={"visit_number": visit_number},
                    code=ExitCode.ILLEGAL_TRANSITION,
                )
            if existing["status"] not in {"active", "awaiting-approval"}:
                raise RunStoreError(
                    f"visit {visit_number} cannot complete from {existing['status']}",
                    diagnostic_code="illegal-visit-status",
                    details={
                        "visit_number": visit_number,
                        "status": existing["status"],
                    },
                    code=ExitCode.ILLEGAL_TRANSITION,
                )
            output = artifact_record(directory, existing["output"]["path"])
            updated = copy.deepcopy(manifest)
            visit = self._visit(updated, visit_number)
            transition = next(
                item
                for item in pipeline.phase(visit["phase_id"]).transitions
                if item.outcome == outcome
            )
            limit_block = self._transition_limit_block(
                manifest, pipeline, visit, outcome, transition_target
            )
            if limit_block is not None:
                visit["status"] = "blocked"
                visit["mutation_result"] = mutation_result
                visit["validation_checks"] = list(validation_checks or [])
                visit["command_results"] = list(command_results or [])
                updated["status"] = "blocked"
                updated["block_reason"] = limit_block
                if isinstance(mutation_result, dict) and isinstance(
                    mutation_result.get("head"), dict
                ):
                    updated["git"]["head"] = mutation_result["head"]
                updated["revision"] += 1
                updated["updated_at"] = self._timestamp()
                self._commit_locked(
                    directory,
                    updated,
                    events,
                    "loop-limit-exceeded",
                    visit_number,
                    limit_block,
                )
                return copy.deepcopy(updated)
            visit["status"] = "completed"
            visit["output"]["sha256"] = output["sha256"]
            visit["mutation_result"] = mutation_result
            visit["validation_checks"] = list(validation_checks or [])
            visit["command_results"] = list(command_results or [])
            visit["chosen_outcome"] = outcome
            visit["transition_target"] = transition_target
            visit["completed_at"] = self._timestamp()
            if isinstance(mutation_result, dict) and isinstance(
                mutation_result.get("head"), dict
            ):
                updated["git"]["head"] = mutation_result["head"]

            next_visit = None
            if transition_target is None:
                updated["status"] = "completed"
                updated["terminal_result"] = (
                    terminal_result
                    if terminal_result is not None
                    else {"outcome": outcome, "visit_number": visit_number}
                )
            else:
                next_visit = self._new_visit(
                    directory,
                    updated,
                    pipeline,
                    transition_target,
                    status="pending",
                    mutation_baseline=None,
                )
                updated["visits"].append(next_visit)
                updated["current_visit"] = next_visit["ordinal"]
                updated["status"] = "paused" if transition.pause else "awaiting-agent"
            updated["revision"] += 1
            updated["updated_at"] = self._timestamp()
            self._commit_locked(
                directory,
                updated,
                events,
                "visit-transitioned",
                visit_number,
                {
                    "phase_id": visit["phase_id"],
                    "outcome": outcome,
                    "target": transition_target,
                    "paused": transition.pause,
                    "next_visit": (
                        next_visit["ordinal"] if next_visit is not None else None
                    ),
                },
            )
            return copy.deepcopy(updated)

    def resume_paused(self, run_id: str, pipeline: PipelineConfig) -> RunRecord:
        """Release a durable checkpoint without starting its pending visit."""

        directory = self.run_directory(run_id)
        with RunLock(directory / ".lock", clock=self._clock):
            manifest = self._read_manifest(directory, run_id)
            events = self._ensure_event_consistency(directory, manifest)
            self._require_pipeline(manifest, pipeline)
            if manifest["status"] != "paused":
                return copy.deepcopy(manifest)
            visit_number = manifest["current_visit"]
            if visit_number is None:
                raise RunCorruptionError(
                    "paused run has no current visit", run_id=run_id
                )
            current = self._visit(manifest, visit_number)
            if current["status"] != "pending":
                raise RunCorruptionError(
                    "paused run does not point to a pending visit", run_id=run_id
                )
            updated = copy.deepcopy(manifest)
            updated["status"] = "awaiting-agent"
            updated["revision"] += 1
            updated["updated_at"] = self._timestamp()
            self._commit_locked(
                directory,
                updated,
                events,
                "run-resumed",
                visit_number,
                {"phase_id": current["phase_id"]},
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
        """Return a persisted block record before a disallowed loop traversal."""

        phase = pipeline.phase(visit["phase_id"])
        transition = next(
            item for item in phase.transitions if item.outcome == outcome
        )
        timestamp = self._timestamp()
        if transition.max_traversals is not None:
            traversals = sum(
                item["phase_id"] == phase.id
                and item.get("chosen_outcome") == outcome
                for item in manifest["visits"]
            )
            if traversals >= transition.max_traversals:
                return {
                    "reason": "transition-traversal-limit",
                    "phase_id": phase.id,
                    "visit_number": visit["ordinal"],
                    "outcome": outcome,
                    "target": transition_target,
                    "limit": transition.max_traversals,
                    "recorded_at": timestamp,
                    "required_action": "new-run",
                    "remediation": "start a new run; this pipeline declares no counter-reset approval",
                }
        if transition_target is not None:
            target_phase = pipeline.phase(transition_target)
            if target_phase.max_visits is not None:
                visits = sum(
                    item["phase_id"] == transition_target
                    for item in manifest["visits"]
                )
                if visits >= target_phase.max_visits:
                    return {
                        "reason": "phase-visit-limit",
                        "phase_id": transition_target,
                        "source_phase": phase.id,
                        "visit_number": visit["ordinal"],
                        "outcome": outcome,
                        "limit": target_phase.max_visits,
                        "recorded_at": timestamp,
                        "required_action": "new-run",
                        "remediation": "start a new run; this pipeline declares no counter-reset approval",
                    }
        return None

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
        with RunLock(directory / ".lock", clock=self._clock):
            manifest = self._read_manifest(directory, run_id)
            events = self._ensure_event_consistency(directory, manifest)
            updated = copy.deepcopy(manifest)
            mutator(updated)
            updated["revision"] = manifest["revision"] + 1
            updated["updated_at"] = self._timestamp()
            self._commit_locked(
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
        inputs = [
            resolve_input_reference(reference, manifest, directory)
            for reference in phase.inputs
        ]
        output_path = render_output_path(pipeline, phase, ordinal)
        reserved_paths = {visit["output"]["path"] for visit in manifest["visits"]}
        if output_path in reserved_paths or (directory / output_path).exists():
            raise ArtifactError(
                f"visit output path would overwrite an earlier artifact: {output_path}",
                diagnostic_code="artifact-path-collision",
                details={"path": output_path, "visit_number": ordinal},
            )
        skill = {
            "path": relative_path(phase.skill_path, self.repository_root),
            "sha256": sha256_file(phase.skill_path),
        }
        template = None
        if phase.output_template_path is not None:
            template = {
                "path": relative_path(phase.output_template_path, self.repository_root),
                "sha256": sha256_file(phase.output_template_path),
            }
        return {
            "phase_id": phase_id,
            "ordinal": ordinal,
            "attempt": attempt,
            "status": status,
            "inputs": inputs,
            "output": {"path": output_path, "sha256": None},
            "mutation_policy": phase.mutation,
            "mutation_baseline": mutation_baseline,
            "mutation_result": None,
            "validation_checks": [],
            "command_results": [],
            "chosen_outcome": None,
            "transition_target": None,
            "skill": skill,
            "template": template,
            "started_at": self._timestamp() if status == "active" else None,
            "completed_at": None,
            "deviations": list(deviations or []),
        }

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

    def _read_manifest(self, directory: Path, run_id: str) -> RunRecord:
        path = directory / "run.json"
        try:
            raw = path.read_text(encoding="utf-8")
            value = json.loads(raw)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RunCorruptionError(
                "run manifest is missing, unreadable, or malformed",
                run_id=run_id,
                details={"path": str(path), "error": str(exc)},
            ) from exc
        if not isinstance(value, dict):
            raise RunCorruptionError(
                "run manifest must be a JSON object", run_id=run_id
            )
        self._validate_manifest(value, run_id)
        return value

    def _write_manifest_atomic(
        self, directory: Path, manifest: RunRecord
    ) -> None:
        target = directory / "run.json"
        self._fault("before-manifest-temporary-write")
        descriptor, temporary_name = tempfile.mkstemp(
            dir=directory, prefix=".run.json.", suffix=".tmp"
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    manifest,
                    stream,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    indent=2,
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._fault("after-manifest-temporary-write")
            self._fault("before-manifest-replace")
            os.replace(temporary, target)
            self._fsync_directory(directory)
            self._fault("after-manifest-replace")
        finally:
            temporary.unlink(missing_ok=True)

    def _append_event(self, directory: Path, event: EventRecord) -> None:
        self._validate_event(event, event["run_id"])
        path = directory / "events.jsonl"
        payload = (
            json.dumps(
                event,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        self._fault("before-event-append")
        try:
            with path.open("ab") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise RunCorruptionError(
                "could not append the run audit event",
                run_id=event["run_id"],
                details={"path": str(path), "error": str(exc)},
            ) from exc
        self._fault("after-event-append")

    def _read_events(self, directory: Path, run_id: str) -> list[EventRecord]:
        path = directory / "events.jsonl"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise RunCorruptionError(
                "run event log is missing or unreadable",
                run_id=run_id,
                details={"path": str(path), "error": str(exc)},
            ) from exc
        events: list[EventRecord] = []
        for index, line in enumerate(lines, 1):
            if not line:
                raise RunCorruptionError(
                    "run event log contains an empty record",
                    run_id=run_id,
                    details={"line": index},
                )
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RunCorruptionError(
                    "run event log contains malformed JSON",
                    run_id=run_id,
                    details={"line": index, "error": str(exc)},
                ) from exc
            if not isinstance(event, dict):
                raise RunCorruptionError(
                    "run event must be a JSON object",
                    run_id=run_id,
                    details={"line": index},
                )
            self._validate_event(event, run_id)
            if event["sequence"] != index:
                raise RunCorruptionError(
                    "run event sequence is not contiguous",
                    run_id=run_id,
                    details={"line": index, "sequence": event["sequence"]},
                )
            if event["manifest_revision"] != index:
                raise RunCorruptionError(
                    "run event revisions are not contiguous",
                    run_id=run_id,
                    details={
                        "line": index,
                        "manifest_revision": event["manifest_revision"],
                    },
                )
            events.append(event)
        return events

    def _ensure_event_consistency(
        self, directory: Path, manifest: RunRecord
    ) -> list[EventRecord]:
        events = self._read_events(directory, manifest["run_id"])
        if self._events_match_manifest(events, manifest):
            return events
        last_revision = events[-1]["manifest_revision"] if events else 0
        if last_revision == manifest["revision"] - 1:
            event = self._event(
                manifest,
                sequence=len(events) + 1,
                event_type="recovery",
                visit_number=manifest["current_visit"],
                payload={
                    "reason": "manifest-event-gap",
                    "previous_sequence": len(events),
                    "previous_manifest_revision": last_revision,
                },
            )
            self._append_event(directory, event)
            events.append(event)
            return events
        raise RunCorruptionError(
            "manifest and event log disagree in a way that cannot be recovered",
            run_id=manifest["run_id"],
            details={
                "manifest_revision": manifest["revision"],
                "last_event_revision": last_revision,
            },
        )

    def _assert_event_consistency(
        self, directory: Path, manifest: RunRecord
    ) -> None:
        events = self._read_events(directory, manifest["run_id"])
        if not self._events_match_manifest(events, manifest):
            raise RunCorruptionError(
                "manifest is newer than its final audit event; recovery is required",
                run_id=manifest["run_id"],
                details={"recoverable": True},
            )

    @staticmethod
    def _events_match_manifest(
        events: list[EventRecord], manifest: RunRecord
    ) -> bool:
        if not events:
            return False
        final = events[-1]
        return (
            final["manifest_revision"] == manifest["revision"]
            and final["manifest_hash"] == sha256_json(manifest)
        )

    def _commit_locked(
        self,
        directory: Path,
        manifest: RunRecord,
        events: list[EventRecord],
        event_type: str,
        visit_number: int | None,
        payload: dict[str, Any],
    ) -> None:
        run_id = manifest["run_id"]
        self._validate_manifest(manifest, run_id)
        self._write_manifest_atomic(directory, manifest)
        event = self._event(
            manifest,
            sequence=len(events) + 1,
            event_type=event_type,
            visit_number=visit_number,
            payload=payload,
        )
        self._append_event(directory, event)

    def _event(
        self,
        manifest: RunRecord,
        *,
        sequence: int,
        event_type: str,
        visit_number: int | None,
        payload: dict[str, Any],
    ) -> EventRecord:
        return {
            "schema_version": EVENT_SCHEMA_VERSION,
            "sequence": sequence,
            "timestamp": self._timestamp(),
            "run_id": manifest["run_id"],
            "visit_number": visit_number,
            "type": event_type,
            "payload": payload,
            "manifest_revision": manifest["revision"],
            "manifest_hash": sha256_json(manifest),
        }

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

    @staticmethod
    def _visit(manifest: RunRecord, visit_number: int) -> VisitRecord:
        for visit in manifest["visits"]:
            if visit["ordinal"] == visit_number:
                return visit
        raise RunStoreError(
            f"visit not found: {visit_number}",
            diagnostic_code="visit-not-found",
            details={"visit_number": visit_number},
            code=ExitCode.NOT_FOUND,
        )

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

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


new_run_id = generate_run_id
CorruptRunError = RunCorruptionError
