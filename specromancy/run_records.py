"""Version-one dictionary vocabulary and side-effect-free record selectors.

TypedDicts describe stored fields, not runtime validation or constructors with
defaults. Open payloads stay open. Approval fields describe engine-produced
records, but are optional because persisted approvals accept arbitrary objects
(including extra keys). See run_validation for the actual acceptance boundary.

Selectors borrow records from their argument; they neither copy nor mutate.
RunStore remains responsible for defensive copies at its public boundaries.
"""

from __future__ import annotations

import re
from typing import Any, TypedDict

from .exit_codes import ExitCode
from .run_errors import RunStoreError


RUN_SCHEMA_VERSION = 1
EVENT_SCHEMA_VERSION = 1
EVENT_TYPE_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RUN_STATUSES = frozenset(
    {"active", "awaiting-agent", "awaiting-approval", "paused", "completed", "failed", "blocked"}
)
VISIT_STATUSES = frozenset(
    {"pending", "active", "awaiting-approval", "completed", "failed", "blocked"}
)


class ArtifactRecord(TypedDict):
    path: str
    sha256: str | None


class SealedArtifactRecord(TypedDict):
    path: str
    sha256: str


class InputArtifactRecord(SealedArtifactRecord):
    reference: str


class PipelineRecord(SealedArtifactRecord):
    id: str
    version: int


class GitRecord(TypedDict):
    base: Any
    head: Any


class ApprovalRecord(TypedDict, total=False):
    run_id: str
    phase_id: str
    visit_number: int
    reason: str
    details: str | None
    artifact_sha256: str
    pipeline_sha256: str
    outcome: str
    status: str
    decision: str | None
    actor: str | None
    requested_at: str
    decided_at: str | None


class VisitRecord(TypedDict):
    phase_id: str
    ordinal: int
    attempt: int
    status: str
    inputs: list[InputArtifactRecord]
    output: ArtifactRecord
    mutation_policy: str
    mutation_baseline: Any
    mutation_result: Any
    validation_checks: list[Any]
    command_results: list[Any]
    chosen_outcome: str | None
    transition_target: str | None
    skill: SealedArtifactRecord
    template: SealedArtifactRecord | None
    started_at: str | None
    completed_at: str | None
    deviations: list[Any]


class RunRecord(TypedDict):
    schema_version: int
    revision: int
    run_id: str
    pipeline: PipelineRecord
    status: str
    current_visit: int | None
    request: SealedArtifactRecord
    git: GitRecord
    created_at: str
    updated_at: str
    visits: list[VisitRecord]
    approvals: list[ApprovalRecord]
    terminal_result: Any
    block_reason: Any


class EventRecord(TypedDict):
    schema_version: int
    sequence: int
    timestamp: str
    run_id: str
    visit_number: int | None
    type: str
    payload: dict[str, Any]
    manifest_revision: int
    manifest_hash: str


def current_visit(manifest: RunRecord) -> VisitRecord | None:
    """Find the current ordinal, including completed visits; tolerate no match."""

    ordinal = manifest["current_visit"]
    if ordinal is None:
        return None
    return next(
        (visit for visit in manifest["visits"] if visit["ordinal"] == ordinal),
        None,
    )


def latest_approval(
    manifest: RunRecord, status: str, *, visit_number: int | None = None
) -> ApprovalRecord | None:
    """Find the last matching approval; omitted visit means any visit."""

    return next(
        (
            approval
            for approval in reversed(manifest["approvals"])
            if (visit_number is None or approval.get("visit_number") == visit_number)
            and approval.get("status") == status
        ),
        None,
    )


def visit_by_number(manifest: RunRecord, visit_number: int) -> VisitRecord:
    for visit in manifest["visits"]:
        if visit["ordinal"] == visit_number:
            return visit
    raise RunStoreError(
        f"visit not found: {visit_number}",
        diagnostic_code="visit-not-found",
        details={"visit_number": visit_number},
        code=ExitCode.NOT_FOUND,
    )
