"""Recoverable, disk-backed run manifests and append-only audit events."""

from __future__ import annotations

import copy
import inspect
import json
import os
import re
import secrets
import tempfile
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
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
from .config import PipelineConfig
from .errors import SpecromancyError
from .exit_codes import ExitCode
from .hashing import (
    SHA256_PATTERN,
    normalize_relative_path,
    relative_path,
    resolve_relative_path,
    sha256_file,
    sha256_json,
)
from .locking import RunLock


RUN_SCHEMA_VERSION = 1
EVENT_SCHEMA_VERSION = 1
RUN_ID_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
EVENT_TYPE_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RUN_STATUSES = frozenset(
    {"pending", "active", "awaiting-approval", "completed", "failed", "blocked"}
)
VISIT_STATUSES = RUN_STATUSES


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def validate_run_id(run_id: str) -> str:
    """Return a valid path-safe run ID or raise ``ValueError``."""

    if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(f"invalid run ID: {run_id!r}")
    try:
        datetime.strptime(run_id[:16], "%Y%m%dT%H%M%SZ")
    except ValueError as exc:
        raise ValueError(f"invalid run ID timestamp: {run_id!r}") from exc
    return run_id


def is_valid_run_id(run_id: str) -> bool:
    try:
        validate_run_id(run_id)
    except (TypeError, ValueError):
        return False
    return True


def generate_run_id(
    *,
    clock: Callable[[], datetime] = utc_now,
    random_source: Callable[..., bytes | str] = secrets.token_bytes,
) -> str:
    """Generate a UTC timestamp plus four cryptographically random bytes."""

    now = clock()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    timestamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        inspect.signature(random_source).bind(4)
    except (TypeError, ValueError):
        random_value = random_source()
    else:
        random_value = random_source(4)
    suffix = random_value.hex() if isinstance(random_value, bytes) else random_value
    run_id = f"{timestamp}-{suffix}"
    return validate_run_id(run_id)


class RunStoreError(SpecromancyError):
    """Base error for expected run-store failures."""

    def __init__(
        self,
        message: str,
        *,
        diagnostic_code: str,
        details: Mapping[str, Any] | None = None,
        code: ExitCode = ExitCode.INTERNAL_ERROR,
    ) -> None:
        values = {"error_code": diagnostic_code}
        if details:
            values.update(details)
        super().__init__(code, message, values)
        self.diagnostic_code = diagnostic_code


class RunNotFoundError(RunStoreError):
    def __init__(self, run_id: str) -> None:
        super().__init__(
            f"run not found: {run_id}",
            diagnostic_code="run-not-found",
            details={"run_id": run_id},
            code=ExitCode.NOT_FOUND,
        )


class RunCorruptionError(RunStoreError):
    def __init__(
        self, message: str, *, run_id: str, details: Mapping[str, Any] | None = None
    ) -> None:
        values: dict[str, Any] = {"run_id": run_id}
        if details:
            values.update(details)
        super().__init__(
            message,
            diagnostic_code="corrupt-run",
            details=values,
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
    ) -> dict[str, Any]:
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
            manifest: dict[str, Any] = {
                "schema_version": RUN_SCHEMA_VERSION,
                "revision": 1,
                "run_id": chosen_id,
                "pipeline": {
                    "id": pipeline.id,
                    "version": pipeline.version,
                    "path": relative_path(pipeline.path, self.repository_root),
                    "sha256": pipeline.config_hash,
                },
                "status": "pending",
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
    ) -> dict[str, Any]:
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

    def read_events(self, run_id: str, *, recover: bool = True) -> list[dict[str, Any]]:
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
    ) -> dict[str, Any]:
        """Resolve visit inputs now and persist their literal immutable records."""

        directory = self.run_directory(run_id)
        with RunLock(directory / ".lock", clock=self._clock):
            manifest = self._read_manifest(directory, run_id)
            events = self._ensure_event_consistency(directory, manifest)
            self._require_pipeline(manifest, pipeline)
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
            reserved_paths = {
                visit["output"]["path"] for visit in manifest["visits"]
            }
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
                    "path": relative_path(
                        phase.output_template_path, self.repository_root
                    ),
                    "sha256": sha256_file(phase.output_template_path),
                }
            visit = {
                "phase_id": phase_id,
                "ordinal": ordinal,
                "attempt": attempt,
                "status": "active",
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
                "started_at": self._timestamp(),
                "completed_at": None,
                "deviations": list(deviations or []),
            }
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
                {"phase_id": phase_id, "attempt": attempt},
            )
            return copy.deepcopy(visit)

    create_visit = start_visit

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
    ) -> dict[str, Any]:
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

    def mutate(
        self,
        run_id: str,
        event_type: str,
        mutator: Callable[[dict[str, Any]], None],
        *,
        visit_number: int | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
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

    def block(self, run_id: str, reason: Any) -> dict[str, Any]:
        def change(manifest: dict[str, Any]) -> None:
            manifest["status"] = "blocked"
            manifest["block_reason"] = reason

        return self.mutate(
            run_id, "run-blocked", change, payload={"reason": reason}
        )

    def complete(self, run_id: str, result: Any) -> dict[str, Any]:
        def change(manifest: dict[str, Any]) -> None:
            manifest["status"] = "completed"
            manifest["terminal_result"] = result

        return self.mutate(
            run_id, "run-completed", change, payload={"result": result}
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

    def _read_manifest(self, directory: Path, run_id: str) -> dict[str, Any]:
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
        self, directory: Path, manifest: dict[str, Any]
    ) -> None:
        target = directory / "run.json"
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
            self._fault("before-manifest-replace")
            os.replace(temporary, target)
            self._fsync_directory(directory)
            self._fault("after-manifest-replace")
        finally:
            temporary.unlink(missing_ok=True)

    def _append_event(self, directory: Path, event: dict[str, Any]) -> None:
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

    def _read_events(self, directory: Path, run_id: str) -> list[dict[str, Any]]:
        path = directory / "events.jsonl"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise RunCorruptionError(
                "run event log is missing or unreadable",
                run_id=run_id,
                details={"path": str(path), "error": str(exc)},
            ) from exc
        events: list[dict[str, Any]] = []
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
            events.append(event)
        return events

    def _ensure_event_consistency(
        self, directory: Path, manifest: dict[str, Any]
    ) -> list[dict[str, Any]]:
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
        self, directory: Path, manifest: dict[str, Any]
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
        events: list[dict[str, Any]], manifest: dict[str, Any]
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
        manifest: dict[str, Any],
        events: list[dict[str, Any]],
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
        manifest: dict[str, Any],
        *,
        sequence: int,
        event_type: str,
        visit_number: int | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
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
        self, manifest: dict[str, Any], pipeline: PipelineConfig
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
    def _visit(manifest: dict[str, Any], visit_number: int) -> dict[str, Any]:
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
        required = {
            "schema_version",
            "revision",
            "run_id",
            "pipeline",
            "status",
            "current_visit",
            "request",
            "git",
            "created_at",
            "updated_at",
            "visits",
            "approvals",
            "terminal_result",
            "block_reason",
        }
        if set(value) != required:
            self._invalid_manifest(run_id, "manifest fields do not match the schema")
        if value["schema_version"] != RUN_SCHEMA_VERSION:
            self._invalid_manifest(run_id, "unsupported run schema version")
        if not isinstance(value["revision"], int) or value["revision"] < 1:
            self._invalid_manifest(run_id, "manifest revision must be positive")
        if value["run_id"] != run_id or not is_valid_run_id(value["run_id"]):
            self._invalid_manifest(run_id, "manifest run ID is invalid")
        if value["status"] not in RUN_STATUSES:
            self._invalid_manifest(run_id, "manifest status is invalid")
        self._validate_timestamp(value["created_at"], run_id)
        self._validate_timestamp(value["updated_at"], run_id)
        pipeline = value["pipeline"]
        if not isinstance(pipeline, dict) or set(pipeline) != {
            "id",
            "version",
            "path",
            "sha256",
        }:
            self._invalid_manifest(run_id, "pipeline record is invalid")
        if (
            not isinstance(pipeline["id"], str)
            or not isinstance(pipeline["version"], int)
            or pipeline["version"] < 1
            or not isinstance(pipeline["sha256"], str)
            or not SHA256_PATTERN.fullmatch(pipeline["sha256"])
        ):
            self._invalid_manifest(run_id, "pipeline provenance is invalid")
        self._validate_path(pipeline["path"], run_id)
        self._validate_artifact_record(value["request"], run_id, hash_required=True)
        if not isinstance(value["git"], dict) or set(value["git"]) != {"base", "head"}:
            self._invalid_manifest(run_id, "git metadata is invalid")
        if not isinstance(value["visits"], list):
            self._invalid_manifest(run_id, "visits must be a list")
        attempts: dict[str, int] = {}
        for expected_ordinal, visit in enumerate(value["visits"], 1):
            if not isinstance(visit, dict):
                self._invalid_manifest(run_id, "visit record must be an object")
            self._validate_visit(visit, run_id, expected_ordinal)
            phase_id = visit["phase_id"]
            attempts[phase_id] = attempts.get(phase_id, 0) + 1
            if visit["attempt"] != attempts[phase_id]:
                self._invalid_manifest(run_id, "visit attempt is not ordered")
        current = value["current_visit"]
        if current is not None and (
            not isinstance(current, int) or current < 1 or current > len(value["visits"])
        ):
            self._invalid_manifest(run_id, "current visit is invalid")
        if not isinstance(value["approvals"], list) or not all(
            isinstance(item, dict) for item in value["approvals"]
        ):
            self._invalid_manifest(run_id, "approvals must be an ordered object list")
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            self._invalid_manifest(run_id, f"manifest is not JSON serializable: {exc}")

    def _validate_visit(
        self, visit: dict[str, Any], run_id: str, expected_ordinal: int
    ) -> None:
        required = {
            "phase_id",
            "ordinal",
            "attempt",
            "status",
            "inputs",
            "output",
            "mutation_policy",
            "mutation_baseline",
            "mutation_result",
            "validation_checks",
            "command_results",
            "chosen_outcome",
            "transition_target",
            "skill",
            "template",
            "started_at",
            "completed_at",
            "deviations",
        }
        if set(visit) != required:
            self._invalid_manifest(run_id, "visit fields do not match the schema")
        if (
            not isinstance(visit["phase_id"], str)
            or visit["ordinal"] != expected_ordinal
            or not isinstance(visit["attempt"], int)
            or visit["attempt"] < 1
            or visit["status"] not in VISIT_STATUSES
        ):
            self._invalid_manifest(run_id, "visit identity or status is invalid")
        if not isinstance(visit["inputs"], list):
            self._invalid_manifest(run_id, "visit inputs must be a list")
        for record in visit["inputs"]:
            self._validate_artifact_record(record, run_id, hash_required=True, reference=True)
        self._validate_artifact_record(
            visit["output"], run_id, hash_required=visit["status"] == "completed"
        )
        if visit["status"] != "completed" and visit["output"]["sha256"] is not None:
            self._invalid_manifest(run_id, "mutable visit output cannot have a sealed hash")
        for name in ("validation_checks", "command_results", "deviations"):
            if not isinstance(visit[name], list):
                self._invalid_manifest(run_id, f"visit {name} must be a list")
        if not isinstance(visit["skill"], dict):
            self._invalid_manifest(run_id, "visit skill provenance is invalid")
        self._validate_provenance(visit["skill"], run_id)
        if visit["template"] is not None:
            if not isinstance(visit["template"], dict):
                self._invalid_manifest(run_id, "visit template provenance is invalid")
            self._validate_provenance(visit["template"], run_id)
        self._validate_timestamp(visit["started_at"], run_id)
        if visit["completed_at"] is not None:
            self._validate_timestamp(visit["completed_at"], run_id)
        if visit["status"] == "completed" and visit["completed_at"] is None:
            self._invalid_manifest(run_id, "completed visit lacks a completion timestamp")

    def _validate_artifact_record(
        self,
        value: Any,
        run_id: str,
        *,
        hash_required: bool,
        reference: bool = False,
    ) -> None:
        fields = {"path", "sha256", "reference"} if reference else {"path", "sha256"}
        if not isinstance(value, dict) or set(value) != fields:
            self._invalid_manifest(run_id, "artifact record is invalid")
        self._validate_path(value["path"], run_id)
        digest = value["sha256"]
        if hash_required and (
            not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest)
        ):
            self._invalid_manifest(run_id, "artifact hash is invalid")
        if not hash_required and digest is not None:
            self._invalid_manifest(run_id, "artifact hash must be null until sealed")
        if reference and not isinstance(value["reference"], str):
            self._invalid_manifest(run_id, "artifact reference is invalid")

    def _validate_provenance(self, value: dict[str, Any], run_id: str) -> None:
        if set(value) != {"path", "sha256"}:
            self._invalid_manifest(run_id, "provenance record is invalid")
        self._validate_path(value["path"], run_id)
        if not isinstance(value["sha256"], str) or not SHA256_PATTERN.fullmatch(
            value["sha256"]
        ):
            self._invalid_manifest(run_id, "provenance hash is invalid")

    def _validate_event(self, event: dict[str, Any], run_id: str) -> None:
        required = {
            "schema_version",
            "sequence",
            "timestamp",
            "run_id",
            "visit_number",
            "type",
            "payload",
            "manifest_revision",
            "manifest_hash",
        }
        if set(event) != required:
            raise RunCorruptionError("event fields do not match the schema", run_id=run_id)
        if (
            event["schema_version"] != EVENT_SCHEMA_VERSION
            or event["run_id"] != run_id
            or not isinstance(event["sequence"], int)
            or event["sequence"] < 1
            or not isinstance(event["manifest_revision"], int)
            or event["manifest_revision"] < 1
            or not isinstance(event["type"], str)
            or not EVENT_TYPE_PATTERN.fullmatch(event["type"])
            or not isinstance(event["payload"], dict)
            or not isinstance(event["manifest_hash"], str)
            or not SHA256_PATTERN.fullmatch(event["manifest_hash"])
        ):
            raise RunCorruptionError("event record is invalid", run_id=run_id)
        visit_number = event["visit_number"]
        if visit_number is not None and (
            not isinstance(visit_number, int) or visit_number < 1
        ):
            raise RunCorruptionError("event visit number is invalid", run_id=run_id)
        self._validate_timestamp(event["timestamp"], run_id)

    @staticmethod
    def _validate_timestamp(value: Any, run_id: str) -> None:
        if not isinstance(value, str) or not value.endswith("Z"):
            raise RunCorruptionError("timestamp is invalid", run_id=run_id)
        try:
            datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
        except ValueError as exc:
            raise RunCorruptionError("timestamp is invalid", run_id=run_id) from exc

    @staticmethod
    def _validate_path(value: Any, run_id: str) -> None:
        if not isinstance(value, str):
            raise RunCorruptionError("persisted path is invalid", run_id=run_id)
        try:
            normalize_relative_path(value)
        except ValueError as exc:
            raise RunCorruptionError("persisted path is unsafe", run_id=run_id) from exc

    @staticmethod
    def _invalid_manifest(run_id: str, message: str) -> None:
        raise RunCorruptionError(message, run_id=run_id)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


new_run_id = generate_run_id
CorruptRunError = RunCorruptionError
