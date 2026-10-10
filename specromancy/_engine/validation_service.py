"""Collect ordered validation evidence without committing run state.

Command logs remain the responsibility of commands.py. Expected failures are
returned with their evidence so orchestration can persist one attempt before
raising; unexpected failures (including injected interruptions) propagate.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..commands import execute_validation_commands, first_required_failure
from .._config.config_models import PhaseConfig, PipelineConfig
from .engine_errors import EngineError
from ..exit_codes import ExitCode
from ..git import GitError, capture_repository_snapshot, enforce_mutation_policy
from .._runs.run_records import VisitRecord
from ..validation import ValidationFailure, validate_artifact


@dataclass(frozen=True)
class ValidationResult:
    checks: list[dict[str, Any]]
    command_results: list[dict[str, Any]]
    mutation_result: dict[str, Any] | None
    failure: EngineError | None = None
    cause: Exception | None = None


def perform_validation(
    pipeline: PipelineConfig,
    run_directory: Path,
    visit: VisitRecord,
    phase: PhaseConfig,
    *,
    command_fault_injector: Callable[[str], None] | None = None,
) -> ValidationResult:
    """Validate the artifact, execute commands, then enforce mutation policy.

    Mutation failure takes precedence over a required command failure, including
    mutations made by that failing command.
    """

    try:
        check = validate_artifact(
            run_directory,
            visit["output"]["path"],
            phase.validator,
            template_path=phase.output_template_path,
        )
    except ValidationFailure as exc:
        failed = {
            "type": phase.validator.type,
            "status": "failed",
            "error_code": exc.diagnostic_code,
            **exc.details,
        }
        return ValidationResult(
            [failed], [], None,
            EngineError(
                ExitCode.VALIDATION_FAILED, exc.message, exc.diagnostic_code,
                **exc.details,
            ),
            exc,
        )

    checks = [check]
    command_results = execute_validation_commands(
        phase.validation_commands,
        pipeline.repository_root,
        run_directory,
        visit["ordinal"],
        fault_injector=command_fault_injector,
    )
    command_failure = first_required_failure(command_results)
    try:
        baseline = visit.get("mutation_baseline")
        if not isinstance(baseline, dict):
            raise GitError(
                "missing-mutation-baseline",
                "the visit has no repository mutation baseline",
            )
        current = capture_repository_snapshot(
            pipeline.repository_root,
            allow_non_git=pipeline.allow_non_git,
        )
        mutation_result = enforce_mutation_policy(
            baseline, current, phase.mutation, phase.allowlist
        )
    except GitError as exc:
        return ValidationResult(
            checks, command_results, exc.details.get("mutation_result"),
            EngineError(
                ExitCode.VALIDATION_FAILED, exc.message, exc.diagnostic_code,
                **exc.details,
            ),
            exc,
        )
    if command_failure is not None:
        return ValidationResult(
            checks, command_results, mutation_result,
            EngineError(
                ExitCode.VALIDATION_FAILED,
                "a required validation command failed",
                "validation-command-failed",
                command=command_failure,
            ),
        )
    return ValidationResult(checks, command_results, mutation_result)
