"""Repository-owned registrations for independently configured pipelines."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from ._config.config_errors import PipelineConfigError
from ._config.config_loader import IDENTIFIER_PATTERN, load_pipeline
from ._config.config_models import PipelineConfig


REGISTRY_PATH = "workflow/pipelines.toml"
PIPELINE_PATH_PATTERN = re.compile(r"^pipelines/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.toml$")


@dataclass(frozen=True, slots=True)
class PipelineRegistration:
    id: str
    path: Path


@dataclass(frozen=True, slots=True)
class PipelineRegistry:
    path: Path
    repository_root: Path
    pipelines: tuple[PipelineRegistration, ...]

    @property
    def canonical_json(self) -> str:
        return json.dumps(
            {
                "schema_version": 1,
                "pipelines": [
                    {"id": item.id, "path": item.path.relative_to(self.path.parent).as_posix()}
                    for item in self.pipelines
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def load(self, pipeline_id: str) -> PipelineConfig:
        for registration in self.pipelines:
            if registration.id == pipeline_id:
                pipeline = load_pipeline(registration.path, self.repository_root)
                if pipeline.id != registration.id:
                    raise PipelineConfigError(
                        "pipeline-id-mismatch",
                        "registered ID differs from pipeline ID",
                        path=self.path,
                        field="pipelines.id",
                        value=pipeline_id,
                        remediation="make the registration and pipeline IDs agree",
                    )
                return pipeline
        raise PipelineConfigError(
            "unknown-pipeline",
            f"pipeline {pipeline_id!r} is not registered",
            path=self.path,
            field="pipelines.id",
            value=pipeline_id,
            remediation="choose a registered ID: " + ", ".join(item.id for item in self.pipelines),
        )

    def load_all(self) -> tuple[PipelineConfig, ...]:
        return tuple(self.load(item.id) for item in self.pipelines)


def load_registry(repository_root: str | Path) -> PipelineRegistry:
    """Validate the mandatory registry without loading unrelated phase graphs."""

    root = Path(repository_root).expanduser().resolve()
    path = root / REGISTRY_PATH

    def fail(code: str, message: str, field: str, value: object = None) -> NoReturn:
        raise PipelineConfigError(
            code,
            message,
            path=path,
            field=field,
            value=value,
            remediation="use schema_version = 1 and unique [[pipelines]] id/path entries under workflow/pipelines/",
        )

    try:
        if not path.resolve().is_relative_to(root):
            fail("unsafe-registry-path", "registry resolves outside the repository", "registry")
        with path.open("rb") as stream:
            raw = tomllib.load(stream)
    except (OSError, ValueError, RuntimeError) as exc:
        fail("invalid-registry", f"cannot load mandatory registry: {exc}", "registry")
    if set(raw) != {"schema_version", "pipelines"}:
        fail("invalid-registry-fields", "registry requires only schema_version and pipelines", "registry")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        fail("unsupported-schema-version", "registry schema_version must be 1", "schema_version", raw["schema_version"])
    entries = raw["pipelines"]
    if not isinstance(entries, list) or not entries:
        fail("empty-registry", "pipelines must be a nonempty array of tables", "pipelines")
    registrations: list[PipelineRegistration] = []
    ids: set[str] = set()
    paths: set[Path] = set()
    directory = root / "workflow" / "pipelines"
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"id", "path"}:
            fail("invalid-registration", "registration requires only id and path", "pipelines", entry)
        pipeline_id = entry["id"]
        if not isinstance(pipeline_id, str) or not IDENTIFIER_PATTERN.fullmatch(pipeline_id):
            fail("invalid-identifier", "pipeline ID must be lowercase kebab-case", "pipelines.id", pipeline_id)
        if pipeline_id in ids:
            fail("duplicate-pipeline-id", "pipeline IDs must be unique", "pipelines.id", pipeline_id)
        declared = entry["path"]
        if not isinstance(declared, str):
            fail("unsafe-pipeline-path", "pipeline path must be a relative TOML path", "pipelines.path", declared)
        if not PIPELINE_PATH_PATTERN.fullmatch(declared):
            fail("unsafe-pipeline-path", "pipeline path must be under pipelines/", "pipelines.path", declared)
        try:
            resolved = (path.parent / declared).resolve()
        except (OSError, ValueError, RuntimeError) as exc:
            fail("unsafe-pipeline-path", f"pipeline path cannot be resolved: {exc}", "pipelines.path", declared)
        if not resolved.is_relative_to(directory) or not resolved.is_relative_to(root):
            fail("unsafe-pipeline-path", "pipeline path escapes workflow/pipelines/", "pipelines.path", declared)
        if not resolved.is_file():
            fail("missing-pipeline", "registered pipeline file does not exist", "pipelines.path", declared)
        if resolved in paths:
            fail("duplicate-pipeline-path", "pipeline paths must be unique", "pipelines.path", declared)
        ids.add(pipeline_id)
        paths.add(resolved)
        registrations.append(PipelineRegistration(pipeline_id, resolved))
    return PipelineRegistry(path, root, tuple(sorted(registrations, key=lambda item: item.id)))
