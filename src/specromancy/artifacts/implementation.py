"""Validation for durable implementation handoff artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Mapping, Sequence

from ..errors import SafetyError, ValidationError
from ..paths import RepositoryPaths
from .frontmatter import parse_frontmatter
from .markdown import parse_markdown_table, require_headings_in_order


REQUIRED_HEADINGS: Final = (
    "## Summary",
    "## Plan items completed",
    "## Files changed",
    "## Deviations from plan",
    "## Verification performed",
    "## Known limitations",
    "## Review handoff",
)
PLAN_ITEM_HEADERS: Final = ("Change ID", "Status", "Notes")
FILE_HEADERS: Final = ("Path", "Classification", "Notes")
DEVIATION_HEADERS: Final = ("Deviation ID", "Material", "Description")
VERIFICATION_HEADERS: Final = ("Command ID", "Exit code", "Blocking", "Outcome")
REVIEW_FINDING_HEADERS: Final = ("Finding ID", "Status", "Notes")
_CHANGE_ID: Final = re.compile(r"CHG-[0-9]{3,}")
_DEVIATION_ID: Final = re.compile(r"DEV-[0-9]{3,}")
_COMMAND_ID: Final = re.compile(r"CMD-[0-9]{3,}")
_FINDING_ID: Final = re.compile(r"REV-[0-9]{3,}")
_TEMPLATE: Final = re.compile(r"\{\{[^}\n]+\}\}|\b(?:TODO|TBD)\b", re.I)
_SECRET_PATTERNS: Final = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(
        r"\b(?:password|passwd|api[_-]?key|access[_-]?token|secret)\s*[:=]\s*[\"']?[^\s\"']{8,}",
        re.I,
    ),
    re.compile(r"\b(?:ghp|github_pat|sk)-[A-Za-z0-9_-]{12,}\b"),
)
CLASSIFICATIONS: Final = {
    "planned",
    "generated",
    "implied_support",
    "pre_existing_user_change",
    "approved_deviation",
}


@dataclass(frozen=True)
class PlanItemResult:
    change_id: str
    status: str
    notes: str


@dataclass(frozen=True)
class ChangedFileDeclaration:
    path: str
    classification: str
    notes: str


@dataclass(frozen=True)
class Deviation:
    deviation_id: str
    material: bool
    description: str


@dataclass(frozen=True)
class VerificationDeclaration:
    command_id: str
    exit_code: int
    blocking: bool
    outcome: str


@dataclass(frozen=True)
class ImplementationArtifact:
    metadata: Mapping[str, str]
    sections: Mapping[str, str]
    plan_items: tuple[PlanItemResult, ...]
    files: tuple[ChangedFileDeclaration, ...]
    deviations: tuple[Deviation, ...]
    verifications: tuple[VerificationDeclaration, ...]
    addressed_findings: tuple[str, ...]


def _failure(message: str, hint: str, **details: object) -> ValidationError:
    return ValidationError(message, hint=hint, details=details)


def _none(section: str) -> bool:
    return section.strip().rstrip(".").casefold() in {"none", "no deviations", "no findings"}


def _plan_items(section: str, planned_change_ids: Sequence[str]) -> tuple[PlanItemResult, ...]:
    table = parse_markdown_table(section, PLAN_ITEM_HEADERS, table_name="Plan items completed")
    known = set(planned_change_ids)
    observed: set[str] = set()
    results: list[PlanItemResult] = []
    for values in table.rows:
        change_id = values["Change ID"]
        status = values["Status"].casefold()
        if _CHANGE_ID.fullmatch(change_id) is None or change_id not in known:
            raise _failure(
                f"Implementation names unknown plan item '{change_id}'.",
                "Use the CHG-NNN identifiers from the approved plan.",
            )
        if change_id in observed:
            raise _failure(f"Plan item '{change_id}' is duplicated.", "Keep one row per plan item.")
        if status not in {"completed", "deferred", "blocked"}:
            raise _failure(
                f"Plan item '{change_id}' has invalid status '{values['Status']}'.",
                "Use Completed, Deferred, or Blocked and explain non-completed work.",
            )
        observed.add(change_id)
        results.append(PlanItemResult(change_id, status, values["Notes"]))
    missing = [item for item in planned_change_ids if item not in observed]
    if missing:
        raise _failure(
            "Implementation does not account for every approved plan item.",
            "Add a completed, deferred, or blocked row for every CHG-NNN item.",
            missing_change_ids=missing,
        )
    return tuple(results)


def _files(section: str, paths: RepositoryPaths) -> tuple[ChangedFileDeclaration, ...]:
    if _none(section):
        return ()
    table = parse_markdown_table(section, FILE_HEADERS, table_name="Files changed")
    observed: set[str] = set()
    results: list[ChangedFileDeclaration] = []
    for values in table.rows:
        raw_path = values["Path"].strip().replace("`", "")
        try:
            target = paths.resolve_relative(raw_path)
        except (SafetyError, ValidationError) as exc:
            raise _failure(
                f"Implementation declares unsafe changed path '{raw_path}'.",
                "Use a repository-relative POSIX path with no parent traversal.",
            ) from exc
        path = paths.serialize(target)
        classification = values["Classification"].casefold().replace(" ", "_").replace("-", "_")
        if classification not in CLASSIFICATIONS:
            raise _failure(
                f"Changed file '{path}' has unsupported classification.",
                "Use planned, generated, implied_support, pre_existing_user_change, or approved_deviation.",
            )
        if path in observed:
            raise _failure(f"Changed file '{path}' is duplicated.", "Keep one row per changed path.")
        observed.add(path)
        results.append(ChangedFileDeclaration(path, classification, values["Notes"]))
    return tuple(results)


def _deviations(section: str) -> tuple[Deviation, ...]:
    if _none(section):
        return ()
    table = parse_markdown_table(section, DEVIATION_HEADERS, table_name="Deviations from plan")
    results: list[Deviation] = []
    observed: set[str] = set()
    for values in table.rows:
        deviation_id = values["Deviation ID"]
        if _DEVIATION_ID.fullmatch(deviation_id) is None or deviation_id in observed:
            raise _failure(
                f"Deviation ID '{deviation_id}' is malformed or duplicated.",
                "Use one stable ID such as DEV-001 for each deviation.",
            )
        material = values["Material"].casefold()
        if material not in {"yes", "no"}:
            raise _failure(f"Deviation '{deviation_id}' has invalid material label.", "Use Yes or No.")
        observed.add(deviation_id)
        results.append(Deviation(deviation_id, material == "yes", values["Description"]))
    return tuple(results)


def _verifications(section: str) -> tuple[VerificationDeclaration, ...]:
    table = parse_markdown_table(section, VERIFICATION_HEADERS, table_name="Verification performed")
    results: list[VerificationDeclaration] = []
    observed: set[str] = set()
    for values in table.rows:
        command_id = values["Command ID"]
        if _COMMAND_ID.fullmatch(command_id) is None or command_id in observed:
            raise _failure(
                f"Command ID '{command_id}' is malformed or duplicated.",
                "Use each persisted CMD-NNN record exactly once.",
            )
        try:
            exit_code = int(values["Exit code"])
        except ValueError as exc:
            raise _failure(f"Command '{command_id}' has a non-integer exit code.", "Copy the recorded exit code.") from exc
        blocking = values["Blocking"].casefold()
        if blocking not in {"yes", "no"}:
            raise _failure(f"Command '{command_id}' has invalid blocking label.", "Use Yes or No.")
        observed.add(command_id)
        results.append(VerificationDeclaration(command_id, exit_code, blocking == "yes", values["Outcome"]))
    return tuple(results)


def _findings(section: str) -> tuple[str, ...]:
    if _none(section):
        return ()
    table = parse_markdown_table(section, REVIEW_FINDING_HEADERS, table_name="Review handoff")
    results: list[str] = []
    for values in table.rows:
        finding_id = values["Finding ID"]
        if _FINDING_ID.fullmatch(finding_id) is None or finding_id in results:
            raise _failure(
                f"Review finding ID '{finding_id}' is malformed or duplicated.",
                "Use each REV-NNN identifier from the current review once.",
            )
        status = values["Status"].casefold()
        if status not in {"addressed", "invalid", "blocked"}:
            raise _failure(
                f"Review finding '{finding_id}' has invalid status.",
                "Use Addressed, Invalid, or Blocked and explain the result.",
            )
        results.append(finding_id)
    return tuple(results)


def validate_implementation(
    text: str,
    repository_root: str | Path,
    run_id: str,
    planned_change_ids: Sequence[str],
) -> ImplementationArtifact:
    document = parse_frontmatter(
        text,
        expected_run_id=run_id,
        expected_stage="implementation",
        expected_status="ready",
    )
    if _TEMPLATE.search(document.body):
        raise _failure(
            "Implementation artifact still contains a placeholder marker.",
            "Replace every template value with a concrete result.",
        )
    if any(pattern.search(document.body) for pattern in _SECRET_PATTERNS):
        raise _failure(
            "Implementation artifact contains a value that looks like a secret.",
            "Remove the sensitive value and record only a safe description.",
        )
    sections = require_headings_in_order(
        document.body, REQUIRED_HEADINGS, artifact_name="Implementation"
    )
    paths = RepositoryPaths(Path(repository_root))
    return ImplementationArtifact(
        metadata=document.metadata,
        sections=sections,
        plan_items=_plan_items(sections["## Plan items completed"], planned_change_ids),
        files=_files(sections["## Files changed"], paths),
        deviations=_deviations(sections["## Deviations from plan"]),
        verifications=_verifications(sections["## Verification performed"]),
        addressed_findings=_findings(sections["## Review handoff"]),
    )


validate_implementation_artifact = validate_implementation
validate = validate_implementation

