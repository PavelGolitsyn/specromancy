"""Static repository validation and reusable safety boundaries."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote

from .errors import InvalidInputError, SafetyError, ValidationError
from .io import DEFAULT_TEXT_LIMIT, read_text
from .paths import RepositoryPaths
from .redaction import contains_secret


MAX_REFERENCE_DEPTH = 3
_MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
_FENCED_COMMAND = re.compile(r"(?m)^\s*\$?\s*specromancy\s+([a-z][a-z-]*)\b")
_KNOWN_COMMANDS = {
    "init", "status", "next", "phase", "artifact", "approve", "approval",
    "validate", "verify", "lock", "resume", "cancel", "adapters", "doctor",
}


@dataclass(frozen=True)
class SecurityFinding:
    check: str
    status: str
    path: str | None
    message: str

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)


def validate_subprocess_argv(argv: object) -> tuple[str, ...]:
    """Validate a shell-free subprocess argument array."""

    if (
        not isinstance(argv, (list, tuple))
        or not argv
        or any(not isinstance(item, str) or not item or "\x00" in item for item in argv)
    ):
        raise InvalidInputError("Subprocess argv must contain nonempty, NUL-free strings.")
    if any(contains_secret(item) for item in argv):
        raise SafetyError("Subprocess arguments contain a value that looks like a secret.")
    return tuple(argv)


def validate_repository_file(
    root: str | Path,
    relative_path: str | Path,
    *,
    max_bytes: int = DEFAULT_TEXT_LIMIT,
) -> Path:
    """Resolve a regular repository-confined file and enforce its size cap."""

    paths = RepositoryPaths(Path(root))
    target = paths.resolve_relative(relative_path)
    if not target.is_file():
        raise ValidationError("Managed repository file is missing.", path=str(relative_path))
    read_text(target, max_bytes=max_bytes)
    return target


def _frontmatter(skill: Path, expected_name: str) -> dict[str, str]:
    text = read_text(skill)
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValidationError(
            f"Canonical skill '{expected_name}' has no YAML frontmatter.", path=str(skill)
        )
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise ValidationError(
            f"Canonical skill '{expected_name}' has unclosed YAML frontmatter.", path=str(skill)
        ) from exc
    metadata: dict[str, str] = {}
    for line in lines[1:closing]:
        key, separator, value = line.partition(":")
        if separator and key in {"name", "description"}:
            if key in metadata:
                raise ValidationError(
                    f"Canonical skill '{expected_name}' repeats '{key}'.", path=str(skill)
                )
            metadata[key] = value.strip().strip("\"'")
    description = metadata.get("description", "")
    if metadata.get("name") != expected_name or not description:
        raise ValidationError(
            f"Canonical skill '{expected_name}' is not discoverable.",
            path=str(skill),
            hint=f"Set non-empty 'name: {expected_name}' and 'description:' fields.",
        )
    lowered = description.lower()
    if len(description.split()) < 3 or not any(
        marker in lowered
        for marker in (" when ", " for ", " use ", " using ", " only ", " phase", " against ")
    ):
        raise ValidationError(
            f"Canonical skill '{expected_name}' description must say what it does and when it applies.",
            path=str(skill),
        )
    return metadata


def _local_markdown_targets(source: Path) -> tuple[str, ...]:
    targets: list[str] = []
    for raw in _MARKDOWN_LINK.findall(read_text(source)):
        target = raw.strip().split(maxsplit=1)[0].strip("<>")
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        targets.append(unquote(target.partition("#")[0]))
    return tuple(targets)


def validate_canonical_skills(
    root: str | Path,
    names: tuple[str, ...],
    *,
    max_depth: int = MAX_REFERENCE_DEPTH,
) -> tuple[Path, ...]:
    """Validate canonical skill identity and confined, shallow, acyclic references."""

    repository = Path(root).resolve()
    validated: list[Path] = []
    for name in names:
        skill_dir = repository / ".agents" / "skills" / name
        skill = skill_dir / "SKILL.md"
        if skill_dir.name != name or not skill.is_file():
            raise ValidationError(f"Canonical skill '{name}' is missing.", path=str(skill))
        _frontmatter(skill, name)
        visiting: set[Path] = set()
        visited: set[Path] = set()

        def walk(source: Path, depth: int) -> None:
            resolved_source = source.resolve()
            if resolved_source in visiting:
                raise ValidationError(
                    f"Canonical skill '{name}' contains a cyclic reference chain.",
                    path=str(source),
                )
            if resolved_source in visited:
                return
            if depth > max_depth:
                raise ValidationError(
                    f"Canonical skill '{name}' reference chain exceeds depth {max_depth}.",
                    path=str(source),
                )
            visiting.add(resolved_source)
            for reference in _local_markdown_targets(source):
                candidate = (source.parent / reference).resolve()
                try:
                    candidate.relative_to(skill_dir.resolve())
                except ValueError as exc:
                    raise SafetyError(
                        "Canonical skill reference escapes its skill directory.",
                        path=str(source),
                        details={"reference": reference},
                    ) from exc
                if not candidate.is_file():
                    raise ValidationError(
                        "Canonical skill reference is missing.",
                        path=str(source),
                        details={"reference": reference},
                    )
                if candidate.suffix.lower() == ".md":
                    walk(candidate, depth + 1)
            visiting.remove(resolved_source)
            visited.add(resolved_source)

        walk(skill, 0)
        validated.append(skill)
    return tuple(validated)


def validate_json_resources(root: str | Path) -> tuple[Path, ...]:
    repository = Path(root).resolve()
    targets = sorted((repository / "src/specromancy/resources/contracts").glob("*.json"))
    for target in targets:
        try:
            value = json.loads(read_text(target))
        except json.JSONDecodeError as exc:
            raise ValidationError("JSON contract is malformed.", path=str(target)) from exc
        if not isinstance(value, dict):
            raise ValidationError("JSON contract must be an object.", path=str(target))
    for target in sorted((repository / "src/specromancy/templates").glob("*.md")):
        if not read_text(target).strip():
            raise ValidationError("Artifact template is empty.", path=str(target))
    return tuple(targets)


def validate_documentation(root: str | Path) -> tuple[Path, ...]:
    repository = Path(root).resolve()
    documents = [repository / "README.md", *sorted((repository / "docs").rglob("*.md"))]
    for source in documents:
        if not source.is_file():
            continue
        text = read_text(source)
        for reference in _local_markdown_targets(source):
            candidate = (source.parent / reference).resolve()
            try:
                candidate.relative_to(repository)
            except ValueError as exc:
                raise SafetyError("Documentation link escapes the repository.", path=str(source)) from exc
            if not candidate.exists():
                raise ValidationError(
                    "Documentation link target is missing.",
                    path=str(source),
                    details={"reference": reference},
                )
        for command in _FENCED_COMMAND.findall(text):
            if command not in _KNOWN_COMMANDS:
                raise ValidationError(
                    "Documentation example names an unknown command.",
                    path=str(source),
                    details={"command": command},
                )
    return tuple(source for source in documents if source.is_file())


def validate_static_repository(
    root: str | Path,
    *,
    skill_names: tuple[str, ...] = ("pipeline", "research", "plan", "implement", "review"),
) -> tuple[SecurityFinding, ...]:
    repository = Path(root).resolve()
    skills = validate_canonical_skills(repository, skill_names)
    contracts = validate_json_resources(repository)
    documents = validate_documentation(repository)
    return (
        SecurityFinding("canonical_skills", "pass", None, f"Validated {len(skills)} canonical skills."),
        SecurityFinding("contracts", "pass", None, f"Validated {len(contracts)} JSON contracts."),
        SecurityFinding("documentation", "pass", None, f"Validated {len(documents)} documentation files."),
    )
