"""Read-only status projection for persisted runs."""

from __future__ import annotations

from typing import Any

from ._config.config_models import PipelineConfig
from ._runs.run_records import RunRecord, VisitRecord, current_visit, latest_approval


STATUS_SCHEMA_VERSION = 1


def build_status(
    manifest: RunRecord,
    pipeline: PipelineConfig | None,
    *,
    warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    current = _current_visit(manifest)
    completed = [
        {
            "visit_id": visit["ordinal"],
            "phase": visit["phase_id"],
            "outcome": visit["chosen_outcome"],
            "output": visit["output"],
        }
        for visit in manifest["visits"]
        if visit["status"] == "completed"
    ]
    pending_approval = latest_approval(manifest, "pending")
    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "pipeline": {
            **manifest["pipeline"],
            "current_sha256": pipeline.config_hash if pipeline is not None else None,
        },
        "status": manifest["status"],
        "current": (
            {
                "visit_id": current["ordinal"],
                "phase": current["phase_id"],
                "status": current["status"],
                "output": current["output"],
            }
            if current is not None
            else None
        ),
        "completed_visits": completed,
        "pending_approval": pending_approval,
        "block": manifest["block_reason"],
        "terminal_result": manifest["terminal_result"],
        "next_command": next_command(manifest),
        "warnings": list(warnings or []),
    }


def next_command(manifest: RunRecord) -> list[str] | None:
    run_id = manifest["run_id"]
    current = _current_visit(manifest)
    if manifest["status"] == "awaiting-agent" and current is not None:
        return ["specromancy", "phase", run_id, current["phase_id"]]
    if manifest["status"] == "active" and current is not None:
        return ["specromancy", "validate", run_id, current["phase_id"]]
    if manifest["status"] == "awaiting-approval" and current is not None:
        pending = latest_approval(
            manifest, "pending", visit_number=current["ordinal"]
        )
        if pending:
            return ["specromancy", "approve", run_id, current["phase_id"]]
        return ["specromancy", "request-approval", run_id]
    if manifest["status"] == "paused":
        return ["specromancy", "resume", run_id]
    if manifest["status"] == "blocked":
        return ["specromancy", "status", run_id]
    return None


def render_status(status: dict[str, Any]) -> str:
    current = status["current"]
    lines = [
        f"Run: {status['run_id']}",
        f"Pipeline: {status['pipeline']['id']} v{status['pipeline']['version']}",
        f"Status: {status['status']}",
    ]
    if current is not None:
        lines.append(
            f"Current: visit {current['visit_id']} / {current['phase']} / {current['status']}"
        )
    lines.append(f"Completed visits: {len(status['completed_visits'])}")
    if status["pending_approval"] is not None:
        lines.append(
            f"Approval: {status['pending_approval'].get('reason', 'pending')}"
        )
    if status["block"] is not None:
        lines.append(f"Block: {status['block']}")
    if status["next_command"] is not None:
        lines.append("Next: " + " ".join(status["next_command"]))
    for warning in status["warnings"]:
        lines.append(f"Warning: {warning['message']}")
    return "\n".join(lines)


def _current_visit(manifest: RunRecord) -> VisitRecord | None:
    return current_visit(manifest)
