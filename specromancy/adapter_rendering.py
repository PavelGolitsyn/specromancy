"""Deterministic harness rendering and expected manifest construction."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .adapter_contracts import (
    ADAPTER_COMMANDS, ADAPTER_SCHEMA_VERSION, GENERATOR_VERSION, HARNESS_MODES,
    MANIFEST_PATH, REGENERATION_COMMAND, AdapterCommand, AdapterError, _target_for_path,
)
from .hashing import sha256_bytes, sha256_json

if TYPE_CHECKING:
    from .adapter_sources import AdapterSources


def render_sources(sources: AdapterSources) -> dict[str, bytes]:
    """Render captured sources without reading the filesystem or registry."""

    files: dict[str, bytes] = {}
    files[".claude/CLAUDE.md"] = _markdown_document(
        "AGENTS.md",
        sources.agents,
        preface="The following repository instructions mirror the canonical AGENTS.md.\n\n",
    )
    for skill_path, skill_text in sources.skills:
        name = Path(skill_path).parent.name
        files[f".claude/skills/{name}/SKILL.md"] = _skill_mirror(
            skill_path, skill_text
        )
    for pipeline in sources.pipelines:
        name = f"specromancy-{pipeline.id}"
        skill = _pipeline_skill(pipeline.id)
        files[f".agents/skills/{name}/SKILL.md"] = skill
        files[f".claude/skills/{name}/SKILL.md"] = skill
    for command in ADAPTER_COMMANDS:
        files[f".claude/commands/specromancy/{command.name}.md"] = (
            _command_wrapper("claude", command)
        )

    files[".github/copilot-instructions.md"] = _markdown_document(
        "AGENTS.md",
        sources.agents,
        preface=(
            "These repository-work rules mirror the canonical instructions used by "
            "Specromancy.\n\n"
        ),
    )
    for command in ADAPTER_COMMANDS:
        files[f".github/prompts/specromancy-{command.name}.prompt.md"] = (
            _command_wrapper("copilot", command)
        )
        files[f".opencode/commands/specromancy-{command.name}.md"] = (
            _command_wrapper("opencode", command)
        )

    # Sorting here is part of the public reproducibility guarantee.
    return {path: files[path] for path in sorted(files)}


def _pipeline_skill(pipeline_id: str) -> bytes:
    source = "workflow/pipelines.toml and .agents/skills/pipeline/SKILL.md"
    lines = [
        "---",
        *_yaml_provenance(source),
        f"name: specromancy-{pipeline_id}",
        f"description: Coordinate the {pipeline_id} pipeline when the user requests this workflow.",
        "license: MIT",
        "compatibility: Specromancy pipeline schema version 1.",
        "metadata:",
        "  role: orchestrator",
        "---",
        "",
        f"# {pipeline_id}",
        "",
        f"For a new request, run `bin/specromancy init DESCRIPTION --pipeline {pipeline_id} --json`.",
        "Retain the emitted RUN_ID. For an existing invocation, obtain RUN_ID from the user.",
        "Then load `.agents/skills/pipeline/SKILL.md` and follow its existing-run procedure",
        "using that RUN_ID and the CLI's persisted status and action packets.",
        "Never edit run.json or events.jsonl.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _command_wrapper(harness: str, command: AdapterCommand) -> bytes:
    source = "CLI help metadata and canonical .agents skills"
    invocation = _harness_invocation(harness, command)
    if command.name == "init":
        follow = (
            "Use the returned run ID and recorded next command. If the response contains "
            "an action packet, load its `skill.absolute_path` and follow that canonical "
            "procedure exactly."
        )
    elif command.name == "status":
        follow = (
            "Report the persisted status and recorded next command. Do not infer run state "
            "from conversation history."
        )
    else:
        follow = (
            "If the response contains an action packet, load its `skill.absolute_path` and "
            "follow that canonical procedure exactly. Stop at any recorded pause, approval, "
            "block, validation failure, or terminal result."
        )

    frontmatter = [
        "---",
        *_yaml_provenance(source),
        f"description: {command.description}",
    ]
    if harness == "copilot":
        frontmatter.append(f"argument-hint: {command.arguments}")
        frontmatter.append("agent: agent")
    elif harness == "claude":
        frontmatter.append(f"argument-hint: {command.arguments}")
    frontmatter.extend(["---", ""])
    text = "\n".join(frontmatter)
    if harness == "copilot":
        text += (
            f"Using the values supplied after this prompt's slash command, replace the "
            f"placeholders in `{invocation}` and run it. {follow}\n"
        )
    else:
        text += f"Run `{invocation}`. {follow}\n"
    return text.encode("utf-8")


def _harness_invocation(harness: str, command: AdapterCommand) -> str:
    if harness == "claude":
        arguments = {
            "init": '"$1" --pipeline "$0"',
            "resume": '"$0"',
            "status": '"$0"',
            "phase": '"$0" "$1"',
        }[command.name]
    elif harness == "opencode":
        arguments = {
            "init": '"$2" --pipeline "$1"',
            "resume": '"$1"',
            "status": '"$1"',
            "phase": '"$1" "$2"',
        }[command.name]
    else:
        arguments = "DESCRIPTION --pipeline PIPELINE_ID" if command.name == "init" else command.arguments
    return f"bin/specromancy {command.cli_command} {arguments} --json"


def _skill_mirror(source: str, text: str) -> bytes:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise AdapterError(
            "canonical skill has no portable frontmatter",
            {"path": source},
        )
    mirrored = [lines[0], *_yaml_provenance(source), *lines[1:]]
    return ("\n".join(mirrored) + "\n").encode("utf-8")


def _markdown_document(source: str, body: str, *, preface: str = "") -> bytes:
    header = (
        "<!-- Generated by Specromancy adapter generator v1.\n"
        f"Canonical source: {source}.\n"
        f"Regenerate: {REGENERATION_COMMAND}\n"
        "Do not edit this file directly. -->\n\n"
    )
    return (header + preface + body).encode("utf-8")


def _yaml_provenance(source: str) -> list[str]:
    return [
        "# Generated by Specromancy adapter generator v1.",
        f"# Canonical source: {source}.",
        f"# Regenerate: {REGENERATION_COMMAND}",
        "# Do not edit this file directly.",
    ]


def expected_manifest(
    bundle: AdapterSources,
    rendered: Mapping[str, bytes],
) -> dict[str, Any]:
    sources = [source.record() for source in bundle.inputs]
    generated = []
    for path, content in rendered.items():
        generated.append(
            {
                "path": path,
                "sha256": sha256_bytes(content),
                "target": _target_for_path(path),
            }
        )
    targets = []
    for name in sorted(HARNESS_MODES):
        paths = [item["path"] for item in generated if item["target"] == name]
        targets.append({"name": name, "mode": HARNESS_MODES[name], "paths": paths})
        if HARNESS_MODES[name] == "native":
            targets[-1]["discovery_paths"] = [path for path in rendered if path.startswith(".agents/")]
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "generator": {
            "name": "specromancy",
            "version": GENERATOR_VERSION,
            "command": REGENERATION_COMMAND,
        },
        "canonical_source": {
            "sha256": sha256_json(sources),
            "inputs": sources,
        },
        "manifest": {
            "path": MANIFEST_PATH,
            "self_hash_omitted": True,
        },
        "targets": targets,
        "generated": generated,
    }
