"""Harness-neutral run inspection, continuation, recovery, and run actions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .clock import Clock, SystemClock, utc_timestamp
from .contracts import pipeline_contract
from .errors import (
    ApprovalRequiredError,
    ConcurrencyError,
    InvalidInputError,
    InvalidTransitionError,
    ValidationError,
)
from .events import append_event, verify_event_projection
from .git import capture_snapshot
from .io import sha256_file
from .locking import RunLock, inspect_run_lock, recover_run_lock
from .paths import RepositoryPaths
from .run import load_manifest, validate_manifest
from .state import apply_transition


TERMINAL_STATUSES = frozenset(pipeline_contract().get("terminal_statuses", []))


@dataclass(frozen=True)
class NextAction:
    action: str | None
    gate: str | None
    description: str


_NEXT: dict[str, NextAction] = {
    "initialized": NextAction(
        "phase start RUN_ID research", "request artifact is current", "Start research."
    ),
    "research_in_progress": NextAction(
        "phase complete RUN_ID research",
        "research.md validates and write scope is unchanged",
        "Finish the research artifact, validate it, and complete research.",
    ),
    "research_ready": NextAction(
        "phase start RUN_ID plan", "research artifact is current", "Start planning."
    ),
    "plan_in_progress": NextAction(
        "phase complete RUN_ID plan",
        "plan.md validates and traces every requirement",
        "Finish the plan artifact, validate it, and complete planning.",
    ),
    "plan_ready": NextAction(
        "approve RUN_ID plan --by IDENTITY",
        "explicit digest-bound user approval",
        "Review and explicitly approve the completed plan.",
    ),
    "plan_approved": NextAction(
        "phase start RUN_ID implementation",
        "current plan digest matches the active approval",
        "Start implementation.",
    ),
    "implementation_in_progress": NextAction(
        "phase complete RUN_ID implementation",
        "implementation.md, changed-file inventory, and verification records validate",
        "Finish the scoped work and complete implementation.",
    ),
    "implementation_ready": NextAction(
        "phase start RUN_ID review",
        "implementation artifact and repository subject are current",
        "Start independent review.",
    ),
    "review_in_progress": NextAction(
        "phase complete RUN_ID review",
        "review.md validates against the unchanged review subject",
        "Finish the review and record its verdict.",
    ),
    "changes_requested": NextAction(
        "phase repair RUN_ID implementation",
        "review cycle remains and every blocking finding will be addressed",
        "Start a bounded implementation repair.",
    ),
}


def _timestamp(clock: Clock) -> str:
    return utc_timestamp(clock.now())


def next_action(manifest: Mapping[str, Any]) -> NextAction:
    status = str(manifest.get("status"))
    if status in TERMINAL_STATUSES:
        return NextAction(None, None, f"Run is terminal with status '{status}'.")
    if status == "changes_requested" and int(manifest.get("review_cycle", 0)) >= int(
        manifest.get("max_review_cycles", 0)
    ):
        return NextAction(
            "phase fail RUN_ID review --reason TEXT",
            "repair-cycle limit is exhausted",
            "Block the exhausted run with a durable reason.",
        )
    try:
        return _NEXT[status]
    except KeyError as exc:
        raise ValidationError("Run has no continuation rule.", details={"status": status}) from exc


def status_run(repository_root: str | Path, run_id: str) -> dict[str, Any]:
    paths = RepositoryPaths(Path(repository_root))
    manifest = validate_manifest(paths, run_id, validate_artifacts=False)
    action = next_action(manifest)
    return {
        "run_id": run_id,
        "title": manifest["title"],
        "status": manifest["status"],
        "current_phase": manifest["current_phase"],
        "review_cycle": manifest["review_cycle"],
        "max_review_cycles": manifest["max_review_cycles"],
        "updated_at": manifest["updated_at"],
        "next_action": action.action,
        "required_gate": action.gate,
        "terminal": manifest["status"] in TERMINAL_STATUSES,
        "artifacts": dict(manifest["artifacts"]),
        "changed_files": list(manifest["changed_files"]),
    }


def _artifact_names(manifest: Mapping[str, Any], selected: str | None) -> list[str]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValidationError("Run artifact records are malformed.")
    if selected is not None:
        if selected not in artifacts:
            raise InvalidInputError(
                f"Run has no recorded '{selected}' artifact.",
                hint="Verify a completed artifact recorded in run.json.",
            )
        return [selected]
    return list(artifacts)


def verify_artifacts(
    repository_root: str | Path, run_id: str, artifact: str | None = None
) -> list[dict[str, str]]:
    paths = RepositoryPaths(Path(repository_root))
    manifest = validate_manifest(paths, run_id, validate_artifacts=False)
    results: list[dict[str, str]] = []
    for name in _artifact_names(manifest, artifact):
        record = manifest["artifacts"][name]
        target = paths.resolve_relative(record["path"])
        if not target.is_file():
            raise ValidationError(
                f"Recorded artifact '{name}' is missing.", path=record["path"]
            )
        digest = sha256_file(target)
        if digest != record.get("sha256"):
            raise ValidationError(
                f"Artifact '{name}' was edited after it was accepted.",
                hint="Restore the artifact or return to its owning phase.",
                path=record["path"],
                details={"recorded_sha256": record.get("sha256"), "current_sha256": digest},
            )
        results.append({"artifact": name, "path": record["path"], "sha256": digest})
    return results


def _outside_run_paths(
    paths: RepositoryPaths, run_id: str, snapshot
) -> set[str]:
    prefix = paths.serialize(paths.run_dir(run_id))
    result: set[str] = set()
    for group in (snapshot.staged_paths, snapshot.unstaged_paths, snapshot.untracked_paths):
        for path in group:
            if path != prefix and not path.startswith(prefix + "/"):
                result.add(path)
    return result


def _validate_repository_subject(
    paths: RepositoryPaths, run_id: str, manifest: Mapping[str, Any]
) -> None:
    snapshot = capture_snapshot(paths.root)
    if snapshot.head != manifest.get("git_head"):
        raise ConcurrencyError(
            "Repository HEAD changed outside the run.",
            hint="Reconcile the commit, then restart the affected phase from a new baseline.",
            details={"recorded_head": manifest.get("git_head"), "current_head": snapshot.head},
        )
    if manifest.get("status") not in {
        "implementation_ready",
        "review_in_progress",
        "changes_requested",
    }:
        return
    changed = manifest.get("changed_files", [])
    recorded_paths = {
        str(item.get("path")) for item in changed if isinstance(item, dict)
    }
    current_paths = _outside_run_paths(paths, run_id, snapshot)
    if current_paths != recorded_paths:
        raise ConcurrencyError(
            "Repository changed-file inventory no longer matches the run.",
            hint="Restore the accepted implementation subject or restart implementation.",
            details={
                "missing_paths": sorted(recorded_paths - current_paths),
                "new_paths": sorted(current_paths - recorded_paths),
            },
        )
    for item in changed:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValidationError("Run changed-file inventory is malformed.")
        target = paths.resolve_relative(item["path"])
        digest = sha256_file(target) if target.is_file() else None
        if digest != item.get("sha256_after"):
            raise ConcurrencyError(
                f"Repository path '{item['path']}' changed outside the run.",
                hint="Restore the reviewed subject or complete a fresh implementation.",
            )


def resume_run(repository_root: str | Path, run_id: str) -> dict[str, Any]:
    paths = RepositoryPaths(Path(repository_root))
    lock = inspect_run_lock(paths.root, run_id)
    if lock is not None:
        raise ConcurrencyError(
            f"Run '{run_id}' has an unresolved lock.",
            hint="Inspect the lock; if its owner is gone or it is stale, run lock recover explicitly.",
            details={
                "pid": lock.pid,
                "hostname": lock.hostname,
                "created_at": lock.created_at,
                "command": lock.command,
            },
        )
    manifest = validate_manifest(
        paths, run_id, validate_artifacts=True, validate_events=True
    )
    _validate_repository_subject(paths, run_id, manifest)
    action = next_action(manifest)
    rendered = action.action.replace("RUN_ID", run_id) if action.action else None
    brief = action.description
    if rendered:
        brief += f" Next command: specromancy {rendered}."
    if action.gate:
        brief += f" Required gate: {action.gate}."
    return {
        "run_id": run_id,
        "status": manifest["status"],
        "current_phase": manifest["current_phase"],
        "next_action": rendered,
        "required_gate": action.gate,
        "continuation_brief": brief,
        "terminal": manifest["status"] in TERMINAL_STATUSES,
    }


def _run_transition(
    paths: RepositoryPaths,
    run_id: str,
    *,
    transition_id: str,
    action: str,
    target: str,
    reason: str,
    clock: Clock,
) -> dict[str, Any]:
    explanation = reason.strip()
    if not explanation or len(explanation) > 1000:
        raise InvalidInputError("Run action requires a reason of 1 to 1000 characters.")
    with RunLock(paths, run_id, action, clock):
        manifest = validate_manifest(paths, run_id, validate_artifacts=False)
        source = str(manifest.get("status"))
        if source in TERMINAL_STATUSES:
            raise InvalidTransitionError(
                f"Run is already terminal with status '{source}'."
            )
        now = _timestamp(clock)
        event = {
            "schema_version": "1",
            "event_type": "transition",
            "run_id": run_id,
            "phase": "run",
            "occurred_at": now,
            "action": action,
            "transition_id": transition_id,
            "from_status": source,
            "to_status": target,
            "reason": explanation,
        }
        return apply_transition(paths, run_id, manifest, event)


def cancel_run(
    repository_root: str | Path,
    run_id: str,
    *,
    reason: str,
    clock: Clock | None = None,
) -> dict[str, Any]:
    paths = RepositoryPaths(Path(repository_root))
    return _run_transition(
        paths,
        run_id,
        transition_id="run.cancel",
        action="cancel_run",
        target="cancelled",
        reason=reason,
        clock=clock or SystemClock(),
    )


def fail_phase(
    repository_root: str | Path,
    run_id: str,
    phase: str,
    *,
    reason: str,
    clock: Clock | None = None,
) -> dict[str, Any]:
    paths = RepositoryPaths(Path(repository_root))
    manifest = validate_manifest(paths, run_id, validate_artifacts=False)
    current = manifest.get("current_phase")
    if current != phase and not (
        manifest.get("status") == "changes_requested" and phase == "review"
    ):
        raise InvalidTransitionError(
            f"Phase '{phase}' is not the active or pending phase for this run.",
            details={"status": manifest.get("status"), "current_phase": current},
        )
    return _run_transition(
        paths,
        run_id,
        transition_id="run.block",
        action="block_run",
        target="blocked",
        reason=reason,
        clock=clock or SystemClock(),
    )


def exhaust_review_cycles(
    repository_root: str | Path,
    run_id: str,
    *,
    clock: Clock | None = None,
) -> dict[str, Any]:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    with RunLock(paths, run_id, "exhaust_review_cycles", clock):
        manifest = validate_manifest(paths, run_id, validate_artifacts=False)
        if manifest.get("status") != "changes_requested" or int(
            manifest.get("review_cycle", 0)
        ) < int(manifest.get("max_review_cycles", 0)):
            raise InvalidTransitionError("Review repair cycles are not exhausted.")
        now = _timestamp(clock)
        event = {
            "schema_version": "1",
            "event_type": "transition",
            "run_id": run_id,
            "phase": "run",
            "occurred_at": now,
            "action": "exhaust_review_cycles",
            "transition_id": "run.exhaust_review_cycles",
            "from_status": "changes_requested",
            "to_status": "blocked",
            "reason": "maximum review repair cycles exhausted",
        }
        return apply_transition(paths, run_id, manifest, event)


def recover_lock(
    repository_root: str | Path,
    run_id: str,
    *,
    clock: Clock | None = None,
    stale_after_seconds: int = 60 * 60,
) -> dict[str, Any]:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    info = recover_run_lock(
        paths.root,
        run_id,
        clock=clock,
        stale_after_seconds=stale_after_seconds,
    )
    append_event(
        paths.run_events(run_id),
        {
            "schema_version": "1",
            "event_type": "lock_recovered",
            "run_id": run_id,
            "phase": "run",
            "occurred_at": _timestamp(clock),
            "owner_id": info.owner_id,
            "pid": info.pid,
            "hostname": info.hostname,
            "created_at": info.created_at,
            "command": info.command,
        },
    )
    manifest = load_manifest(paths, run_id)
    verify_event_projection(paths, run_id, manifest)
    return {
        "run_id": run_id,
        "recovered_owner_id": info.owner_id,
        "pid": info.pid,
        "hostname": info.hostname,
    }
