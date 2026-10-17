"""Shared, pure command argument resolution and transition diagnostics."""

from __future__ import annotations

from typing import Any

from .._config.config_models import PhaseConfig
from .engine_errors import EngineError
from ..errors import UsageError
from ..exit_codes import ExitCode
from .._runs.run_records import RunRecord


def select_outcome(phase: PhaseConfig, requested: str | None) -> str:
    outcomes = [
        transition.outcome
        for transition in phase.transitions
        if transition.outcome != "blocked"
    ]
    if requested is not None:
        if requested not in outcomes:
            raise EngineError(
                ExitCode.ILLEGAL_TRANSITION,
                f"outcome {requested!r} is not declared by phase {phase.id!r}",
                "undeclared-outcome",
                phase=phase.id,
                requested=requested,
                declared=outcomes,
            )
        if len(outcomes) <= 1:
            raise EngineError(
                ExitCode.ILLEGAL_TRANSITION,
                "--outcome is valid only when the phase has multiple successful outcomes",
                "unnecessary-outcome",
                phase=phase.id,
                declared=outcomes,
            )
        return requested
    if len(outcomes) != 1:
        raise EngineError(
            ExitCode.ILLEGAL_TRANSITION,
            f"phase {phase.id!r} requires one of {outcomes!r}",
            "outcome-required",
            phase=phase.id,
            declared=outcomes,
        )
    return outcomes[0]


def declared_reason(
    requested: str | None, declared: tuple[str, ...], kind: str
) -> str:
    if requested is None:
        if len(declared) == 1:
            return declared[0]
        raise UsageError(
            f"--reason is required; declared {kind} reasons: {', '.join(declared) or 'none'}",
            {"declared": list(declared)},
        )
    if requested not in declared:
        raise EngineError(
            ExitCode.ILLEGAL_TRANSITION,
            f"{kind} reason {requested!r} is not declared",
            f"undeclared-{kind}-reason",
            requested=requested,
            declared=list(declared),
        )
    return requested


def illegal_transition(
    message: str, manifest: RunRecord, **details: Any
) -> EngineError:
    return EngineError(
        ExitCode.ILLEGAL_TRANSITION,
        message,
        "illegal-transition",
        status=manifest["status"],
        **details,
    )

