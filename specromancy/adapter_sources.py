"""Per-invocation capture of validated adapter sources and their hash inputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .adapter_contracts import ADAPTER_COMMANDS, AdapterError
from .cli_commands import adapter_command_metadata
from .hashing import canonical_json_bytes, relative_path, sha256_bytes

if TYPE_CHECKING:
    from .config_models import PipelineConfig
    from .registry import PipelineRegistry


@dataclass(frozen=True, slots=True)
class SourceInput:
    kind: str
    path: str
    content: bytes

    def record(self) -> dict[str, str]:
        return {"kind": self.kind, "path": self.path, "sha256": sha256_bytes(self.content)}


@dataclass(frozen=True, slots=True)
class AdapterSources:
    pipelines: tuple[PipelineConfig, ...]
    agents: str
    skills: tuple[tuple[str, str], ...]
    inputs: tuple[SourceInput, ...]


def capture_sources(
    root: Path,
    registry: PipelineRegistry,
    command_metadata: Mapping[str, Any] | None,
    *,
    include_manifest_inputs: bool = True,
) -> AdapterSources:
    """Read sources once for rendering and hashing; retain no cross-call cache."""

    if root != registry.repository_root:
        raise AdapterError("registry and adapter roots differ", {"path": str(registry.path)})
    pipelines = registry.load_all()
    agents = _normalized_text(root / "AGENTS.md", "AGENTS.md")
    skill_sources = _skill_sources(root)
    if ".agents/skills/pipeline/SKILL.md" not in {path for path, _ in skill_sources}:
        raise AdapterError(
            "canonical pipeline orchestrator skill is missing",
            {"path": ".agents/skills/pipeline/SKILL.md"},
        )
    if command_metadata is None:
        phases = sorted({phase for pipeline in pipelines for phase in pipeline.phase_ids})
        command_metadata = adapter_command_metadata(phases)
    cli_commands = _known_cli_commands(command_metadata)
    for command in ADAPTER_COMMANDS:
        if command.cli_command not in cli_commands:
            raise AdapterError(
                "adapter command is absent from CLI metadata",
                {"command": command.cli_command},
            )

    # Validate portable frontmatter before collecting manifest dependencies, as
    # rendering did before source capture was extracted.
    for path, text in skill_sources:
        if not text.splitlines() or text.splitlines()[0] != "---":
            raise AdapterError("canonical skill has no portable frontmatter", {"path": path})

    # The public render-only facade historically did not read dependency bytes.
    if not include_manifest_inputs:
        return AdapterSources(pipelines, agents, tuple(skill_sources), ())

    inputs = [
        SourceInput("repository-instructions", "AGENTS.md", agents.encode("utf-8")),
        SourceInput("validated-registry", relative_path(registry.path, root),
                    registry.canonical_json.encode("utf-8")),
    ]
    dependencies: set[str] = set()
    for pipeline in pipelines:
        inputs.append(SourceInput(
            "validated-pipeline", relative_path(pipeline.path, root),
            pipeline.canonical_json.encode("utf-8"),
        ))
        for phase in pipeline.phases:
            for path in (phase.output_template_path, phase.validator.resolved_path):
                if path is not None:
                    dependencies.add(relative_path(path, root))
    for path in sorted(dependencies):
        inputs.append(SourceInput("pipeline-dependency", path, (root / path).read_bytes()))
    for path, text in skill_sources:
        inputs.append(SourceInput("canonical-skill", path, text.encode("utf-8")))
    inputs.append(SourceInput(
        "cli-help-metadata", "@cli-help-metadata", canonical_json_bytes(command_metadata),
    ))
    return AdapterSources(pipelines, agents, tuple(skill_sources), tuple(inputs))


def _skill_sources(root: Path) -> list[tuple[str, str]]:
    skills_root = root / ".agents" / "skills"
    paths = sorted(
        (path for path in skills_root.glob("*/SKILL.md")
         if not path.parent.name.startswith("specromancy-")),
        key=lambda item: item.as_posix(),
    )
    if not paths:
        raise AdapterError(
            "no canonical skills found",
            {"path": ".agents/skills/*/SKILL.md"},
        )
    return [
        (relative_path(path, root), _normalized_text(path, relative_path(path, root)))
        for path in paths
    ]


def _normalized_text(path: Path, label: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AdapterError(
            "cannot read canonical adapter source",
            {"path": label, "error": str(exc)},
        ) from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.rstrip("\n") + "\n"


def _known_cli_commands(metadata: Mapping[str, Any]) -> set[str]:
    commands = metadata.get("commands")
    if not isinstance(commands, Sequence) or isinstance(commands, (str, bytes)):
        raise AdapterError("invalid CLI help metadata", {"field": "commands"})
    known: set[str] = set()
    for item in commands:
        if isinstance(item, Mapping) and isinstance(item.get("name"), str):
            known.add(item["name"])
    return known
