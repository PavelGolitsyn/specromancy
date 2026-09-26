"""Deterministic, safely owned adapters for supported agent harnesses."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import PipelineConfig
from .errors import SpecromancyError
from .exit_codes import ExitCode
from .hashing import (
    SHA256_PATTERN,
    canonical_json_bytes,
    normalize_relative_path,
    relative_path,
    sha256_bytes,
    sha256_json,
)


ADAPTER_SCHEMA_VERSION = 1
GENERATOR_VERSION = 1
MANIFEST_PATH = "adapters/manifest.json"
REGENERATION_COMMAND = "bin/specromancy adapters generate"


@dataclass(frozen=True, slots=True)
class AdapterCommand:
    """A thin harness command that delegates to the stable CLI."""

    name: str
    cli_command: str
    arguments: str
    description: str


ADAPTER_COMMANDS = (
    AdapterCommand(
        "init",
        "init",
        "DESCRIPTION",
        "Initialize a Specromancy run and return its recorded next action.",
    ),
    AdapterCommand(
        "resume",
        "resume",
        "RUN_ID",
        "Resume a Specromancy run from persisted state.",
    ),
    AdapterCommand(
        "status",
        "status",
        "RUN_ID",
        "Read a Specromancy run's persisted status and next command.",
    ),
    AdapterCommand(
        "phase",
        "phase",
        "RUN_ID PHASE",
        "Start or resume the named current phase and return its action packet.",
    ),
)

HARNESS_MODES = {
    "claude": "generated",
    "codex": "native",
    "copilot": "generated",
    "hermes": "native",
    "opencode": "generated",
}


class AdapterError(SpecromancyError):
    """Report adapter drift or an ownership conflict without unsafe writes."""

    def __init__(self, message: str, details: Mapping[str, Any]) -> None:
        super().__init__(ExitCode.ADAPTER_DRIFT, message, details)


def generate_adapters(
    repository_root: Path,
    pipeline: PipelineConfig,
    command_metadata: Mapping[str, Any],
    *,
    check: bool = False,
) -> dict[str, Any]:
    """Generate adapters or compare the worktree to deterministic output."""

    root = repository_root.resolve(strict=True)
    rendered = render_adapters(root, pipeline, command_metadata)
    expected_manifest = _manifest(root, pipeline, command_metadata, rendered)
    manifest_bytes = canonical_json_bytes(expected_manifest) + b"\n"

    if check:
        drift = _compare(root, rendered, manifest_bytes)
        if _has_drift(drift):
            raise AdapterError("generated adapter drift detected", drift)
        return _result(
            "generated adapters are up to date",
            checked=True,
            paths=tuple(rendered),
            canonical_source_sha256=expected_manifest["canonical_source"][
                "sha256"
            ],
        )

    previous = _read_previous_manifest(root)
    conflicts, stale = _preflight_generation(root, rendered, previous)
    if conflicts:
        raise AdapterError(
            "adapter generation stopped to protect unowned or modified files",
            conflicts,
        )

    for path, content in rendered.items():
        target = _target(root, path)
        if target.is_file() and not target.is_symlink():
            try:
                if target.read_bytes() == content:
                    continue
            except OSError as exc:
                raise AdapterError(
                    "cannot read generated adapter destination",
                    {"path": path, "error": str(exc)},
                ) from exc
        _atomic_write(root, path, content)

    for path, expected_hash in stale:
        target = _target(root, path)
        if not target.exists() and not target.is_symlink():
            continue
        if target.is_symlink() or not target.is_file():
            raise AdapterError(
                "stale generated adapter changed during generation",
                {"stale_modified": [path]},
            )
        current = sha256_bytes(target.read_bytes())
        if current != expected_hash:
            raise AdapterError(
                "stale generated adapter changed during generation",
                {"stale_modified": [path]},
            )
        target.unlink()

    _atomic_write(root, MANIFEST_PATH, manifest_bytes)
    return _result(
        f"generated {len(rendered)} harness adapter files",
        checked=False,
        paths=tuple(rendered),
        canonical_source_sha256=expected_manifest["canonical_source"]["sha256"],
        removed=tuple(path for path, _ in stale),
    )


def render_adapters(
    repository_root: Path,
    pipeline: PipelineConfig,
    command_metadata: Mapping[str, Any],
) -> dict[str, bytes]:
    """Render all generated adapter files in stable path order."""

    root = repository_root.resolve(strict=True)
    agents = _normalized_text(root / "AGENTS.md", "AGENTS.md")
    skill_sources = _skill_sources(root)
    cli_commands = _known_cli_commands(command_metadata)
    for command in ADAPTER_COMMANDS:
        if command.cli_command not in cli_commands:
            raise AdapterError(
                "adapter command is absent from CLI metadata",
                {"command": command.cli_command},
            )

    files: dict[str, bytes] = {}
    files[".claude/CLAUDE.md"] = _markdown_document(
        "AGENTS.md",
        agents,
        preface="The following repository instructions mirror the canonical AGENTS.md.\n\n",
    )
    for skill_path, skill_text in skill_sources:
        name = Path(skill_path).parent.name
        files[f".claude/skills/{name}/SKILL.md"] = _skill_mirror(
            skill_path, skill_text
        )
    for command in ADAPTER_COMMANDS:
        files[f".claude/commands/specromancy/{command.name}.md"] = (
            _command_wrapper("claude", command)
        )

    files[".github/copilot-instructions.md"] = _markdown_document(
        "AGENTS.md",
        agents,
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
            "follow that canonical procedure exactly. Stop at any recorded approval, block, "
            "validation failure, or terminal result."
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
            "init": '"$ARGUMENTS"',
            "resume": '"$0"',
            "status": '"$0"',
            "phase": '"$0" "$1"',
        }[command.name]
    elif harness == "opencode":
        arguments = {
            "init": '"$ARGUMENTS"',
            "resume": '"$1"',
            "status": '"$1"',
            "phase": '"$1" "$2"',
        }[command.name]
    else:
        arguments = command.arguments
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


def _manifest(
    root: Path,
    pipeline: PipelineConfig,
    command_metadata: Mapping[str, Any],
    rendered: Mapping[str, bytes],
) -> dict[str, Any]:
    sources = _canonical_sources(root, pipeline, command_metadata)
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


def _canonical_sources(
    root: Path,
    pipeline: PipelineConfig,
    command_metadata: Mapping[str, Any],
) -> list[dict[str, str]]:
    sources = [
        _file_source(root, "AGENTS.md"),
        {
            "kind": "validated-pipeline",
            "path": relative_path(pipeline.path, root),
            "sha256": sha256_bytes(pipeline.canonical_json.encode("utf-8")),
        },
    ]
    for path, text in _skill_sources(root):
        sources.append(
            {
                "kind": "canonical-skill",
                "path": path,
                "sha256": sha256_bytes(text.encode("utf-8")),
            }
        )
    sources.append(
        {
            "kind": "cli-help-metadata",
            "path": "@cli-help-metadata",
            "sha256": sha256_bytes(canonical_json_bytes(command_metadata)),
        }
    )
    return sources


def _file_source(root: Path, path: str) -> dict[str, str]:
    text = _normalized_text(root / path, path)
    return {
        "kind": "repository-instructions",
        "path": path,
        "sha256": sha256_bytes(text.encode("utf-8")),
    }


def _skill_sources(root: Path) -> list[tuple[str, str]]:
    skills_root = root / ".agents" / "skills"
    paths = sorted(skills_root.glob("*/SKILL.md"), key=lambda item: item.as_posix())
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


def _target_for_path(path: str) -> str:
    if path.startswith(".claude/"):
        return "claude"
    if path.startswith(".github/"):
        return "copilot"
    if path.startswith(".opencode/"):
        return "opencode"
    raise AdapterError("generated path has no target harness", {"path": path})


def _read_previous_manifest(root: Path) -> dict[str, Any] | None:
    path = _target(root, MANIFEST_PATH)
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file():
        raise AdapterError("adapter manifest is not a regular file", {"path": MANIFEST_PATH})
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AdapterError(
            "adapter manifest is unreadable or invalid",
            {"path": MANIFEST_PATH, "error": str(exc)},
        ) from exc
    _owned_paths(value)
    return value


def _owned_paths(manifest: Mapping[str, Any]) -> dict[str, str]:
    if manifest.get("schema_version") != ADAPTER_SCHEMA_VERSION:
        raise AdapterError(
            "unsupported adapter manifest schema",
            {"path": MANIFEST_PATH, "schema_version": manifest.get("schema_version")},
        )
    generated = manifest.get("generated")
    if not isinstance(generated, list):
        raise AdapterError("adapter manifest has no generated path list", {"path": MANIFEST_PATH})
    owned: dict[str, str] = {}
    for item in generated:
        if not isinstance(item, Mapping):
            raise AdapterError(
                "adapter manifest has an invalid generated entry",
                {"path": MANIFEST_PATH},
            )
        path = item.get("path")
        digest = item.get("sha256")
        try:
            normalized = normalize_relative_path(path)
        except (TypeError, ValueError) as exc:
            raise AdapterError(
                "adapter manifest contains an unsafe path",
                {"path": path, "error": str(exc)},
            ) from exc
        if normalized == MANIFEST_PATH or normalized in owned:
            raise AdapterError(
                "adapter manifest contains a duplicate or self-owned path",
                {"path": normalized},
            )
        if not _is_managed_adapter_path(normalized):
            raise AdapterError(
                "adapter manifest contains a path outside generated adapter locations",
                {"path": normalized},
            )
        target = item.get("target")
        if target != _target_for_path(normalized):
            raise AdapterError(
                "adapter manifest target does not match its generated path",
                {"path": normalized, "target": target},
            )
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise AdapterError(
                "adapter manifest contains an invalid content hash",
                {"path": normalized, "sha256": digest},
            )
        owned[normalized] = digest
    return owned


def _preflight_generation(
    root: Path,
    rendered: Mapping[str, bytes],
    previous: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    owned = {} if previous is None else _owned_paths(previous)
    expected = set(rendered)
    conflicts: dict[str, Any] = {}
    unowned = []
    unsafe = []
    for path in sorted(expected):
        target = _target(root, path)
        problem = _unsafe_existing_path(root, target)
        if problem is not None:
            unsafe.append({"path": path, "reason": problem})
        elif (target.exists() or target.is_symlink()) and path not in owned:
            unowned.append(path)

    unexpected = sorted(_managed_paths(root) - expected - set(owned))
    if unexpected:
        unowned.extend(path for path in unexpected if path not in unowned)

    stale: list[tuple[str, str]] = []
    stale_modified = []
    for path in sorted(set(owned) - expected):
        target = _target(root, path)
        if not target.exists() and not target.is_symlink():
            continue
        problem = _unsafe_existing_path(root, target)
        if problem is not None or target.is_symlink() or not target.is_file():
            stale_modified.append(path)
            continue
        try:
            current_hash = sha256_bytes(target.read_bytes())
        except OSError:
            stale_modified.append(path)
            continue
        if current_hash == owned[path]:
            stale.append((path, owned[path]))
        else:
            stale_modified.append(path)

    if unowned:
        conflicts["unowned"] = sorted(unowned)
    if unsafe:
        conflicts["unsafe"] = unsafe
    if stale_modified:
        conflicts["stale_modified"] = stale_modified
    return conflicts, stale


def _compare(
    root: Path, rendered: Mapping[str, bytes], manifest_bytes: bytes
) -> dict[str, Any]:
    missing = []
    modified = []
    for path, expected in (*rendered.items(), (MANIFEST_PATH, manifest_bytes)):
        target = _target(root, path)
        if not target.exists() and not target.is_symlink():
            missing.append(path)
            continue
        if target.is_symlink() or not target.is_file():
            modified.append(path)
            continue
        try:
            actual = target.read_bytes()
        except OSError:
            modified.append(path)
            continue
        if actual != expected:
            modified.append(path)
    unexpected = sorted(_managed_paths(root) - set(rendered))
    return {
        "missing": sorted(missing),
        "modified": sorted(modified),
        "unexpected": unexpected,
    }


def _has_drift(drift: Mapping[str, Any]) -> bool:
    return any(bool(value) for value in drift.values())


def _managed_paths(root: Path) -> set[str]:
    paths: set[str] = set()
    singles = (".claude/CLAUDE.md", ".github/copilot-instructions.md")
    for path in singles:
        target = root / path
        if target.exists() or target.is_symlink():
            paths.add(path)
    scans = (
        (root / ".claude" / "skills", "*/SKILL.md"),
        (root / ".claude" / "commands" / "specromancy", "*.md"),
        (root / ".github" / "prompts", "specromancy-*.prompt.md"),
        (root / ".opencode" / "commands", "specromancy-*.md"),
    )
    for directory, pattern in scans:
        if not directory.is_dir() or directory.is_symlink():
            continue
        for candidate in directory.glob(pattern):
            if candidate.is_file() or candidate.is_symlink():
                try:
                    paths.add(candidate.relative_to(root).as_posix())
                except ValueError:
                    continue
    return paths


def _is_managed_adapter_path(path: str) -> bool:
    parts = Path(path).parts
    if path in {".claude/CLAUDE.md", ".github/copilot-instructions.md"}:
        return True
    if len(parts) == 4 and parts[:2] == (".claude", "skills"):
        return parts[3] == "SKILL.md"
    if len(parts) == 4 and parts[:3] == (".claude", "commands", "specromancy"):
        return parts[3].endswith(".md")
    if len(parts) == 3 and parts[:2] == (".github", "prompts"):
        return parts[2].startswith("specromancy-") and parts[2].endswith(
            ".prompt.md"
        )
    if len(parts) == 3 and parts[:2] == (".opencode", "commands"):
        return parts[2].startswith("specromancy-") and parts[2].endswith(".md")
    return False


def _unsafe_existing_path(root: Path, target: Path) -> str | None:
    current = root
    for part in target.relative_to(root).parts[:-1]:
        current = current / part
        if current.is_symlink():
            return "parent-is-symlink"
        if current.exists() and not current.is_dir():
            return "parent-is-not-directory"
    if target.is_symlink():
        return "target-is-symlink"
    if target.exists() and not target.is_file():
        return "target-is-not-file"
    return None


def _target(root: Path, relative: str) -> Path:
    normalized = normalize_relative_path(relative)
    return root / normalized


def _atomic_write(root: Path, relative: str, content: bytes) -> None:
    target = _target(root, relative)
    problem = _unsafe_existing_path(root, target)
    if problem is not None:
        raise AdapterError(
            "generated adapter destination is unsafe",
            {"path": relative, "reason": problem},
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _result(
    message: str,
    *,
    checked: bool,
    paths: tuple[str, ...],
    canonical_source_sha256: str,
    removed: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "adapters",
        "code": int(ExitCode.SUCCESS),
        "message": message,
        "adapters": {
            "checked": checked,
            "manifest": MANIFEST_PATH,
            "canonical_source_sha256": canonical_source_sha256,
            "paths": list(paths),
            "removed": list(removed),
        },
    }
