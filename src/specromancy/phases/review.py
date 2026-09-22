"""Read-only review lifecycle, evidence validation, and verdict transitions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..artifacts.frontmatter import parse_frontmatter
from ..artifacts.review import ReviewArtifact, validate_review
from ..clock import Clock, SystemClock
from ..commands import load_command_records
from ..errors import (
    ConcurrencyError,
    InvalidTransitionError,
    SpecromancyError,
    ValidationError,
)
from ..git import GitSnapshot, capture_snapshot, snapshot_payload
from ..io import append_json_line, canonical_json, read_text, sha256_file, sha256_text
from ..paths import RepositoryPaths
from ..state import apply_transition
from ..locking import RunLock
from .implement import _baseline_event, validate_implementation_file
from .research import _event, _load_manifest, _timestamp


@dataclass(frozen=True)
class ReviewPhaseResult:
    run_id: str
    status: str
    artifact_path: str
    artifact_sha256: str | None = None
    review_subject_sha256: str | None = None
    replayed: bool = False


def review_artifact_path(repository_root: str | Path, run_id: str) -> Path:
    paths = RepositoryPaths(Path(repository_root))
    _load_manifest(paths, run_id)
    return paths.run_artifact(run_id, "review.md")


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
            phase="review",
            action=action,
            error_code=error.code,
            message=error.message,
        ),
    )


def _requirements(manifest: Mapping[str, Any]) -> list[Mapping[str, object]]:
    requirements = manifest.get("requirements")
    if not isinstance(requirements, list) or not requirements or not all(
        isinstance(item, dict) for item in requirements
    ):
        raise ValidationError(
            "Run requirements are missing or malformed.",
            hint="Restore the initialized requirements before review.",
        )
    return requirements


def _paths_outside_run(
    paths: RepositoryPaths, run_id: str, snapshot: GitSnapshot
) -> set[str]:
    prefix = paths.serialize(paths.run_dir(run_id))
    result: set[str] = set()
    for group in (snapshot.staged_paths, snapshot.unstaged_paths, snapshot.untracked_paths):
        for path in group:
            if path != prefix and not path.startswith(prefix + "/"):
                result.add(path)
    return result


def _artifact_digests(
    paths: RepositoryPaths, run_id: str, manifest: Mapping[str, Any]
) -> dict[str, str]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValidationError("Run artifact records are malformed.")
    result: dict[str, str] = {}
    for name in ("request", "research", "plan", "implementation"):
        record = artifacts.get(name)
        target = paths.run_artifact(run_id, f"{name}.md")
        if not isinstance(record, dict) or not target.is_file():
            raise ValidationError(
                f"Review requires the completed {name} artifact.",
                hint=f"Restore the recorded {name}.md before starting review.",
            )
        digest = sha256_file(target)
        if record.get("sha256") != digest:
            raise ValidationError(
                f"The recorded {name} artifact is stale.",
                hint=f"Restore the accepted {name}.md or return to its owning phase.",
            )
        result[name] = digest
    expected_bindings = {
        "research": {"request": result["request"]},
        "plan": {"research": result["research"]},
    }
    for name, expected in expected_bindings.items():
        record = artifacts[name]
        if record.get("bindings") != expected:
            raise ValidationError(
                f"The {name} artifact no longer matches its recorded inputs.",
                hint=f"Restore the accepted {name} artifact chain before review.",
            )
    implementation_bindings = artifacts["implementation"].get("bindings")
    if not isinstance(implementation_bindings, dict) or implementation_bindings.get(
        "plan"
    ) != result["plan"]:
        raise ValidationError(
            "The implementation artifact no longer matches the approved plan.",
            hint="Restore the completed implementation and its plan binding before review.",
        )
    return result


def _review_subject(
    paths: RepositoryPaths, run_id: str, manifest: Mapping[str, Any]
) -> tuple[str, GitSnapshot, dict[str, str]]:
    digests = _artifact_digests(paths, run_id, manifest)
    validate_implementation_file(paths.root, run_id, record_event=False)
    snapshot = capture_snapshot(paths.root)
    if snapshot.head != manifest.get("git_head"):
        raise ConcurrencyError(
            "Repository HEAD changed after implementation completion.",
            hint="Reconcile the concurrent commit and complete a fresh implementation before review.",
            details={"recorded_head": manifest.get("git_head"), "current_head": snapshot.head},
        )
    changed_files = manifest.get("changed_files")
    if not isinstance(changed_files, list) or not all(
        isinstance(item, dict) for item in changed_files
    ):
        raise ValidationError(
            "Implementation changed-file inventory is malformed.",
            hint="Complete implementation again from a valid recorded inventory.",
        )
    recorded_paths: set[str] = set()
    for item in changed_files:
        path = item.get("path")
        if not isinstance(path, str) or path in recorded_paths:
            raise ValidationError("Implementation changed-file inventory has invalid paths.")
        recorded_paths.add(path)
        target = paths.resolve_relative(path)
        current_hash = sha256_file(target) if target.is_file() else None
        if current_hash != item.get("sha256_after"):
            raise ConcurrencyError(
                f"Repository path '{path}' changed after implementation completion.",
                hint="Restore the implementation subject or complete a fresh implementation before review.",
                details={"path": path},
            )
    current_paths = _paths_outside_run(paths, run_id, snapshot)
    if current_paths != recorded_paths:
        raise ConcurrencyError(
            "Repository changed-file inventory changed after implementation completion.",
            hint="Restore the implementation subject or complete a fresh implementation before review.",
            details={
                "missing_paths": sorted(recorded_paths - current_paths),
                "new_paths": sorted(current_paths - recorded_paths),
            },
        )
    subject = sha256_text(canonical_json(changed_files))
    implementation = manifest["artifacts"]["implementation"]
    bindings = implementation.get("bindings", {})
    if bindings.get("repository_diff") != subject:
        raise ValidationError(
            "Implementation repository-diff binding is stale.",
            hint="Restore the accepted implementation subject before review.",
        )
    baseline = _baseline_event(paths, run_id)
    prior_command_ids = set(baseline.get("baseline_command_ids", []))
    records = [
        record
        for record in load_command_records(paths.root, run_id)
        if record.get("command_id") not in prior_command_ids
    ]
    verification_digest = sha256_text(canonical_json(records))
    if bindings.get("verification") != verification_digest:
        raise ValidationError(
            "Implementation verification records no longer match their recorded digest.",
            hint="Restore the accepted command records before review.",
        )
    return subject, snapshot, digests


def _findings_from_previous_review(
    paths: RepositoryPaths, run_id: str, manifest: Mapping[str, Any]
) -> tuple[str, ...]:
    if int(manifest.get("review_cycle", 0)) == 0:
        return ()
    record = manifest.get("artifacts", {}).get("review")
    target = paths.run_artifact(run_id, "review.md")
    if not isinstance(record, dict) or not target.is_file() or record.get(
        "sha256"
    ) != sha256_file(target):
        raise ValidationError(
            "Repair review requires the immediately preceding review artifact.",
            hint="Restore the recorded changes-requested review before starting the repair review.",
        )
    document = parse_frontmatter(
        read_text(target),
        expected_run_id=run_id,
        expected_stage="review",
        expected_status="changes_requested",
    )
    section = document.body.partition("## Findings")[2]
    if "\n## " in section:
        section = section.partition("\n## ")[0]
    identifiers = tuple(
        dict.fromkeys(
            match.group(1)
            for line in section.splitlines()
            if (match := re.match(r"^\|\s*(REV-[0-9]{3,})\s*\|", line.strip()))
        )
    )
    if not identifiers:
        raise ValidationError(
            "The preceding changes-requested review contains no finding IDs.",
            hint="Restore the validated review with its stable REV-NNN findings.",
        )
    return identifiers


def _review_start_event(paths: RepositoryPaths, run_id: str) -> Mapping[str, Any]:
    latest: Mapping[str, Any] | None = None
    for line_number, line in enumerate(
        read_text(paths.run_events(run_id)).splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "Run event log contains malformed JSON.",
                hint=f"Repair events.jsonl line {line_number} before review completion.",
            ) from exc
        if (
            isinstance(value, dict)
            and value.get("event_type") == "transition"
            and value.get("transition_id") == "review.start"
        ):
            latest = value
    if latest is None:
        raise ValidationError(
            "Review start event is missing.",
            hint="Restart review from a current completed implementation.",
        )
    return latest


def start_review(
    repository_root: str | Path, run_id: str, *, clock: Clock | None = None
) -> ReviewPhaseResult:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    _load_manifest(paths, run_id)
    try:
        with RunLock(paths, run_id, "start_review", clock):
            manifest = _load_manifest(paths, run_id)
            status = manifest.get("status")
            if status == "review_in_progress":
                subject, _, _ = _review_subject(paths, run_id, manifest)
                if subject != manifest.get("review_subject_sha256"):
                    raise ConcurrencyError(
                        "In-progress review subject no longer matches its recorded digest.",
                        hint="Restore the subject before resuming review.",
                    )
                return ReviewPhaseResult(
                    run_id,
                    "review_in_progress",
                    paths.serialize(paths.run_artifact(run_id, "review.md")),
                    review_subject_sha256=subject,
                    replayed=True,
                )
            if status != "implementation_ready":
                raise InvalidTransitionError(
                    f"Review cannot start while the run is '{status}'.",
                    hint="Start review only from implementation_ready.",
                    details={"status": status},
                )
            prior_findings = _findings_from_previous_review(paths, run_id, manifest)
            subject, snapshot, digests = _review_subject(paths, run_id, manifest)
            now = _timestamp(clock)
            event = _event(
                event_type="transition",
                run_id=run_id,
                occurred_at=now,
                phase="review",
                action="start_review",
                transition_id="review.start",
                from_status="implementation_ready",
                to_status="review_in_progress",
                review_subject_sha256=subject,
                artifact_digests=digests,
                baseline_snapshot=snapshot_payload(snapshot),
                prior_finding_ids=list(prior_findings),
            )
            apply_transition(
                paths,
                run_id,
                manifest,
                event,
                manifest_updates={"review_subject_sha256": subject},
            )
            return ReviewPhaseResult(
                run_id,
                "review_in_progress",
                paths.serialize(paths.run_artifact(run_id, "review.md")),
                review_subject_sha256=subject,
            )
    except SpecromancyError as exc:
        if isinstance(exc, ConcurrencyError):
            raise
        _append_failure(paths, run_id, exc, action="start_review", clock=clock)
        raise


def validate_review_file(
    repository_root: str | Path,
    run_id: str,
    *,
    record_event: bool = True,
    clock: Clock | None = None,
) -> ReviewArtifact:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    manifest = _load_manifest(paths, run_id)

    def validate_current() -> ReviewArtifact:
        target = paths.run_artifact(run_id, "review.md")
        if not target.is_file():
            raise ValidationError(
                "Review artifact is missing.",
                hint="Create review.md from the canonical template and retry.",
                path=paths.serialize(target),
            )
        event = _review_start_event(paths, run_id)
        prior = event.get("prior_finding_ids", [])
        if not isinstance(prior, list) or not all(isinstance(item, str) for item in prior):
            raise ValidationError("Review start event has malformed prior finding IDs.")
        return validate_review(
            read_text(target),
            run_id,
            _requirements(manifest),
            prior_finding_ids=prior,
        )

    if not record_event:
        return validate_current()
    with RunLock(paths, run_id, "validate_review", clock):
        try:
            artifact = validate_current()
        except SpecromancyError as exc:
            _append_failure(paths, run_id, exc, action="validate_review", clock=clock)
            raise
        target = paths.run_artifact(run_id, "review.md")
        append_json_line(
            paths.run_events(run_id),
            _event(
                event_type="validation",
                run_id=run_id,
                occurred_at=_timestamp(clock),
                phase="review",
                action="validate_review",
                outcome="passed",
                artifact="review",
                artifact_sha256=sha256_file(target),
                verdict=artifact.verdict,
            ),
        )
        return artifact


def complete_review(
    repository_root: str | Path, run_id: str, *, clock: Clock | None = None
) -> ReviewPhaseResult:
    paths = RepositoryPaths(Path(repository_root))
    clock = clock or SystemClock()
    _load_manifest(paths, run_id)
    try:
        with RunLock(paths, run_id, "complete_review", clock):
            manifest = _load_manifest(paths, run_id)
            target = paths.run_artifact(run_id, "review.md")
            if manifest.get("status") in {"passed", "changes_requested", "blocked"}:
                record = manifest.get("artifacts", {}).get("review")
                if not isinstance(record, dict) or not target.is_file():
                    raise InvalidTransitionError(
                        f"Review cannot complete while the run is '{manifest.get('status')}'.",
                        hint="Only a status produced by a completed review can be replayed.",
                    )
                artifact = validate_review_file(
                    paths.root, run_id, record_event=False, clock=clock
                )
                subject, _, digests = _review_subject(paths, run_id, manifest)
                expected = {
                    **digests,
                    "repository_diff": subject,
                }
                if (
                    artifact.verdict == manifest.get("status")
                    and record.get("sha256") == sha256_file(target)
                    and record.get("bindings") == expected
                    and manifest.get("review_subject_sha256") == subject
                ):
                    return ReviewPhaseResult(
                        run_id,
                        str(manifest["status"]),
                        paths.serialize(target),
                        str(record["sha256"]),
                        subject,
                        True,
                    )
                raise ValidationError(
                    "Completed review no longer matches its recorded artifact or subject.",
                    hint="Restore the accepted review and repository subject before replaying completion.",
                )
            if manifest.get("status") != "review_in_progress":
                raise InvalidTransitionError(
                    f"Review cannot complete while the run is '{manifest.get('status')}'.",
                    hint="Start review from a completed implementation first.",
                )
            event = _review_start_event(paths, run_id)
            subject, _, digests = _review_subject(paths, run_id, manifest)
            recorded_subject = manifest.get("review_subject_sha256")
            if subject != recorded_subject or subject != event.get("review_subject_sha256"):
                    raise ConcurrencyError(
                        "Repository diff changed while review was in progress.",
                        hint=(
                            "Restore the reviewed subject or complete a fresh implementation "
                            "and restart review."
                        ),
                    details={"recorded_subject": recorded_subject, "current_subject": subject},
                )
            if event.get("artifact_digests") != digests:
                raise ConcurrencyError(
                    "A required artifact changed while review was in progress.",
                    hint="Restore the review inputs or restart from their owning phase.",
                )
            artifact = validate_review_file(
                paths.root, run_id, record_event=False, clock=clock
            )
            target_status = artifact.verdict
            transition_id = {
                "passed": "review.pass",
                "changes_requested": "review.request_changes",
                "blocked": "review.block",
            }[target_status]
            action = {
                "passed": "pass_review",
                "changes_requested": "request_changes",
                "blocked": "block_review",
            }[target_status]
            digest = sha256_file(target)
            bindings = {**digests, "repository_diff": subject}
            now = _timestamp(clock)
            transition = _event(
                event_type="transition",
                run_id=run_id,
                occurred_at=now,
                phase="review",
                action=action,
                transition_id=transition_id,
                from_status="review_in_progress",
                to_status=target_status,
                artifact="review",
                artifact_sha256=digest,
                bindings=bindings,
                verdict=target_status,
                finding_ids=[finding.finding_id for finding in artifact.findings],
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
                transition,
                artifact_name="review",
                artifact_record=record,
            )
            return ReviewPhaseResult(
                run_id,
                target_status,
                paths.serialize(target),
                digest,
                subject,
            )
    except SpecromancyError as exc:
        if isinstance(exc, ConcurrencyError):
            raise
        _append_failure(paths, run_id, exc, action="complete_review", clock=clock)
        raise
