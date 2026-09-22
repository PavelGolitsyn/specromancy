"""Implementation lifecycle, scope enforcement, locking, and completion."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..artifacts.frontmatter import parse_frontmatter
from ..artifacts.implementation import ImplementationArtifact, validate_implementation
from ..clock import Clock, SystemClock
from ..commands import load_command_records, run_verification_command
from ..errors import (
    ApprovalRequiredError,
    ConcurrencyError,
    ExternalCommandError,
    InvalidInputError,
    InvalidTransitionError,
    SpecromancyError,
    ValidationError,
)
from ..git import GitSnapshot, capture_snapshot, snapshot_payload
from ..io import (
    append_json_line,
    canonical_json,
    read_text,
    sha256_file,
    sha256_text,
)
from ..locking import RunLock, RunLockInfo, inspect_run_lock
from ..paths import RepositoryPaths
from ..state import apply_transition
from .plan import _active_approvals, validate_plan_file
from .research import _append_failure, _event, _load_manifest, _timestamp


@dataclass(frozen=True)
class ImplementationPhaseResult:
    run_id: str
    status: str
    artifact_path: str
    artifact_sha256: str | None = None
    changed_files: tuple[Mapping[str, Any], ...] = ()
    replayed: bool = False


def implementation_artifact_path(repository_root: str | Path, run_id: str) -> Path:
    paths = RepositoryPaths(Path(repository_root))
    _load_manifest(paths, run_id)
    return paths.run_artifact(run_id, "implementation.md")


def _plan_approval(
    paths: RepositoryPaths, run_id: str, manifest: Mapping[str, Any]
) -> tuple[str, Mapping[str, Any]]:
    target = paths.run_artifact(run_id, "plan.md")
    record = manifest.get("artifacts", {}).get("plan")
    if not target.is_file() or not isinstance(record, dict):
        raise ApprovalRequiredError(
            "Implementation requires a completed approved plan.",
            hint="Restore, complete, and explicitly approve the plan first.",
        )
    digest = sha256_file(target)
    active = _active_approvals(manifest)
    if record.get("sha256") != digest or len(active) != 1 or active[0].get("artifact_sha256") != digest:
        raise ApprovalRequiredError(
            "The active approval does not match the current plan digest.",
            hint="Restore the approved plan or revoke, replan, and approve the revised digest.",
        )
    return digest, active[0]


def _paths_outside_run(paths: RepositoryPaths, run_id: str, snapshot: GitSnapshot) -> set[str]:
    prefix = paths.serialize(paths.run_dir(run_id))
    result: set[str] = set()
    for group in (snapshot.staged_paths, snapshot.unstaged_paths, snapshot.untracked_paths):
        for path in group:
            if path != prefix and not path.startswith(prefix + "/"):
                result.add(path)
    return result


def _baseline_event(paths: RepositoryPaths, run_id: str) -> Mapping[str, Any]:
    latest: Mapping[str, Any] | None = None
    for line_number, line in enumerate(read_text(paths.run_events(run_id)).splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "Run event log contains malformed JSON.",
                hint=f"Repair events.jsonl line {line_number} before implementation completion.",
            ) from exc
        if (
            isinstance(value, dict)
            and value.get("event_type") == "transition"
            and value.get("transition_id") in {"implementation.start", "implementation.start_repair"}
            and isinstance(value.get("baseline_snapshot"), dict)
        ):
            latest = value
    if latest is None:
        raise ValidationError(
            "Implementation baseline event is missing.",
            hint="Restart implementation from the approved plan before making changes.",
        )
    return latest


def _review_findings(paths: RepositoryPaths, run_id: str, manifest: Mapping[str, Any]) -> tuple[str, ...]:
    target = paths.run_artifact(run_id, "review.md")
    record = manifest.get("artifacts", {}).get("review")
    if not target.is_file() or not isinstance(record, dict) or record.get("sha256") != sha256_file(target):
        raise ValidationError(
            "Repair requires the current recorded review artifact.",
            hint="Restore the changes-requested review before starting repair.",
        )
    document = parse_frontmatter(
        read_text(target), expected_run_id=run_id, expected_stage="review", expected_status="changes_requested"
    )
    body = document.body
    findings_section = body.partition("## Findings")[2]
    if "\n## " in findings_section:
        findings_section = findings_section.partition("\n## ")[0]
    identifiers = tuple(dict.fromkeys(re.findall(r"REV-[0-9]{3,}", findings_section)))
    if not identifiers:
        raise ValidationError(
            "Changes-requested review contains no repair finding IDs.",
            hint="Record at least one REV-NNN finding before starting repair.",
        )
    return identifiers


def _start(
    paths: RepositoryPaths,
    run_id: str,
    manifest: dict[str, Any],
    *,
    clock: Clock,
    repair: bool,
) -> ImplementationPhaseResult:
    status = manifest.get("status")
    expected = "changes_requested" if repair else "plan_approved"
    if status == "implementation_in_progress":
        baseline = manifest.get("implementation_baseline")
        if not isinstance(baseline, dict):
            raise ValidationError("In-progress implementation has no recorded baseline.")
        _plan_approval(paths, run_id, manifest)
        return ImplementationPhaseResult(
            run_id, status, paths.serialize(paths.run_artifact(run_id, "implementation.md")), replayed=True
        )
    if status != expected:
        if not repair and status in {"plan_ready", "research_ready", "plan_in_progress"}:
            raise ApprovalRequiredError(
                f"Implementation cannot start while the run is '{status}'.",
                hint="Complete and explicitly approve the current plan first.",
            )
        raise InvalidTransitionError(
            f"{'Repair' if repair else 'Implementation'} cannot start while the run is '{status}'.",
            hint=f"Start this action only from {expected}.",
            details={"status": status},
        )
    plan_digest, _ = _plan_approval(paths, run_id, manifest)
    plan = validate_plan_file(
        paths.root,
        run_id,
        record_event=False,
        clock=clock,
        implementation_context=repair,
    )
    finding_ids: tuple[str, ...] = ()
    review_cycle = int(manifest.get("review_cycle", 0))
    if repair:
        maximum = int(manifest.get("max_review_cycles", 0))
        if review_cycle >= maximum:
            raise InvalidTransitionError(
                "The implementation repair-cycle limit has been reached.",
                hint="The run must be blocked or explicitly replanned under a new authorization.",
                details={"review_cycle": review_cycle, "max_review_cycles": maximum},
            )
        finding_ids = _review_findings(paths, run_id, manifest)
        review_cycle += 1
    snapshot = capture_snapshot(paths.root, additional_paths=plan.planned_paths)
    user_paths = sorted(_paths_outside_run(paths, run_id, snapshot))
    now = _timestamp(clock)
    baseline = {
        "recorded_at": now,
        "git_head": snapshot.head,
        "staged_paths": list(snapshot.staged_paths),
        "unstaged_paths": list(snapshot.unstaged_paths),
        "untracked_paths": list(snapshot.untracked_paths),
        "plan_paths": list(plan.planned_paths),
        "user_modified_paths": user_paths,
    }
    command_ids = [str(record.get("command_id")) for record in load_command_records(paths.root, run_id)]
    transition_id = "implementation.start_repair" if repair else "implementation.start"
    baseline_payload = snapshot_payload(snapshot)
    baseline_payload["planned_paths"] = list(plan.planned_paths)
    event = _event(
        event_type="transition",
        run_id=run_id,
        occurred_at=now,
        phase="implementation",
        action="start_repair" if repair else "start_implementation",
        transition_id=transition_id,
        from_status=expected,
        to_status="implementation_in_progress",
        plan_sha256=plan_digest,
        baseline_snapshot=baseline_payload,
        baseline_command_ids=command_ids,
        repair_finding_ids=list(finding_ids),
    )
    updates: dict[str, Any] = {
        "implementation_baseline": baseline,
        "git_head": snapshot.head,
        "git_branch": snapshot.branch,
    }
    if repair:
        updates["review_cycle"] = review_cycle
    apply_transition(paths, run_id, manifest, event, manifest_updates=updates)
    return ImplementationPhaseResult(
        run_id=run_id,
        status="implementation_in_progress",
        artifact_path=paths.serialize(paths.run_artifact(run_id, "implementation.md")),
    )


def start_implementation(
    repository_root: str | Path, run_id: str, *, clock: Clock | None = None
) -> ImplementationPhaseResult:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    _load_manifest(paths, run_id)
    try:
        with RunLock(paths, run_id, "start_implementation", clock):
            return _start(paths, run_id, _load_manifest(paths, run_id), clock=clock, repair=False)
    except SpecromancyError as exc:
        if isinstance(exc, ConcurrencyError):
            raise
        _append_failure(paths, run_id, exc, action="start_implementation", clock=clock)
        raise


def start_repair(
    repository_root: str | Path, run_id: str, *, clock: Clock | None = None
) -> ImplementationPhaseResult:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    _load_manifest(paths, run_id)
    try:
        with RunLock(paths, run_id, "start_repair", clock):
            return _start(paths, run_id, _load_manifest(paths, run_id), clock=clock, repair=True)
    except SpecromancyError as exc:
        if isinstance(exc, ConcurrencyError):
            raise
        _append_failure(paths, run_id, exc, action="start_repair", clock=clock)
        raise


def validate_implementation_file(
    repository_root: str | Path,
    run_id: str,
    *,
    record_event: bool = True,
    clock: Clock | None = None,
) -> ImplementationArtifact:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    _load_manifest(paths, run_id)

    def validate_current() -> ImplementationArtifact:
        _load_manifest(paths, run_id)
        target = paths.run_artifact(run_id, "implementation.md")
        if not target.is_file():
            raise ValidationError(
                "Implementation artifact is missing.",
                hint="Create implementation.md from the canonical template and retry.",
                path=paths.serialize(target),
            )
        plan = validate_plan_file(
            paths.root,
            run_id,
            record_event=False,
            implementation_context=True,
        )
        return validate_implementation(
            read_text(target), paths.root, run_id, [item.change_id for item in plan.proposed_changes]
        )

    if not record_event:
        return validate_current()
    with RunLock(paths, run_id, "validate_implementation", clock):
        try:
            artifact = validate_current()
        except SpecromancyError as exc:
            _append_failure(paths, run_id, exc, action="validate_implementation", clock=clock)
            raise
        target = paths.run_artifact(run_id, "implementation.md")
        append_json_line(
            paths.run_events(run_id),
            _event(
                event_type="validation",
                run_id=run_id,
                occurred_at=_timestamp(clock),
                phase="implementation",
                action="validate_implementation",
                outcome="passed",
                artifact="implementation",
                artifact_sha256=sha256_file(target),
            ),
        )
        return artifact


def _path_is_planned(path: str, planned_paths: Sequence[str]) -> bool:
    return any(path == planned or path.startswith(planned.rstrip("/") + "/") for planned in planned_paths)


def _changed_inventory(
    paths: RepositoryPaths,
    run_id: str,
    baseline_event: Mapping[str, Any],
    current: GitSnapshot,
    artifact: ImplementationArtifact,
) -> list[dict[str, Any]]:
    baseline = baseline_event["baseline_snapshot"]
    before_hashes = baseline.get("hashes", {})
    if not isinstance(before_hashes, dict):
        raise ValidationError("Implementation baseline hashes are malformed.")
    baseline_paths = set(baseline.get("staged_paths", [])) | set(baseline.get("unstaged_paths", [])) | set(baseline.get("untracked_paths", []))
    current_paths = _paths_outside_run(paths, run_id, current)
    paths_to_record = baseline_paths | current_paths
    declarations = {item.path: item for item in artifact.files}
    if set(declarations) != paths_to_record:
        raise ValidationError(
            "Implementation file inventory does not match the current Git inventory.",
            hint="List every current and pre-existing changed path exactly once.",
            details={
                "missing_paths": sorted(paths_to_record - set(declarations)),
                "extra_paths": sorted(set(declarations) - paths_to_record),
            },
        )
    planned_paths = baseline_event.get("baseline_snapshot", {}).get("planned_paths")
    if not isinstance(planned_paths, list):
        manifest_baseline = baseline_event.get("plan_paths", [])
        planned_paths = manifest_baseline if isinstance(manifest_baseline, list) else []
    # Older start events store plan paths in the manifest-shaped event sibling.
    if not planned_paths:
        planned_paths = list(baseline_event.get("implementation_baseline", {}).get("plan_paths", [])) if isinstance(baseline_event.get("implementation_baseline"), dict) else []
    if not planned_paths:
        # New events can derive them from the declaration only after checking the plan below.
        plan = validate_plan_file(paths.root, run_id, record_event=False, implementation_context=True)
        planned_paths = list(plan.planned_paths)
    inventory: list[dict[str, Any]] = []
    unexplained: list[str] = []
    for path in sorted(paths_to_record):
        before = before_hashes.get(path)
        target = paths.resolve_relative(path)
        after = sha256_file(target) if target.is_file() else None
        declaration = declarations[path]
        unchanged_preexisting = path in baseline_paths and before == after
        if unchanged_preexisting:
            classification = "pre_existing_user_change"
        elif _path_is_planned(path, planned_paths):
            classification = "planned"
        elif declaration.classification in {"generated", "implied_support", "approved_deviation"}:
            classification = declaration.classification
        else:
            classification = "unexplained"
            unexplained.append(path)
        if declaration.classification != classification:
            raise ValidationError(
                f"Changed file '{path}' has an incorrect classification.",
                hint=f"Classify it as {classification}, or revise the approved scope before completion.",
            )
        inventory.append(
            {
                "path": path,
                "classification": classification,
                "sha256_before": before,
                "sha256_after": after,
            }
        )
    if unexplained:
        raise ValidationError(
            "Implementation contains unexplained changed files.",
            hint="Document legitimate support work or restore changes introduced outside approved scope.",
            details={"unexplained_paths": unexplained},
        )
    return inventory


def _verification_records(
    paths: RepositoryPaths,
    run_id: str,
    baseline_event: Mapping[str, Any],
    artifact: ImplementationArtifact,
) -> list[Mapping[str, Any]]:
    prior = set(baseline_event.get("baseline_command_ids", []))
    records = [record for record in load_command_records(paths.root, run_id) if record.get("command_id") not in prior]
    if not records:
        raise ValidationError(
            "Implementation has no verification command records.",
            hint="Run focused and broader checks through the command-record helper before completion.",
        )
    declarations = {item.command_id: item for item in artifact.verifications}
    record_ids = {str(record.get("command_id")) for record in records}
    if set(declarations) != record_ids:
        raise ValidationError(
            "Implementation verification table does not match persisted command records.",
            hint="Reference each current-cycle CMD-NNN record exactly once.",
            details={"record_ids": sorted(record_ids), "declared_ids": sorted(declarations)},
        )
    for record in records:
        command_id = str(record.get("command_id"))
        declaration = declarations[command_id]
        exit_code = record.get("exit_code")
        blocking = record.get("blocking")
        if declaration.exit_code != exit_code or declaration.blocking is not blocking:
            raise ValidationError(
                f"Verification declaration for '{command_id}' does not match its command record.",
                hint="Copy the recorded exit code and blocking flag into implementation.md.",
            )
        if blocking and exit_code != 0:
            raise ExternalCommandError(
                f"Blocking verification command '{command_id}' failed.",
                hint="Fix the implementation or test, rerun verification, and record the new result.",
                details={"command_id": command_id, "exit_code": exit_code},
            )
        if exit_code != 0 and not record.get("failure_reason"):
            raise ValidationError(
                f"Nonblocking failed command '{command_id}' has no recorded rationale.",
                hint="Record why this failure does not block independent review.",
            )
    return records


def complete_implementation(
    repository_root: str | Path, run_id: str, *, clock: Clock | None = None
) -> ImplementationPhaseResult:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    _load_manifest(paths, run_id)
    try:
        with RunLock(paths, run_id, "complete_implementation", clock):
            manifest = _load_manifest(paths, run_id)
            target = paths.run_artifact(run_id, "implementation.md")
            if manifest.get("status") == "implementation_ready":
                plan_digest, _ = _plan_approval(paths, run_id, manifest)
                digest = sha256_file(target)
                record = manifest.get("artifacts", {}).get("implementation")
                recorded_files = manifest.get("changed_files", [])
                current = capture_snapshot(paths.root)
                current_paths = _paths_outside_run(paths, run_id, current)
                recorded_paths = {
                    item.get("path") for item in recorded_files if isinstance(item, dict)
                }
                files_current = current_paths == recorded_paths
                if files_current:
                    for item in recorded_files:
                        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                            files_current = False
                            break
                        file_target = paths.resolve_relative(item["path"])
                        current_hash = sha256_file(file_target) if file_target.is_file() else None
                        if current_hash != item.get("sha256_after"):
                            files_current = False
                            break
                if (
                    isinstance(record, dict)
                    and record.get("sha256") == digest
                    and record.get("bindings", {}).get("plan") == plan_digest
                    and current.head == manifest.get("git_head")
                    and files_current
                ):
                    return ImplementationPhaseResult(
                        run_id,
                        "implementation_ready",
                        paths.serialize(target),
                        digest,
                        tuple(manifest.get("changed_files", [])),
                        True,
                    )
                raise ValidationError(
                    "Completed implementation no longer matches its recorded inputs or repository state.",
                    hint="Restore the accepted plan, implementation artifact, and repository changes before replaying completion.",
                )
            if manifest.get("status") != "implementation_in_progress":
                raise InvalidTransitionError(
                    f"Implementation cannot complete while the run is '{manifest.get('status')}'.",
                    hint="Start implementation or repair before completing it.",
                )
            plan_digest, _ = _plan_approval(paths, run_id, manifest)
            baseline_event = _baseline_event(paths, run_id)
            baseline = baseline_event["baseline_snapshot"]
            current = capture_snapshot(paths.root)
            if current.head != baseline.get("git_head"):
                raise ConcurrencyError(
                    "Repository HEAD changed after implementation started.",
                    hint="Reconcile the concurrent commit and restart implementation from a new approved baseline.",
                    details={"baseline_head": baseline.get("git_head"), "current_head": current.head},
                )
            artifact = validate_implementation_file(paths.root, run_id, record_event=False, clock=clock)
            material = [item.deviation_id for item in artifact.deviations if item.material]
            if material:
                raise ApprovalRequiredError(
                    "Implementation contains material deviations from the approved plan.",
                    hint="Return to planning, revise the plan, and obtain approval for the changed scope.",
                    details={"material_deviation_ids": material},
                )
            claimed_approvals = [
                item.path for item in artifact.files if item.classification == "approved_deviation"
            ]
            if claimed_approvals:
                raise ApprovalRequiredError(
                    "Implementation claims deviations that are not covered by the approved plan digest.",
                    hint="Revise and approve the plan so these paths become planned changes.",
                    details={"deviation_paths": claimed_approvals},
                )
            records = _verification_records(paths, run_id, baseline_event, artifact)
            inventory = _changed_inventory(paths, run_id, baseline_event, current, artifact)
            required_findings = set(baseline_event.get("repair_finding_ids", []))
            missing_findings = sorted(required_findings - set(artifact.addressed_findings))
            if missing_findings:
                raise ValidationError(
                    "Repair implementation does not account for every review finding.",
                    hint="Add one Review handoff row for each current REV-NNN finding.",
                    details={"missing_finding_ids": missing_findings},
                )
            digest = sha256_file(target)
            diff_digest = sha256_text(canonical_json(inventory))
            verification_digest = sha256_text(canonical_json(records))
            now = _timestamp(clock)
            bindings = {
                "plan": plan_digest,
                "repository_diff": diff_digest,
                "verification": verification_digest,
            }
            event = _event(
                event_type="transition",
                run_id=run_id,
                occurred_at=now,
                phase="implementation",
                action="complete_implementation",
                transition_id="implementation.complete",
                from_status="implementation_in_progress",
                to_status="implementation_ready",
                artifact="implementation",
                artifact_sha256=digest,
                bindings=bindings,
                changed_files=inventory,
                command_ids=[record.get("command_id") for record in records],
            )
            record = {
                "path": paths.serialize(target),
                "sha256": digest,
                "validated_at": now,
                "schema_version": "1",
                "bindings": bindings,
            }
            apply_transition(
                paths,
                run_id,
                manifest,
                event,
                artifact_name="implementation",
                artifact_record=record,
                manifest_updates={
                    "git_head": current.head,
                    "git_branch": current.branch,
                    "changed_files": inventory,
                },
            )
            return ImplementationPhaseResult(
                run_id,
                "implementation_ready",
                paths.serialize(target),
                digest,
                tuple(inventory),
            )
    except SpecromancyError as exc:
        if isinstance(exc, ConcurrencyError):
            raise
        _append_failure(paths, run_id, exc, action="complete_implementation", clock=clock)
        raise


def abort_implementation(
    repository_root: str | Path,
    run_id: str,
    *,
    reason: str,
    clock: Clock | None = None,
) -> ImplementationPhaseResult:
    explanation = reason.strip()
    if not explanation or len(explanation) > 1000:
        raise InvalidInputError("Implementation abort requires a reason of 1 to 1000 characters.")
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    _load_manifest(paths, run_id)
    with RunLock(paths, run_id, "abort_implementation", clock):
        manifest = _load_manifest(paths, run_id)
        if manifest.get("status") != "implementation_in_progress":
            raise InvalidTransitionError("Only an in-progress implementation can be aborted.")
        event = _event(
            event_type="transition",
            run_id=run_id,
            occurred_at=_timestamp(clock),
            phase="run",
            action="block_run",
            transition_id="run.block",
            from_status="implementation_in_progress",
            to_status="blocked",
            reason=explanation,
        )
        apply_transition(paths, run_id, manifest, event)
    return ImplementationPhaseResult(
        run_id, "blocked", paths.serialize(paths.run_artifact(run_id, "implementation.md"))
    )


def execute_verification(
    repository_root: str | Path,
    run_id: str,
    argv: Sequence[str],
    **kwargs: Any,
):
    """Implementation-aware wrapper around the durable command helper."""

    paths = RepositoryPaths(Path(repository_root))
    clock = kwargs.pop("clock", None) or SystemClock()
    _load_manifest(paths, run_id)
    with RunLock(paths, run_id, "execute_verification", clock):
        manifest = _load_manifest(paths, run_id)
        if manifest.get("status") != "implementation_in_progress":
            raise InvalidTransitionError("Verification can run only during implementation.")
        result = run_verification_command(
            paths.root, run_id, argv, clock=clock, **kwargs
        )
        append_json_line(
            paths.run_events(run_id),
            _event(
                event_type="command",
                run_id=run_id,
                occurred_at=result.ended_at,
                phase="implementation",
                action="execute_verification",
                command_id=result.command_id,
                exit_code=result.exit_code,
                blocking=result.blocking,
                record_path=result.record_path,
            ),
        )
        return result


start = start_implementation
complete = complete_implementation
repair = start_repair
abort = abort_implementation
fail_implementation = abort_implementation
