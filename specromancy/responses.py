"""Versioned command envelopes over the existing action and status payloads."""

from __future__ import annotations

from typing import Any

from .actions import build_action_packet
from .approvals import pending_approval
from .config_models import PipelineConfig
from .exit_codes import ExitCode
from .run_records import ApprovalRecord, RunRecord, VisitRecord, current_visit
from .status import build_status


RESPONSE_SCHEMA_VERSION = 1


def after_transition(
    pipeline: PipelineConfig, manifest: RunRecord, outcome: str
) -> dict[str, Any]:
    if manifest["status"] == "blocked":
        return blocked_response(
            pipeline,
            manifest, "run blocked because a configured loop limit was reached"
        )
    if manifest["status"] == "completed":
        return status_response(
            pipeline,
            manifest, f"run completed with outcome {outcome!r}"
        )
    if manifest["status"] == "paused":
        return paused_response(
            pipeline,
            manifest, f"outcome {outcome!r} recorded; run paused at checkpoint"
        )
    visit = current_visit(manifest)
    assert visit is not None
    return action_response(
        pipeline,
        manifest,
        visit,
        f"outcome {outcome!r} recorded; next phase requires agent action",
    )


def response_for_state(
    pipeline: PipelineConfig, manifest: RunRecord, message: str
) -> dict[str, Any]:
    visit = current_visit(manifest)
    if manifest["status"] in {"awaiting-agent", "active"} and visit is not None:
        return action_response(pipeline, manifest, visit, message)
    if manifest["status"] == "awaiting-approval":
        approval = pending_approval(
            manifest, visit["ordinal"] if visit is not None else -1
        )
        return approval_response(pipeline, manifest, approval, "approval is required")
    if manifest["status"] == "paused":
        return paused_response(pipeline, manifest, message)
    if manifest["status"] == "blocked":
        return blocked_response(pipeline, manifest, message)
    return status_response(pipeline, manifest, message)


def action_response(
    pipeline: PipelineConfig, manifest: RunRecord, visit: VisitRecord, message: str
) -> dict[str, Any]:
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "kind": "action",
        "code": int(ExitCode.AGENT_ACTION_REQUIRED),
        "message": message,
        "action": build_action_packet(pipeline, manifest, visit),
    }


def approval_response(
    pipeline: PipelineConfig,
    manifest: RunRecord,
    approval: ApprovalRecord | None,
    message: str,
) -> dict[str, Any]:
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "kind": "approval",
        "code": int(ExitCode.APPROVAL_REQUIRED),
        "message": message,
        "approval": approval,
        "status": build_status(manifest, pipeline),
    }


def blocked_response(
    pipeline: PipelineConfig, manifest: RunRecord, message: str
) -> dict[str, Any]:
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "kind": "status",
        "code": int(ExitCode.RUN_BLOCKED),
        "message": message,
        "status": build_status(manifest, pipeline),
    }


def paused_response(
    pipeline: PipelineConfig, manifest: RunRecord, message: str
) -> dict[str, Any]:
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "kind": "status",
        "code": int(ExitCode.RUN_PAUSED),
        "message": message,
        "status": build_status(manifest, pipeline),
    }


def status_response(
    pipeline: PipelineConfig,
    manifest: RunRecord,
    message: str,
    *,
    warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "kind": "status",
        "code": int(ExitCode.SUCCESS),
        "message": message,
        "status": build_status(manifest, pipeline, warnings=warnings),
    }
