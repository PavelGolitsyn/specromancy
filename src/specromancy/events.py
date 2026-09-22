"""Append-only event loading, replay, and projection verification."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import pipeline_contract
from .errors import ValidationError
from .io import append_json_line, read_text
from .paths import RepositoryPaths


@dataclass(frozen=True)
class EventProjection:
    run_id: str
    status: str
    current_phase: str | None
    review_cycle: int
    transition_count: int
    artifact_sha256s: Mapping[str, str]
    active_plan_sha256: str | None
    changed_files: tuple[Mapping[str, Any], ...] | None
    review_subject_sha256: str | None


def load_events(path: str | Path) -> tuple[dict[str, Any], ...]:
    target = Path(path)
    if not target.is_file():
        raise ValidationError(
            "Run event log is missing.",
            hint="Restore events.jsonl before resuming the run.",
            path=str(target),
        )
    result: list[dict[str, Any]] = []
    for line_number, line in enumerate(read_text(target).splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "Run event log contains malformed JSON.",
                hint=f"Repair events.jsonl line {line_number} from trusted evidence.",
                path=str(target),
                details={"line": line_number},
            ) from exc
        if not isinstance(value, dict):
            raise ValidationError(
                "Run event log entries must be JSON objects.",
                path=str(target),
                details={"line": line_number},
            )
        result.append(value)
    if not result:
        raise ValidationError("Run event log is empty.", path=str(target))
    return tuple(result)


def append_event(path: str | Path, event: Mapping[str, Any]) -> None:
    append_json_line(path, dict(event))


def _transition_by_id() -> dict[str, Mapping[str, Any]]:
    rows = pipeline_contract().get("transitions", [])
    return {
        str(row["id"]): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }


def replay_events(events: Iterable[Mapping[str, Any]], run_id: str) -> EventProjection:
    status: str | None = None
    review_cycle = 0
    transition_count = 0
    artifact_sha256s: dict[str, str] = {}
    active_plan_sha256: str | None = None
    changed_files: tuple[Mapping[str, Any], ...] | None = None
    review_subject_sha256: str | None = None
    transitions = _transition_by_id()
    phases = pipeline_contract().get("status_current_phase", {})
    saw_initial = False
    for index, event in enumerate(events, start=1):
        if event.get("run_id") != run_id:
            raise ValidationError(
                "Run event belongs to a different run.",
                details={"event_index": index, "run_id": event.get("run_id")},
            )
        event_type = event.get("event_type")
        if event_type == "run_initialized":
            if saw_initial or status is not None or event.get("status") != "initialized":
                raise ValidationError(
                    "Run initialization event is duplicated or malformed.",
                    details={"event_index": index},
                )
            status = "initialized"
            saw_initial = True
            request_sha256 = event.get("request_sha256")
            if isinstance(request_sha256, str):
                artifact_sha256s["request"] = request_sha256
            continue
        if event_type != "transition":
            continue
        if status is None:
            # Stage 2-5 fixture runs predate Stage 6 initialization events.
            source = event.get("from_status")
            if source != "initialized":
                raise ValidationError(
                    "Event replay cannot infer the initial run status.",
                    details={"event_index": index},
                )
            status = "initialized"
        transition_id = event.get("transition_id")
        contract = transitions.get(str(transition_id))
        if contract is None:
            raise ValidationError(
                "Run event names an unknown transition.",
                details={"event_index": index, "transition_id": transition_id},
            )
        source = event.get("from_status")
        target = event.get("to_status")
        allowed = (
            [contract.get("from")]
            if "from" in contract
            else contract.get("allowed_from", [])
        )
        if status != source or source not in allowed or target != contract.get("to"):
            raise ValidationError(
                "Run event transition chain is inconsistent.",
                details={
                    "event_index": index,
                    "projected_status": status,
                    "from_status": source,
                    "to_status": target,
                    "transition_id": transition_id,
                },
            )
        if transition_id == "implementation.start_repair":
            review_cycle += 1
        artifact = event.get("artifact")
        artifact_sha256 = event.get("artifact_sha256")
        if isinstance(artifact, str) and isinstance(artifact_sha256, str):
            artifact_sha256s[artifact] = artifact_sha256
        if transition_id == "plan.approve":
            active_plan_sha256 = (
                artifact_sha256 if isinstance(artifact_sha256, str) else None
            )
        elif transition_id == "plan.revoke_approval":
            active_plan_sha256 = None
        event_files = event.get("changed_files")
        if transition_id == "implementation.complete" and isinstance(event_files, list):
            if not all(isinstance(item, dict) for item in event_files):
                raise ValidationError(
                    "Implementation transition has malformed changed files.",
                    details={"event_index": index},
                )
            changed_files = tuple(event_files)
        subject = event.get("review_subject_sha256")
        if transition_id == "review.start" and isinstance(subject, str):
            review_subject_sha256 = subject
        status = str(target)
        transition_count += 1
    if status is None:
        raise ValidationError("Event log has no initialization or transition event.")
    return EventProjection(
        run_id=run_id,
        status=status,
        current_phase=phases.get(status),
        review_cycle=review_cycle,
        transition_count=transition_count,
        artifact_sha256s=artifact_sha256s,
        active_plan_sha256=active_plan_sha256,
        changed_files=changed_files,
        review_subject_sha256=review_subject_sha256,
    )


def verify_event_projection(
    paths: RepositoryPaths, run_id: str, manifest: Mapping[str, Any]
) -> EventProjection:
    projection = replay_events(load_events(paths.run_events(run_id)), run_id)
    mismatches: dict[str, Any] = {}
    for field in ("status", "current_phase"):
        expected = getattr(projection, field)
        if manifest.get(field) != expected:
            mismatches[field] = {
                "event_projection": expected,
                "manifest": manifest.get(field),
            }
    if int(manifest.get("review_cycle", 0)) != projection.review_cycle:
        mismatches["review_cycle"] = {
            "event_projection": projection.review_cycle,
            "manifest": manifest.get("review_cycle"),
        }
    records = manifest.get("artifacts", {})
    if isinstance(records, dict):
        manifest_digests = {
            name: record.get("sha256")
            for name, record in records.items()
            if isinstance(record, dict)
        }
        for name, digest in projection.artifact_sha256s.items():
            if manifest_digests.get(name) != digest:
                mismatches[f"artifact:{name}"] = {
                    "event_projection": digest,
                    "manifest": manifest_digests.get(name),
                }
    approvals = manifest.get("approvals", [])
    active = [
        item
        for item in approvals
        if isinstance(item, dict) and item.get("status") == "active"
    ] if isinstance(approvals, list) else []
    manifest_approval = active[0].get("artifact_sha256") if len(active) == 1 else None
    if manifest_approval != projection.active_plan_sha256:
        mismatches["active_plan_approval"] = {
            "event_projection": projection.active_plan_sha256,
            "manifest": manifest_approval,
        }
    if projection.changed_files is not None and list(projection.changed_files) != manifest.get(
        "changed_files"
    ):
        mismatches["changed_files"] = {
            "event_projection": list(projection.changed_files),
            "manifest": manifest.get("changed_files"),
        }
    if (
        projection.review_subject_sha256 is not None
        and manifest.get("review_subject_sha256") != projection.review_subject_sha256
    ):
        mismatches["review_subject_sha256"] = {
            "event_projection": projection.review_subject_sha256,
            "manifest": manifest.get("review_subject_sha256"),
        }
    if mismatches:
        raise ValidationError(
            "Run manifest diverges from its event log.",
            hint="Recover run.json from the append-only events before continuing.",
            details={"mismatches": mismatches},
        )
    return projection
