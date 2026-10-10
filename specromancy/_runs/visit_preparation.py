"""Read visit resources without locks, state mutation, or durable writes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..artifacts import ArtifactError, render_output_path, resolve_input_reference
from .._config.config_models import PhaseConfig, PipelineConfig
from ..hashing import relative_path, sha256_file
from .run_records import InputArtifactRecord, RunRecord, SealedArtifactRecord


@dataclass(frozen=True)
class VisitResources:
    """Detached evidence captured from borrowed state at preparation time."""

    inputs: list[InputArtifactRecord]
    output_path: str
    skill: SealedArtifactRecord
    template: SealedArtifactRecord | None


def collect_resources(
    directory: Path,
    manifest: RunRecord,
    pipeline: PipelineConfig,
    phase: PhaseConfig,
    *,
    repository_root: Path,
    ordinal: int,
) -> VisitResources:
    """Resolve inputs, reject output collisions, then capture skill/template hashes.

    The store supplies the current or sealed proposed manifest under its lock.
    This helper neither changes that manifest nor coordinates external writers.
    """

    inputs = [
        resolve_input_reference(reference, manifest, directory)
        for reference in phase.inputs
    ]
    output_path = render_output_path(pipeline, phase, ordinal)
    reserved_paths = {visit["output"]["path"] for visit in manifest["visits"]}
    if output_path in reserved_paths or (directory / output_path).exists():
        raise ArtifactError(
            f"visit output path would overwrite an earlier artifact: {output_path}",
            diagnostic_code="artifact-path-collision",
            details={"path": output_path, "visit_number": ordinal},
        )
    skill = {
        "path": relative_path(phase.skill_path, repository_root),
        "sha256": sha256_file(phase.skill_path),
    }
    template = None
    if phase.output_template_path is not None:
        template = {
            "path": relative_path(phase.output_template_path, repository_root),
            "sha256": sha256_file(phase.output_template_path),
        }
    return VisitResources(inputs, output_path, skill, template)
