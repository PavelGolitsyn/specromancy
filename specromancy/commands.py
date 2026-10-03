"""Run trusted validation commands without a shell and capture bounded summaries."""

from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config import ValidationCommand


DEFAULT_SUMMARY_BYTES = 4096


def execute_validation_commands(
    commands: tuple[ValidationCommand, ...] | list[ValidationCommand],
    repository_root: Path,
    run_directory: Path,
    visit_number: int,
    *,
    summary_bytes: int = DEFAULT_SUMMARY_BYTES,
    fault_injector: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Execute commands sequentially, stopping at the first required failure."""

    results: list[dict[str, Any]] = []
    secret_values = _secret_environment_values()
    command_directory = run_directory / "commands"
    command_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for index, command in enumerate(commands, 1):
        stdout_path = command_directory / f"{visit_number:03}-{index:02}-stdout.txt"
        stderr_path = command_directory / f"{visit_number:03}-{index:02}-stderr.txt"
        started = time.monotonic()
        timed_out = False
        missing = False
        try:
            completed = subprocess.run(
                list(command.argv),
                cwd=repository_root,
                check=False,
                shell=False,
                capture_output=True,
                timeout=command.timeout_seconds,
                env=os.environ.copy(),
            )
            stdout = completed.stdout
            stderr = completed.stderr
            exit_code: int | None = completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = _as_bytes(exc.stdout)
            stderr = _as_bytes(exc.stderr)
            exit_code = None
        except OSError as exc:
            missing = isinstance(exc, FileNotFoundError)
            stdout = b""
            stderr = str(exc).encode("utf-8", "replace")
            exit_code = None
        duration = max(0.0, time.monotonic() - started)
        if fault_injector is not None:
            fault_injector("before-command-output-write")
        stdout_path.write_bytes(stdout)
        if fault_injector is not None:
            fault_injector("after-command-stdout-write")
        stderr_path.write_bytes(stderr)
        if fault_injector is not None:
            fault_injector("after-command-output-write")
        failed = timed_out or missing or exit_code != 0
        result = {
            "executable": command.argv[0],
            "arguments": list(command.argv[1:]),
            "required": command.required,
            "exit_code": exit_code,
            "duration_seconds": round(duration, 6),
            "timed_out": timed_out,
            "missing_executable": missing,
            "status": "failed" if failed else "passed",
            "stdout_path": stdout_path.relative_to(run_directory).as_posix(),
            "stderr_path": stderr_path.relative_to(run_directory).as_posix(),
            "stdout_summary": _summary(stdout, summary_bytes, secret_values),
            "stderr_summary": _summary(stderr, summary_bytes, secret_values),
        }
        results.append(result)
        if failed and command.required:
            break
    return results


def first_required_failure(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (
            result
            for result in results
            if result.get("required") and result.get("status") == "failed"
        ),
        None,
    )


def _summary(content: bytes, limit: int, secret_values: tuple[str, ...] = ()) -> str:
    if limit < 0:
        raise ValueError("summary byte limit must not be negative")
    text = content.decode("utf-8", "replace")
    for value in secret_values:
        text = text.replace(value, "[REDACTED]")
    redacted = text.encode("utf-8")
    prefix = redacted[:limit].decode("utf-8", "replace")
    if len(redacted) > limit:
        prefix += f"\n...[truncated {len(redacted) - limit} bytes]"
    return prefix


def _secret_environment_values() -> tuple[str, ...]:
    sensitive = re.compile(
        r"(?:SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL|PRIVATE|API[_-]?KEY|AUTH)",
        re.IGNORECASE,
    )
    return tuple(
        sorted(
            {
                value
                for name, value in os.environ.items()
                if value and sensitive.search(name)
            },
            key=len,
            reverse=True,
        )
    )


def _as_bytes(value: bytes | str | None) -> bytes:
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8", "replace")
