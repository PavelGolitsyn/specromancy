"""Immutable run-artifact addressing and integrity verification."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from .config import PhaseConfig, PipelineConfig
from .errors import SpecromancyError
from .exit_codes import ExitCode
from .hashing import normalize_relative_path, resolve_relative_path, sha256_bytes, sha256_file


class ArtifactError(SpecromancyError):
    """An expected missing, unsafe, or inconsistent artifact failure."""

    def __init__(
        self,
        message: str,
        *,
        diagnostic_code: str,
        details: dict[str, Any] | None = None,
        not_found: bool = False,
    ) -> None:
        values = {"error_code": diagnostic_code}
        if details:
            values.update(details)
        super().__init__(
            ExitCode.NOT_FOUND if not_found else ExitCode.INTERNAL_ERROR,
            message,
            values,
        )
        self.diagnostic_code = diagnostic_code


def render_output_path(
    pipeline: PipelineConfig, phase: PhaseConfig, visit_number: int
) -> str:
    """Render a phase's globally addressed output path inside a run."""

    if visit_number < 1:
        raise ValueError("visit number must be positive")
    try:
        output_name = phase.output_name.format(
            visit=visit_number,
            phase=phase.id,
            output_name="output.md",
        )
        rendered = pipeline.artifact_pattern.format(
            visit=visit_number,
            phase=phase.id,
            output_name=output_name,
        )
        return normalize_relative_path(rendered)
    except (KeyError, IndexError, ValueError) as exc:
        raise ArtifactError(
            f"could not render output path for phase {phase.id!r}: {exc}",
            diagnostic_code="invalid-output-path",
            details={"phase": phase.id, "visit_number": visit_number},
        ) from exc


def artifact_record(
    run_directory: Path,
    path: str,
    *,
    reference: str | None = None,
) -> dict[str, Any]:
    """Create a literal path/hash record for an existing regular artifact."""

    resolved = _required_regular_artifact(run_directory, path)
    record: dict[str, Any] = {
        "path": normalize_relative_path(path),
        "sha256": sha256_file(resolved),
    }
    if reference is not None:
        record["reference"] = reference
    return record


def resolve_input_reference(
    reference: str,
    manifest: dict[str, Any],
    run_directory: Path,
) -> dict[str, Any]:
    """Resolve a symbolic input to a completed, immutable artifact record."""

    source: dict[str, Any] | None = None
    if reference == "request":
        value = manifest.get("request")
        if isinstance(value, dict):
            source = value
    elif reference.startswith("latest:"):
        phase_id = reference.removeprefix("latest:")
        if not phase_id:
            return _invalid_reference(reference)
        for visit in reversed(manifest.get("visits", [])):
            if (
                isinstance(visit, dict)
                and visit.get("phase_id") == phase_id
                and visit.get("status") == "completed"
            ):
                value = visit.get("output")
                if isinstance(value, dict):
                    source = value
                break
    elif reference.startswith("visit:"):
        raw_number = reference.removeprefix("visit:")
        if not raw_number.isascii() or not raw_number.isdigit() or int(raw_number) < 1:
            return _invalid_reference(reference)
        number = int(raw_number)
        for visit in manifest.get("visits", []):
            if (
                isinstance(visit, dict)
                and visit.get("ordinal") == number
                and visit.get("status") == "completed"
            ):
                value = visit.get("output")
                if isinstance(value, dict):
                    source = value
                break
    else:
        return _invalid_reference(reference)

    if source is None:
        raise ArtifactError(
            f"artifact reference is not available: {reference}",
            diagnostic_code="artifact-not-found",
            details={"reference": reference},
            not_found=True,
        )
    path = source.get("path")
    expected_hash = source.get("sha256")
    if not isinstance(path, str) or not isinstance(expected_hash, str):
        raise ArtifactError(
            f"artifact record for {reference!r} is incomplete",
            diagnostic_code="invalid-artifact-record",
            details={"reference": reference},
        )
    actual = artifact_record(run_directory, path, reference=reference)
    if actual["sha256"] != expected_hash:
        raise ArtifactError(
            f"artifact changed after it became immutable: {path}",
            diagnostic_code="artifact-hash-mismatch",
            details={
                "path": path,
                "expected": expected_hash,
                "actual": actual["sha256"],
            },
        )
    return actual


def verify_manifest_artifacts(
    manifest: dict[str, Any], run_directory: Path
) -> tuple[dict[str, Any], ...]:
    """Verify the request and every completed visit output from disk alone."""

    records: list[dict[str, Any]] = []
    request = manifest.get("request")
    if not isinstance(request, dict):
        raise ArtifactError(
            "run manifest has no request artifact record",
            diagnostic_code="invalid-artifact-record",
        )
    records.append(_verify_record(request, run_directory, "request"))
    for visit in manifest.get("visits", []):
        if not isinstance(visit, dict) or visit.get("status") != "completed":
            continue
        records.append(
            _verify_record(
                visit.get("output"),
                run_directory,
                f"visit:{visit.get('ordinal')}",
            )
        )
    return tuple(records)


def write_artifact_atomic(
    run_directory: Path,
    path: str,
    content: str | bytes,
    *,
    replace: bool = False,
) -> str:
    """Atomically write an artifact, refusing accidental replacement by default."""

    normalized = normalize_relative_path(path)
    try:
        target = resolve_relative_path(run_directory, normalized)
    except (OSError, ValueError) as exc:
        raise ArtifactError(
            f"artifact path escapes the run directory: {path!r}",
            diagnostic_code="unsafe-artifact-path",
            details={"path": path},
        ) from exc
    if target.exists() and not replace:
        raise ArtifactError(
            f"artifact already exists and will not be overwritten: {normalized}",
            diagnostic_code="artifact-already-exists",
            details={"path": normalized},
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    # Re-resolve after creating parents so a pre-existing symlink cannot redirect us.
    try:
        target = resolve_relative_path(run_directory, normalized)
    except (OSError, ValueError) as exc:
        raise ArtifactError(
            f"artifact path escapes the run directory: {path!r}",
            diagnostic_code="unsafe-artifact-path",
            details={"path": path},
        ) from exc
    payload = content.encode("utf-8") if isinstance(content, str) else content
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists() and not replace:
            raise ArtifactError(
                f"artifact already exists and will not be overwritten: {normalized}",
                diagnostic_code="artifact-already-exists",
                details={"path": normalized},
            )
        os.replace(temporary, target)
        _fsync_directory(target.parent)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256_bytes(payload)


def _invalid_reference(reference: str) -> dict[str, Any]:
    raise ArtifactError(
        f"invalid artifact reference: {reference!r}",
        diagnostic_code="invalid-artifact-reference",
        details={"reference": reference},
        not_found=True,
    )


def _required_regular_artifact(run_directory: Path, path: str) -> Path:
    try:
        normalized = normalize_relative_path(path)
        resolved = resolve_relative_path(run_directory, normalized, must_exist=True)
    except (OSError, ValueError) as exc:
        raise ArtifactError(
            f"artifact path is missing or unsafe: {path!r}",
            diagnostic_code="unsafe-artifact-path",
            details={"path": path},
            not_found=True,
        ) from exc
    literal = run_directory / normalized
    if literal.is_symlink() or not resolved.is_file():
        raise ArtifactError(
            f"artifact is not a regular file: {path!r}",
            diagnostic_code="invalid-artifact-type",
            details={"path": path},
        )
    return resolved


def _verify_record(value: Any, run_directory: Path, reference: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ArtifactError(
            f"artifact record for {reference!r} is invalid",
            diagnostic_code="invalid-artifact-record",
            details={"reference": reference},
        )
    path = value.get("path")
    expected = value.get("sha256")
    if not isinstance(path, str) or not isinstance(expected, str):
        raise ArtifactError(
            f"artifact record for {reference!r} is incomplete",
            diagnostic_code="invalid-artifact-record",
            details={"reference": reference},
        )
    actual = artifact_record(run_directory, path, reference=reference)
    if actual["sha256"] != expected:
        raise ArtifactError(
            f"artifact changed after it became immutable: {path}",
            diagnostic_code="artifact-hash-mismatch",
            details={"path": path, "expected": expected, "actual": actual["sha256"]},
        )
    return actual


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


resolve_artifact_reference = resolve_input_reference
verify_artifacts = verify_manifest_artifacts
