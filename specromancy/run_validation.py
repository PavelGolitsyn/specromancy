"""Pure checks for persisted dictionaries, preserving version-one acceptance.

Annotations are not validators. These checks intentionally retain the legacy
weak nested-field checks; see docs/refactoring/03-persisted-records.md. Event
sequence/revision continuity and manifest hashes remain store responsibilities.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .hashing import SHA256_PATTERN, normalize_relative_path
from .run_errors import RunCorruptionError
from .run_identity import is_valid_run_id
from .run_records import (
    EVENT_SCHEMA_VERSION, EVENT_TYPE_PATTERN, RUN_SCHEMA_VERSION,
    RUN_STATUSES, VISIT_STATUSES,
)


def validate_manifest(value: dict[str, Any], run_id: str) -> None:
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
        invalid_manifest(run_id, "manifest fields do not match the schema")
    if value["schema_version"] != RUN_SCHEMA_VERSION:
        invalid_manifest(run_id, "unsupported run schema version")
    if not isinstance(value["revision"], int) or value["revision"] < 1:
        invalid_manifest(run_id, "manifest revision must be positive")
    if value["run_id"] != run_id or not is_valid_run_id(value["run_id"]):
        invalid_manifest(run_id, "manifest run ID is invalid")
    if not isinstance(value["status"], str) or value["status"] not in RUN_STATUSES:
        invalid_manifest(run_id, "manifest status is invalid")
    validate_timestamp(value["created_at"], run_id)
    validate_timestamp(value["updated_at"], run_id)
    pipeline = value["pipeline"]
    if not isinstance(pipeline, dict) or set(pipeline) != {
        "id",
        "version",
        "path",
        "sha256",
    }:
        invalid_manifest(run_id, "pipeline record is invalid")
    if (
        not isinstance(pipeline["id"], str)
        or not isinstance(pipeline["version"], int)
        or pipeline["version"] < 1
        or not isinstance(pipeline["sha256"], str)
        or not SHA256_PATTERN.fullmatch(pipeline["sha256"])
    ):
        invalid_manifest(run_id, "pipeline provenance is invalid")
    validate_path(pipeline["path"], run_id)
    validate_artifact_record(value["request"], run_id, hash_required=True)
    if not isinstance(value["git"], dict) or set(value["git"]) != {"base", "head"}:
        invalid_manifest(run_id, "git metadata is invalid")
    if not isinstance(value["visits"], list):
        invalid_manifest(run_id, "visits must be a list")
    attempts: dict[str, int] = {}
    for expected_ordinal, visit in enumerate(value["visits"], 1):
        if not isinstance(visit, dict):
            invalid_manifest(run_id, "visit record must be an object")
        validate_visit(visit, run_id, expected_ordinal)
        phase_id = visit["phase_id"]
        attempts[phase_id] = attempts.get(phase_id, 0) + 1
        if visit["attempt"] != attempts[phase_id]:
            invalid_manifest(run_id, "visit attempt is not ordered")
    current = value["current_visit"]
    if current is not None and (
        not isinstance(current, int) or current < 1 or current > len(value["visits"])
    ):
        invalid_manifest(run_id, "current visit is invalid")
    if not isinstance(value["approvals"], list) or not all(
        isinstance(item, dict) for item in value["approvals"]
    ):
        invalid_manifest(run_id, "approvals must be an ordered object list")
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        invalid_manifest(run_id, f"manifest is not JSON serializable: {exc}")

def validate_visit(
    visit: dict[str, Any], run_id: str, expected_ordinal: int
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
        invalid_manifest(run_id, "visit fields do not match the schema")
    if (
        not isinstance(visit["phase_id"], str)
        or visit["ordinal"] != expected_ordinal
        or not isinstance(visit["attempt"], int)
        or visit["attempt"] < 1
        or not isinstance(visit["status"], str)
        or visit["status"] not in VISIT_STATUSES
    ):
        invalid_manifest(run_id, "visit identity or status is invalid")
    if not isinstance(visit["inputs"], list):
        invalid_manifest(run_id, "visit inputs must be a list")
    for record in visit["inputs"]:
        validate_artifact_record(record, run_id, hash_required=True, reference=True)
    validate_artifact_record(
        visit["output"], run_id, hash_required=visit["status"] == "completed"
    )
    if visit["status"] != "completed" and visit["output"]["sha256"] is not None:
        invalid_manifest(run_id, "mutable visit output cannot have a sealed hash")
    for name in ("validation_checks", "command_results", "deviations"):
        if not isinstance(visit[name], list):
            invalid_manifest(run_id, f"visit {name} must be a list")
    if not isinstance(visit["skill"], dict):
        invalid_manifest(run_id, "visit skill provenance is invalid")
    validate_provenance(visit["skill"], run_id)
    if visit["template"] is not None:
        if not isinstance(visit["template"], dict):
            invalid_manifest(run_id, "visit template provenance is invalid")
        validate_provenance(visit["template"], run_id)
    if visit["started_at"] is not None:
        validate_timestamp(visit["started_at"], run_id)
    if visit["status"] != "pending" and visit["started_at"] is None:
        invalid_manifest(run_id, "started visit lacks a start timestamp")
    if visit["completed_at"] is not None:
        validate_timestamp(visit["completed_at"], run_id)
    if visit["status"] == "completed" and visit["completed_at"] is None:
        invalid_manifest(run_id, "completed visit lacks a completion timestamp")

def validate_artifact_record(
    value: Any,
    run_id: str,
    *,
    hash_required: bool,
    reference: bool = False,
) -> None:
    fields = {"path", "sha256", "reference"} if reference else {"path", "sha256"}
    if not isinstance(value, dict) or set(value) != fields:
        invalid_manifest(run_id, "artifact record is invalid")
    validate_path(value["path"], run_id)
    digest = value["sha256"]
    if hash_required and (
        not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest)
    ):
        invalid_manifest(run_id, "artifact hash is invalid")
    if not hash_required and digest is not None:
        invalid_manifest(run_id, "artifact hash must be null until sealed")
    if reference and not isinstance(value["reference"], str):
        invalid_manifest(run_id, "artifact reference is invalid")

def validate_provenance(value: dict[str, Any], run_id: str) -> None:
    if set(value) != {"path", "sha256"}:
        invalid_manifest(run_id, "provenance record is invalid")
    validate_path(value["path"], run_id)
    if not isinstance(value["sha256"], str) or not SHA256_PATTERN.fullmatch(
        value["sha256"]
    ):
        invalid_manifest(run_id, "provenance hash is invalid")

def validate_event(event: dict[str, Any], run_id: str) -> None:
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
    validate_timestamp(event["timestamp"], run_id)

def validate_timestamp(value: Any, run_id: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise RunCorruptionError("timestamp is invalid", run_id=run_id)
    try:
        datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise RunCorruptionError("timestamp is invalid", run_id=run_id) from exc

def validate_path(value: Any, run_id: str) -> None:
    if not isinstance(value, str):
        raise RunCorruptionError("persisted path is invalid", run_id=run_id)
    try:
        normalize_relative_path(value)
    except ValueError as exc:
        raise RunCorruptionError("persisted path is unsafe", run_id=run_id) from exc

def invalid_manifest(run_id: str, message: str) -> None:
    raise RunCorruptionError(message, run_id=run_id)
