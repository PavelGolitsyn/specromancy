"""Run initialization, manifest serialization, and invariant validation."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from .clock import Clock, RunIdGenerator, SystemClock, utc_timestamp
from .compatibility import (
    ARTIFACT_SCHEMA_VERSION,
    RUN_MANIFEST_SCHEMA_VERSION,
    require_supported_version,
)
from .contracts import pipeline_contract, run_schema
from .errors import InvalidInputError, SafetyError, ValidationError
from .events import verify_event_projection
from .git import capture_snapshot
from .io import atomic_write_json, atomic_write_text, normalized_text, read_text, sha256_file
from .paths import RepositoryPaths
from .requirements import extract_requirements


@dataclass(frozen=True)
class RunInitialization:
    run_id: str
    title: str
    status: str
    run_path: str
    request_path: str
    manifest_path: str
    next_command: str


def _timestamp(clock: Clock) -> str:
    return utc_timestamp(clock.now())


def _repository_url(root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError:
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip() or None
    if value is None:
        return None
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        raise SafetyError(
            "Repository URL contains embedded credentials.",
            hint="Remove credentials from the configured origin URL before initialization.",
        )
    return value


def _request_body(content: str) -> str:
    value = normalized_text(content).strip()
    if value.startswith("---\n"):
        closing = value.find("\n---\n", 4)
        if closing >= 0:
            value = value[closing + 5 :].strip()
    if not value:
        raise InvalidInputError("The run request cannot be empty.")
    return value


def _request_document(run_id: str, content: str, created_at: str) -> str:
    body = _request_body(content)
    return (
        "---\n"
        f'schema-version: "{ARTIFACT_SCHEMA_VERSION}"\n'
        f'run-id: "{run_id}"\n'
        'stage: "request"\n'
        'status: "ready"\n'
        f'created-at: "{created_at}"\n'
        "---\n\n"
        f"{body}\n"
    )


def _derive_title(content: str) -> str:
    for line in _request_body(content).splitlines():
        candidate = re.sub(r"^#+\s*", "", line).strip()
        if candidate:
            return candidate[:200]
    return "Specromancy run"


def initialize_run(
    repository_root: str | Path,
    *,
    title: str | None = None,
    request_path: str | Path | None = None,
    request_text: str | None = None,
    run_id: str | None = None,
    clock: Clock | None = None,
    id_generator: RunIdGenerator | None = None,
) -> RunInitialization:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    if request_path is not None and request_text is not None:
        raise InvalidInputError("Pass either request_path or request_text, not both.")
    if request_path is not None:
        source = Path(request_path).expanduser().resolve()
        if not source.is_file():
            raise InvalidInputError("Request file does not exist.", path=str(source))
        content = read_text(source)
    elif request_text is not None:
        content = request_text
    elif title is not None and title.strip():
        content = f"# Request\n\n{title.strip()}"
    else:
        raise InvalidInputError(
            "Run initialization requires a request file, request text, or title.",
            hint="Pass --request FILE or --title TEXT.",
        )
    normalized_title = (title.strip() if title is not None else _derive_title(content))
    if not normalized_title or len(normalized_title) > 200:
        raise InvalidInputError("Run title must contain 1 to 200 characters.")
    generator = id_generator or RunIdGenerator(clock=clock)
    selected_id = run_id or generator.generate(normalized_title)
    # Validate before creating any directory.
    final_dir = paths.run_dir(selected_id)
    paths.runs_dir.mkdir(parents=True, exist_ok=True)
    if final_dir.exists():
        raise InvalidInputError(
            f"Run '{selected_id}' already exists.",
            hint="Use resume with the existing run ID instead of reinitializing it.",
        )

    created_at = _timestamp(clock)
    request_document = _request_document(selected_id, content, created_at)
    requirements = list(extract_requirements(request_document))
    snapshot = capture_snapshot(paths.root)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{selected_id}.", dir=paths.runs_dir)
    )
    try:
        request_target = temporary / "request.md"
        manifest_target = temporary / "run.json"
        events_target = temporary / "events.jsonl"
        atomic_write_text(request_target, request_document)
        request_relative = f".specromancy/runs/{selected_id}/request.md"
        manifest: dict[str, Any] = {
            "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
            "run_id": selected_id,
            "title": normalized_title,
            "created_at": created_at,
            "updated_at": created_at,
            "status": "initialized",
            "current_phase": None,
            "repository_root": str(paths.root),
            "repository_url": _repository_url(paths.root),
            "git_base": snapshot.head,
            "git_head": snapshot.head,
            "git_branch": snapshot.branch,
            "initial_worktree": {
                "recorded_at": created_at,
                "staged_paths": list(snapshot.staged_paths),
                "unstaged_paths": list(snapshot.unstaged_paths),
                "untracked_paths": list(snapshot.untracked_paths),
            },
            "implementation_baseline": None,
            "requirements": requirements,
            "artifacts": {
                "request": {
                    "path": request_relative,
                    "sha256": sha256_file(request_target),
                    "validated_at": created_at,
                    "schema_version": ARTIFACT_SCHEMA_VERSION,
                    "bindings": {},
                }
            },
            "approvals": [],
            "changed_files": [],
            "review_subject_sha256": None,
            "review_cycle": 0,
            "max_review_cycles": int(
                pipeline_contract().get("default_max_review_cycles", 3)
            ),
            "last_error": None,
            "events_path": f".specromancy/runs/{selected_id}/events.jsonl",
            "lock_path": f".specromancy/runs/{selected_id}/run.lock",
        }
        atomic_write_json(manifest_target, manifest)
        event = {
            "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
            "event_type": "run_initialized",
            "run_id": selected_id,
            "phase": "run",
            "occurred_at": created_at,
            "status": "initialized",
            "repository_root": str(paths.root),
            "request_sha256": manifest["artifacts"]["request"]["sha256"],
        }
        atomic_write_text(
            events_target,
            json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            + "\n",
        )
        try:
            os.replace(temporary, final_dir)
        except FileExistsError as exc:
            raise InvalidInputError(
                f"Run '{selected_id}' was initialized concurrently.",
                hint="Use the existing run ID or initialize a new run.",
            ) from exc
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    validate_manifest(paths, selected_id, validate_artifacts=True, validate_events=True)
    return RunInitialization(
        run_id=selected_id,
        title=normalized_title,
        status="initialized",
        run_path=paths.serialize(final_dir),
        request_path=request_relative,
        manifest_path=paths.serialize(paths.run_manifest(selected_id)),
        next_command=f"specromancy phase start {selected_id} research",
    )


def load_manifest(paths: RepositoryPaths, run_id: str) -> dict[str, Any]:
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
        raise ValidationError("Run manifest must contain a JSON object.")
    return value


def save_manifest(paths: RepositoryPaths, run_id: str, manifest: Mapping[str, Any]) -> None:
    atomic_write_json(paths.run_manifest(run_id), dict(manifest))


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValidationError(f"Run manifest field '{field}' is not a timestamp.")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"Run manifest field '{field}' is not a timestamp.") from exc


def validate_manifest(
    paths_or_root: RepositoryPaths | str | Path,
    run_id: str,
    *,
    validate_artifacts: bool = False,
    validate_events: bool = True,
) -> dict[str, Any]:
    paths = (
        paths_or_root
        if isinstance(paths_or_root, RepositoryPaths)
        else RepositoryPaths(Path(paths_or_root))
    )
    manifest = load_manifest(paths, run_id)
    required = set(run_schema().get("required", []))
    missing = sorted(required - set(manifest))
    extras = sorted(set(manifest) - set(run_schema().get("properties", {})))
    if missing or extras:
        raise ValidationError(
            "Run manifest fields do not match the version 1 schema.",
            details={"missing_fields": missing, "unexpected_fields": extras},
        )
    require_supported_version(
        "Run manifest schema",
        manifest.get("schema_version"),
        RUN_MANIFEST_SCHEMA_VERSION,
    )
    if manifest.get("run_id") != run_id:
        raise ValidationError("Run manifest identity does not match its directory.")
    if Path(str(manifest.get("repository_root", ""))).resolve() != paths.root:
        raise ValidationError(
            "Run manifest belongs to a different repository root.",
            hint="Run the command in the repository that initialized this run.",
        )
    phases = pipeline_contract().get("status_current_phase", {})
    status = manifest.get("status")
    if status not in phases or manifest.get("current_phase") != phases[status]:
        raise ValidationError("Run status and current phase are inconsistent.")
    created = _parse_timestamp(manifest.get("created_at"), "created_at")
    updated = _parse_timestamp(manifest.get("updated_at"), "updated_at")
    if updated < created:
        raise ValidationError("Run updated_at is earlier than created_at.")
    cycle = manifest.get("review_cycle")
    maximum = manifest.get("max_review_cycles")
    if (
        not isinstance(cycle, int)
        or not isinstance(maximum, int)
        or cycle < 0
        or maximum < 1
        or cycle > maximum
    ):
        raise ValidationError("Run review-cycle counters are invalid.")
    if manifest.get("events_path") != paths.serialize(paths.run_events(run_id)):
        raise ValidationError("Run events path does not match its managed location.")
    if manifest.get("lock_path") != paths.serialize(paths.run_lock(run_id)):
        raise ValidationError("Run lock path does not match its managed location.")
    url = manifest.get("repository_url")
    if isinstance(url, str):
        parsed = urlsplit(url)
        if parsed.username is not None or parsed.password is not None:
            raise SafetyError("Run manifest repository URL contains embedded credentials.")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or "request" not in artifacts:
        raise ValidationError("Run manifest has no request artifact record.")
    for name, record in artifacts.items():
        if name not in {"request", "research", "plan", "implementation", "review"}:
            raise ValidationError("Run manifest contains an unknown artifact record.")
        if not isinstance(record, dict):
            raise ValidationError(f"Artifact record '{name}' is malformed.")
        expected = paths.serialize(paths.run_artifact(run_id, f"{name}.md"))
        if record.get("path") != expected:
            raise ValidationError(
                f"Artifact record '{name}' points outside its canonical path."
            )
        target = paths.resolve_relative(expected)
        if validate_artifacts:
            if not target.is_file() or record.get("sha256") != sha256_file(target):
                raise ValidationError(
                    f"Artifact '{name}' does not match its recorded digest.",
                    hint="Restore the accepted artifact or return to its owning phase.",
                )
    approvals = manifest.get("approvals")
    if not isinstance(approvals, list):
        raise ValidationError("Run approvals are malformed.")
    active = [
        item
        for item in approvals
        if isinstance(item, dict) and item.get("status") == "active"
    ]
    if len(active) > 1:
        raise ValidationError("Run contains more than one active plan approval.")
    if active:
        plan = artifacts.get("plan")
        if not isinstance(plan, dict) or active[0].get("artifact_sha256") != plan.get(
            "sha256"
        ):
            raise ValidationError("Active plan approval is bound to a stale plan digest.")
    if validate_events:
        verify_event_projection(paths, run_id, manifest)
    return manifest
