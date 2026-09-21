"""Research phase lifecycle, validation, digest binding, and audit events."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..artifacts.frontmatter import parse_frontmatter
from ..artifacts.research import ResearchArtifact, validate_research
from ..clock import Clock, SystemClock, utc_timestamp
from ..errors import (
    InvalidInputError,
    InvalidTransitionError,
    SpecromancyError,
    ValidationError,
)
from ..io import append_json_line, read_text, sha256_file
from ..paths import RepositoryPaths
from ..state import apply_transition


@dataclass(frozen=True)
class ResearchPhaseResult:
    run_id: str
    status: str
    artifact_path: str
    artifact_sha256: str | None = None
    warnings: tuple[str, ...] = ()
    replayed: bool = False


def _timestamp(clock: Clock) -> str:
    return utc_timestamp(clock.now())


def _load_manifest(paths: RepositoryPaths, run_id: str) -> dict[str, Any]:
    target = paths.run_manifest(run_id)
    if not target.is_file():
        raise InvalidInputError(
            f"Run '{run_id}' does not exist.",
            hint="Use a run ID whose run.json exists in .specromancy/runs/.",
            details={"run_id": run_id},
        )
    try:
        value = json.loads(read_text(target))
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "Run manifest is not valid JSON.",
            hint="Restore run.json from a valid event projection before continuing.",
            path=paths.serialize(target),
        ) from exc
    if not isinstance(value, dict):
        raise ValidationError(
            "Run manifest must contain a JSON object.",
            hint="Restore a version 1 run manifest before continuing.",
            path=paths.serialize(target),
        )
    if value.get("run_id") != run_id:
        raise ValidationError(
            "Run manifest ID does not match its directory.",
            hint="Move the manifest to its matching run directory or correct the run ID.",
        )
    if Path(str(value.get("repository_root", ""))).resolve() != paths.root:
        raise ValidationError(
            "Run manifest belongs to a different repository root.",
            hint="Run the command in the repository that initialized this run.",
        )
    return value


def _request_digest(
    paths: RepositoryPaths, run_id: str, manifest: Mapping[str, Any]
) -> str:
    request_path = paths.run_artifact(run_id, "request.md")
    if not request_path.is_file():
        raise ValidationError(
            "The run request artifact is missing.",
            hint="Restore request.md before starting research.",
            path=paths.serialize(request_path),
        )
    parse_frontmatter(
        read_text(request_path),
        expected_run_id=run_id,
        expected_stage="request",
        expected_status="ready",
    )
    digest = sha256_file(request_path)
    artifacts = manifest.get("artifacts")
    record = artifacts.get("request") if isinstance(artifacts, dict) else None
    if not isinstance(record, dict) or record.get("sha256") != digest:
        raise ValidationError(
            "The request artifact does not match the digest in run.json.",
            hint="Restore the initialized request artifact or repair the run before research.",
        )
    return digest


def _path_in_run(path: str, run_prefix: str) -> bool:
    normalized = path.replace("\\", "/").strip('"')
    return normalized == run_prefix or normalized.startswith(run_prefix + "/")


def _git_scope_snapshot(root: Path, run_prefix: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=root,
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        return None
    if completed.returncode != 0:
        return None

    chunks = completed.stdout.split(b"\0")
    entries: list[dict[str, Any]] = []
    index = 0
    while index < len(chunks):
        chunk = chunks[index]
        index += 1
        if not chunk:
            continue
        decoded = chunk.decode("utf-8", errors="surrogateescape")
        if len(decoded) < 4:
            continue
        status = decoded[:2]
        path = decoded[3:]
        paths_for_entry = [path]
        if ("R" in status or "C" in status) and index < len(chunks) and chunks[index]:
            paths_for_entry.append(chunks[index].decode("utf-8", errors="surrogateescape"))
            index += 1
        if all(_path_in_run(item, run_prefix) for item in paths_for_entry):
            continue
        hashes: dict[str, str | None] = {}
        for item in paths_for_entry:
            candidate = root / item
            if candidate.is_file():
                try:
                    hashes[item] = sha256_file(candidate)
                except ValidationError:
                    hashes[item] = None
            else:
                hashes[item] = None
        entries.append({"status": status, "paths": paths_for_entry, "hashes": hashes})
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8", errors="surrogateescape")).hexdigest()


def _filesystem_scope_snapshot(root: Path, run_dir: Path) -> str:
    digest = hashlib.sha256()
    for candidate in sorted(root.rglob("*")):
        if not candidate.is_file():
            continue
        try:
            relative = candidate.relative_to(root)
            candidate.relative_to(run_dir)
        except ValueError:
            pass
        else:
            continue
        if relative.parts and relative.parts[0] == ".git":
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(bytes.fromhex(sha256_file(candidate)))
        except ValidationError:
            digest.update(b"unreadable")
    return digest.hexdigest()


def _scope_snapshot(paths: RepositoryPaths, run_id: str) -> str:
    run_prefix = paths.serialize(paths.run_dir(run_id))
    git_snapshot = _git_scope_snapshot(paths.root, run_prefix)
    if git_snapshot is not None:
        return git_snapshot
    return _filesystem_scope_snapshot(paths.root, paths.run_dir(run_id))


def _event(
    *,
    event_type: str,
    run_id: str,
    occurred_at: str,
    phase: str = "research",
    **values: Any,
) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "event_type": event_type,
        "run_id": run_id,
        "phase": phase,
        "occurred_at": occurred_at,
        **values,
    }


def _append_failure(
    paths: RepositoryPaths,
    run_id: str,
    error: SpecromancyError,
    *,
    action: str,
    clock: Clock,
) -> None:
    if not paths.run_dir(run_id).is_dir():
        return
    append_json_line(
        paths.run_events(run_id),
        _event(
            event_type="failure",
            run_id=run_id,
            occurred_at=_timestamp(clock),
            action=action,
            error_code=error.code,
            message=error.message,
        ),
    )


def _research_start_snapshot(paths: RepositoryPaths, run_id: str) -> str:
    events = paths.run_events(run_id)
    if not events.is_file():
        raise ValidationError(
            "Research start event is missing.",
            hint="Restart from a valid initialized run so write-scope checks can be enforced.",
        )
    latest: str | None = None
    for line_number, line in enumerate(read_text(events).splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "Run event log contains malformed JSON.",
                hint=f"Repair events.jsonl line {line_number} before completing research.",
            ) from exc
        if (
            isinstance(event, dict)
            and event.get("event_type") == "transition"
            and event.get("transition_id") == "research.start"
        ):
            snapshot = event.get("write_scope_snapshot")
            if isinstance(snapshot, str):
                latest = snapshot
    if latest is None:
        raise ValidationError(
            "Research start event has no write-scope snapshot.",
            hint="Restart from a valid initialized run before completing research.",
        )
    return latest


def research_artifact_path(repository_root: str | Path, run_id: str) -> Path:
    paths = RepositoryPaths(Path(repository_root))
    _load_manifest(paths, run_id)
    return paths.run_artifact(run_id, "research.md")


def validate_research_file(
    repository_root: str | Path,
    run_id: str,
    *,
    record_event: bool = True,
    clock: Clock | None = None,
) -> ResearchArtifact:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    _load_manifest(paths, run_id)
    artifact_path = paths.run_artifact(run_id, "research.md")
    try:
        if not artifact_path.is_file():
            raise ValidationError(
                "Research artifact is missing.",
                hint="Create research.md from the canonical research template and retry.",
                path=paths.serialize(artifact_path),
            )
        artifact = validate_research(read_text(artifact_path), paths.root, run_id)
    except SpecromancyError as exc:
        if record_event:
            _append_failure(paths, run_id, exc, action="validate_research", clock=clock)
        raise
    if record_event:
        append_json_line(
            paths.run_events(run_id),
            _event(
                event_type="validation",
                run_id=run_id,
                occurred_at=_timestamp(clock),
                action="validate_research",
                outcome="passed",
                artifact="research",
                artifact_sha256=sha256_file(artifact_path),
                warnings=list(artifact.warnings),
            ),
        )
    return artifact


def start_research(
    repository_root: str | Path,
    run_id: str,
    *,
    clock: Clock | None = None,
) -> ResearchPhaseResult:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    manifest = _load_manifest(paths, run_id)
    if manifest.get("status") != "initialized":
        error = InvalidTransitionError(
            f"Research cannot start while the run is '{manifest.get('status')}'.",
            hint="Start research only from an initialized run.",
            details={"status": manifest.get("status")},
        )
        _append_failure(paths, run_id, error, action="start_research", clock=clock)
        raise error
    try:
        _request_digest(paths, run_id, manifest)
        snapshot = _scope_snapshot(paths, run_id)
    except SpecromancyError as exc:
        _append_failure(paths, run_id, exc, action="start_research", clock=clock)
        raise
    now = _timestamp(clock)
    event = _event(
        event_type="transition",
        run_id=run_id,
        occurred_at=now,
        action="start_research",
        transition_id="research.start",
        from_status="initialized",
        to_status="research_in_progress",
        write_scope_snapshot=snapshot,
    )
    apply_transition(paths, run_id, manifest, event)
    artifact_path = paths.run_artifact(run_id, "research.md")
    return ResearchPhaseResult(
        run_id=run_id,
        status="research_in_progress",
        artifact_path=paths.serialize(artifact_path),
    )


def complete_research(
    repository_root: str | Path,
    run_id: str,
    *,
    clock: Clock | None = None,
) -> ResearchPhaseResult:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    manifest = _load_manifest(paths, run_id)
    artifact_path = paths.run_artifact(run_id, "research.md")

    if manifest.get("status") == "research_ready":
        artifact = validate_research_file(
            paths.root, run_id, record_event=False, clock=clock
        )
        digest = sha256_file(artifact_path)
        record = manifest.get("artifacts", {}).get("research")
        request = manifest.get("artifacts", {}).get("request")
        expected_request = request.get("sha256") if isinstance(request, dict) else None
        if (
            isinstance(record, dict)
            and record.get("sha256") == digest
            and record.get("bindings") == {"request": expected_request}
        ):
            return ResearchPhaseResult(
                run_id=run_id,
                status="research_ready",
                artifact_path=paths.serialize(artifact_path),
                artifact_sha256=digest,
                warnings=artifact.warnings,
                replayed=True,
            )
        error = ValidationError(
            "Completed research no longer matches its recorded digest or bindings.",
            hint="Restore the accepted research artifact before repeating completion.",
        )
        _append_failure(paths, run_id, error, action="complete_research", clock=clock)
        raise error

    if manifest.get("status") != "research_in_progress":
        error = InvalidTransitionError(
            f"Research cannot complete while the run is '{manifest.get('status')}'.",
            hint="Complete research only after a successful research start.",
            details={"status": manifest.get("status")},
        )
        _append_failure(paths, run_id, error, action="complete_research", clock=clock)
        raise error

    try:
        artifact = validate_research_file(paths.root, run_id, clock=clock)
        start_snapshot = _research_start_snapshot(paths, run_id)
        current_snapshot = _scope_snapshot(paths, run_id)
        if current_snapshot != start_snapshot:
            raise ValidationError(
                "Repository files outside the active run changed during research.",
                hint="Restore those changes or restart research from the new repository state.",
            )
        request_digest = _request_digest(paths, run_id, manifest)
    except SpecromancyError as exc:
        _append_failure(paths, run_id, exc, action="complete_research", clock=clock)
        raise

    digest = sha256_file(artifact_path)
    now = _timestamp(clock)
    event = _event(
        event_type="transition",
        run_id=run_id,
        occurred_at=now,
        action="complete_research",
        transition_id="research.complete",
        from_status="research_in_progress",
        to_status="research_ready",
        artifact="research",
        artifact_sha256=digest,
        bindings={"request": request_digest},
    )
    record = {
        "path": paths.serialize(artifact_path),
        "sha256": digest,
        "validated_at": now,
        "schema_version": "1",
        "bindings": {"request": request_digest},
    }
    apply_transition(
        paths,
        run_id,
        manifest,
        event,
        artifact_name="research",
        artifact_record=record,
    )
    return ResearchPhaseResult(
        run_id=run_id,
        status="research_ready",
        artifact_path=paths.serialize(artifact_path),
        artifact_sha256=digest,
        warnings=artifact.warnings,
    )


start = start_research
complete = complete_research
