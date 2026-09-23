"""Safe verification command execution and durable, redacted records."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .clock import Clock, SystemClock, utc_timestamp
from .errors import ExternalCommandError, InvalidInputError, SafetyError, ValidationError
from .io import atomic_write_json, atomic_write_text, read_text
from .paths import RepositoryPaths
from .redaction import bounded_utf8, contains_secret, redact_and_bound, redact_text


DEFAULT_OUTPUT_LIMIT = 64 * 1024
@dataclass(frozen=True)
class CommandRecord:
    command_id: str
    argv: tuple[str, ...]
    cwd: str
    started_at: str
    ended_at: str
    exit_code: int
    blocking: bool
    failure_reason: str | None
    stdout_path: str
    stderr_path: str
    stdout_truncated: bool
    stderr_truncated: bool
    record_path: str


def redact_output(value: str) -> str:
    """Compatibility alias for the centralized redactor."""

    return redact_text(value)


def _bounded(value: str, limit: int) -> tuple[str, bool]:
    """Compatibility alias for deterministic byte bounding."""

    return bounded_utf8(value, limit)


def command_records_dir(paths: RepositoryPaths, run_id: str) -> Path:
    return paths.run_artifact(run_id, "commands")


def load_command_records(
    repository_root: str | Path, run_id: str
) -> tuple[Mapping[str, Any], ...]:
    paths = RepositoryPaths(Path(repository_root))
    directory = command_records_dir(paths, run_id)
    if not directory.exists():
        return ()
    records: list[Mapping[str, Any]] = []
    for target in sorted(directory.glob("CMD-*.json")):
        try:
            value = json.loads(read_text(target))
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "A verification command record is malformed.",
                hint="Remove the incomplete record and rerun the verification command.",
                path=paths.serialize(target),
            ) from exc
        if not isinstance(value, dict):
            raise ValidationError("A verification command record must be a JSON object.")
        required = {
            "schema_version", "command_id", "argv", "cwd", "started_at", "ended_at",
            "exit_code", "blocking", "failure_reason", "stdout_path", "stderr_path",
            "stdout_truncated", "stderr_truncated",
        }
        if set(value) != required or value.get("schema_version") != "1":
            raise ValidationError(
                "A verification command record has unexpected or missing fields.",
                hint="Rerun the command through the Specromancy verification helper.",
                path=paths.serialize(target),
            )
        command_id = value.get("command_id")
        if not isinstance(command_id, str) or target.name != f"{command_id}.json":
            raise ValidationError("A verification command record ID does not match its filename.")
        argv = value.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
            raise ValidationError("A verification command record has invalid argv.")
        if not isinstance(value.get("exit_code"), int) or not isinstance(value.get("blocking"), bool):
            raise ValidationError("A verification command record has invalid result fields.")
        try:
            paths.resolve_relative(str(value.get("cwd")), allow_root=True)
            output_targets = [
                paths.resolve_relative(str(value.get("stdout_path"))),
                paths.resolve_relative(str(value.get("stderr_path"))),
            ]
            for output_target in output_targets:
                output_target.relative_to(paths.run_dir(run_id))
                if not output_target.is_file():
                    raise ValidationError("A verification command output file is missing.")
        except (ValueError, SafetyError, ValidationError) as exc:
            raise ValidationError(
                "A verification command record contains an unsafe or missing managed path.",
                hint="Rerun the verification command to recreate its evidence.",
            ) from exc
        records.append(value)
    return tuple(records)


def _next_command_id(directory: Path) -> str:
    highest = 0
    for target in directory.glob("CMD-*.json") if directory.exists() else ():
        match = re.fullmatch(r"CMD-([0-9]{3,})\.json", target.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"CMD-{highest + 1:03d}"


def run_verification_command(
    repository_root: str | Path,
    run_id: str,
    argv: Sequence[str],
    *,
    cwd: str = ".",
    blocking: bool = True,
    failure_reason: str | None = None,
    output_limit: int = DEFAULT_OUTPUT_LIMIT,
    clock: Clock | None = None,
) -> CommandRecord:
    """Run one command without a shell and persist bounded stdout/stderr evidence."""

    if not argv or any(not isinstance(item, str) or not item or "\x00" in item for item in argv):
        raise InvalidInputError("Verification argv must contain nonempty, NUL-free strings.")
    if any(contains_secret(item) for item in argv):
        raise SafetyError(
            "Verification arguments contain a value that looks like a secret.",
            hint="Pass secrets through an approved external mechanism; command records retain exact argv.",
        )
    if output_limit < 256:
        raise InvalidInputError("Verification output limit must be at least 256 bytes.")
    paths = RepositoryPaths(Path(repository_root))
    working_directory = paths.root if cwd == "." else paths.resolve_relative(cwd)
    if not working_directory.is_dir():
        raise InvalidInputError("Verification working directory does not exist.", path=cwd)
    clock = clock or SystemClock()
    started = utc_timestamp(clock.now())
    try:
        completed = subprocess.run(
            list(argv),
            cwd=working_directory,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise ExternalCommandError(
            f"Verification command could not start: {argv[0]}.",
            hint="Install the command or correct the approved verification argv.",
        ) from exc
    ended = utc_timestamp(clock.now())
    directory = command_records_dir(paths, run_id)
    command_id = _next_command_id(directory)
    stdout, stdout_truncated = redact_and_bound(completed.stdout, output_limit)
    stderr, stderr_truncated = redact_and_bound(completed.stderr, output_limit)
    stdout_target = directory / f"{command_id}.stdout.txt"
    stderr_target = directory / f"{command_id}.stderr.txt"
    record_target = directory / f"{command_id}.json"
    atomic_write_text(stdout_target, stdout)
    atomic_write_text(stderr_target, stderr)
    normalized_reason = failure_reason.strip() if failure_reason else None
    record = {
        "schema_version": "1",
        "command_id": command_id,
        "argv": list(argv),
        "cwd": paths.serialize(working_directory),
        "started_at": started,
        "ended_at": ended,
        "exit_code": completed.returncode,
        "blocking": blocking,
        "failure_reason": normalized_reason,
        "stdout_path": paths.serialize(stdout_target),
        "stderr_path": paths.serialize(stderr_target),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
    }
    atomic_write_json(record_target, record)
    return CommandRecord(
        command_id=command_id,
        argv=tuple(argv),
        cwd=str(record["cwd"]),
        started_at=started,
        ended_at=ended,
        exit_code=completed.returncode,
        blocking=blocking,
        failure_reason=normalized_reason,
        stdout_path=str(record["stdout_path"]),
        stderr_path=str(record["stderr_path"]),
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        record_path=paths.serialize(record_target),
    )


execute_verification = run_verification_command
record_command = run_verification_command
execute_command = run_verification_command
run_command = run_verification_command
