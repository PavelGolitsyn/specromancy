"""Contract validation for reviewable, requirement-traced plan artifacts."""

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
    "## Outcome",
    "## Scope",
    "## Requirements traceability",
    "## Proposed changes",
    "## Data and interface changes",
    "## Verification strategy",
    "## Rollout and rollback",
    "## Risks and mitigations",
    "## Open decisions",
    "## Implementation sequence",
)
TRACEABILITY_HEADERS: Final = (
    "Requirement ID",
    "Evidence IDs",
    "Planned changes",
    "Verification",
)
PROPOSED_CHANGE_HEADERS: Final = (
    "Change ID",
    "Action",
    "Path",
    "Description",
    "Approval-sensitive",
)
OPEN_DECISION_HEADERS: Final = ("Decision ID", "Decision", "Blocking", "Status")
_REQUIREMENT_ID: Final = re.compile(r"REQ-[0-9]{3,}")
_EVIDENCE_ID: Final = re.compile(r"E-[0-9]{3,}")
_CHANGE_ID: Final = re.compile(r"CHG-[0-9]{3,}")
_DECISION_ID: Final = re.compile(r"DEC-[0-9]{3,}")
_TEMPLATE_VARIABLE: Final = re.compile(r"\{\{[^}\n]+\}\}")
_PATCH_FENCE: Final = re.compile(
    r"```(?:diff|patch)[^\n]*\n|diff --git |\*\*\* Begin Patch",
    re.IGNORECASE,
)
_APPROVAL_SENSITIVE: Final = (
    re.compile(
        r"\b(?:delete|remove|drop|destroy|destructive|truncate|overwrite)\w*\b", re.I
    ),
    re.compile(r"\b(?:add|new|install|introduce)\w*\s+(?:runtime\s+)?dependenc", re.I),
    re.compile(r"\b(?:schema|database|data)\s+migrat", re.I),
    re.compile(r"\bpublic\s+(?:api|interface)\b", re.I),
    re.compile(
        r"\bproduction\s+(?:action|change|deploy\w*|migration|operation)\b", re.I
    ),
)


@dataclass(frozen=True)
class TraceabilityRow:
    requirement_id: str
    evidence_ids: tuple[str, ...]
    change_ids: tuple[str, ...]
    verification: str


@dataclass(frozen=True)
class ProposedChange:
    change_id: str
    action: str
    path: str
    description: str
    approval_sensitive: bool


@dataclass(frozen=True)
class OpenDecision:
    decision_id: str
    decision: str
    blocking: bool
    status: str


@dataclass(frozen=True)
class PlanArtifact:
    metadata: Mapping[str, str]
    sections: Mapping[str, str]
    traceability: tuple[TraceabilityRow, ...]
    proposed_changes: tuple[ProposedChange, ...]
    decisions: tuple[OpenDecision, ...]

    @property
    def planned_paths(self) -> tuple[str, ...]:
        return tuple(change.path for change in self.proposed_changes)


def _failure(message: str, hint: str, **details: object) -> ValidationError:
    return ValidationError(message, hint=hint, details=details)


def _identifiers(value: str, pattern: re.Pattern[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(pattern.findall(value)))


def _required_ids(requirements: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    result: list[str] = []
    for index, requirement in enumerate(requirements, start=1):
        requirement_id = requirement.get("id")
        if not isinstance(requirement_id, str) or _REQUIREMENT_ID.fullmatch(requirement_id) is None:
            raise _failure(
                f"Run requirement {index} has no valid stable ID.",
                "Regenerate run requirements using IDs such as REQ-001 before planning.",
            )
        if requirement_id in result:
            raise _failure(
                f"Run requirement '{requirement_id}' is duplicated.",
                "Give every initialized request requirement one unique stable ID.",
            )
        result.append(requirement_id)
    if not result:
        raise _failure(
            "The run has no initialized requirements to trace.",
            "Initialize at least one request goal or acceptance criterion before planning.",
        )
    return tuple(result)


def _parse_changes(section: str, paths: RepositoryPaths) -> tuple[ProposedChange, ...]:
    table = parse_markdown_table(
        section, PROPOSED_CHANGE_HEADERS, table_name="Proposed changes"
    )
    changes: list[ProposedChange] = []
    identifiers: set[str] = set()
    for values in table.rows:
        change_id = values["Change ID"]
        if _CHANGE_ID.fullmatch(change_id) is None:
            raise _failure(
                f"Change ID '{change_id}' is malformed.",
                "Use stable IDs such as CHG-001, CHG-002, and CHG-003.",
            )
        if change_id in identifiers:
            raise _failure(
                f"Change ID '{change_id}' is duplicated.",
                "Give every proposed change a unique stable ID.",
            )
        identifiers.add(change_id)
        action = values["Action"].strip().casefold()
        if action not in {"modify", "create", "delete"}:
            raise _failure(
                f"Change '{change_id}' has unsupported action '{values['Action']}'.",
                "Use modify, create, or delete; describe generated outputs in the change text.",
            )
        raw_path = values["Path"].strip().replace("`", "")
        try:
            target = paths.resolve_relative(raw_path)
        except (SafetyError, ValidationError) as exc:
            raise _failure(
                f"Change '{change_id}' uses an unsafe repository path.",
                "Use one repository-relative POSIX path with no '..' components.",
                change_id=change_id,
                path=raw_path,
            ) from exc
        if action == "create" and target.exists():
            raise _failure(
                f"Change '{change_id}' marks an existing path as create.",
                "Use action 'modify' for an existing file or directory.",
                change_id=change_id,
                path=raw_path,
            )
        if action != "create" and not target.exists():
            raise _failure(
                f"Change '{change_id}' names an existing target that cannot be found.",
                "Correct the path or mark a new file explicitly with action 'create'.",
                change_id=change_id,
                path=raw_path,
            )
        sensitivity = values["Approval-sensitive"].strip().casefold()
        if sensitivity not in {"yes", "no"}:
            raise _failure(
                f"Change '{change_id}' has an invalid approval-sensitive label.",
                "Use Yes or No and explain the reason in the description.",
            )
        combined = f"{action} {raw_path} {values['Description']}"
        needs_approval = action == "delete" or any(
            pattern.search(combined) for pattern in _APPROVAL_SENSITIVE
        )
        if needs_approval and sensitivity != "yes":
            raise _failure(
                f"Change '{change_id}' is approval-sensitive but is labeled No.",
                (
                    "Label destructive operations, dependency additions, schema migrations, "
                    "public API changes, and production actions as approval-sensitive."
                ),
                change_id=change_id,
            )
        changes.append(
            ProposedChange(
                change_id=change_id,
                action=action,
                path=paths.serialize(target),
                description=values["Description"],
                approval_sensitive=sensitivity == "yes",
            )
        )
    return tuple(changes)


def _parse_traceability(
    section: str,
    required_ids: Sequence[str],
    evidence_ids: Sequence[str],
    change_ids: Sequence[str],
) -> tuple[TraceabilityRow, ...]:
    table = parse_markdown_table(
        section, TRACEABILITY_HEADERS, table_name="Requirements traceability"
    )
    known_evidence = set(evidence_ids)
    known_changes = set(change_ids)
    rows: list[TraceabilityRow] = []
    observed: set[str] = set()
    for values in table.rows:
        requirement_id = values["Requirement ID"]
        if _REQUIREMENT_ID.fullmatch(requirement_id) is None:
            raise _failure(
                f"Requirement ID '{requirement_id}' is malformed.",
                "Use the stable REQ-NNN IDs recorded in run.json.",
            )
        if requirement_id not in required_ids:
            raise _failure(
                f"Traceability row names unknown requirement '{requirement_id}'.",
                "Use only request requirement IDs recorded in run.json.",
            )
        if requirement_id in observed:
            raise _failure(
                f"Requirement '{requirement_id}' has more than one traceability row.",
                "Combine its evidence, planned changes, and verification in one row.",
            )
        observed.add(requirement_id)
        row_evidence = _identifiers(values["Evidence IDs"], _EVIDENCE_ID)
        if not row_evidence:
            raise _failure(
                f"Requirement '{requirement_id}' has no evidence ID.",
                "Cite one or more E-NNN IDs from the validated research artifact.",
            )
        unknown_evidence = [item for item in row_evidence if item not in known_evidence]
        if unknown_evidence:
            raise _failure(
                f"Requirement '{requirement_id}' cites unknown evidence IDs.",
                "Use evidence IDs present in the current validated research artifact.",
                requirement_id=requirement_id,
                evidence_ids=unknown_evidence,
            )
        row_changes = _identifiers(values["Planned changes"], _CHANGE_ID)
        if not row_changes:
            raise _failure(
                f"Requirement '{requirement_id}' has no planned change ID.",
                "Map the requirement to one or more CHG-NNN rows.",
            )
        unknown_changes = [item for item in row_changes if item not in known_changes]
        if unknown_changes:
            raise _failure(
                f"Requirement '{requirement_id}' cites unknown planned changes.",
                "Use change IDs defined in the Proposed changes table.",
                requirement_id=requirement_id,
                change_ids=unknown_changes,
            )
        verification = values["Verification"].strip()
        if verification.casefold() in {"none", "n/a", "not applicable"}:
            raise _failure(
                f"Requirement '{requirement_id}' has no verification method.",
                "Name at least one observable check, test, or inspection for this requirement.",
                requirement_id=requirement_id,
            )
        rows.append(
            TraceabilityRow(
                requirement_id=requirement_id,
                evidence_ids=row_evidence,
                change_ids=row_changes,
                verification=verification,
            )
        )
    missing = [item for item in required_ids if item not in observed]
    if missing:
        raise _failure(
            "Plan traceability is missing request requirements.",
            "Add one complete traceability row for every listed requirement ID.",
            missing_requirement_ids=missing,
        )
    return tuple(rows)


def _parse_decisions(section: str) -> tuple[OpenDecision, ...]:
    if section.strip().rstrip(".").casefold() in {"none", "no open decisions"}:
        return ()
    table = parse_markdown_table(section, OPEN_DECISION_HEADERS, table_name="Open decisions")
    decisions: list[OpenDecision] = []
    observed: set[str] = set()
    for values in table.rows:
        decision_id = values["Decision ID"]
        if _DECISION_ID.fullmatch(decision_id) is None or decision_id in observed:
            raise _failure(
                f"Decision ID '{decision_id}' is malformed or duplicated.",
                "Use one unique stable ID such as DEC-001 for each decision.",
            )
        observed.add(decision_id)
        blocking_value = values["Blocking"].casefold()
        status = values["Status"].casefold()
        if blocking_value not in {"yes", "no"}:
            raise _failure(
                f"Decision '{decision_id}' has an invalid blocking label.",
                "Use Yes for a choice that must be resolved before approval, otherwise No.",
            )
        if status not in {"open", "resolved"}:
            raise _failure(
                f"Decision '{decision_id}' has an invalid status.",
                "Use Open or Resolved.",
            )
        decision = OpenDecision(
            decision_id=decision_id,
            decision=values["Decision"],
            blocking=blocking_value == "yes",
            status=status,
        )
        if decision.blocking and decision.status == "open":
            raise _failure(
                f"Blocking decision '{decision_id}' is still open.",
                "Resolve the decision and update the plan before validation or approval.",
                decision_id=decision_id,
            )
        decisions.append(decision)
    return tuple(decisions)


def validate_plan(
    text: str,
    repository_root: str | Path,
    run_id: str,
    requirements: Sequence[Mapping[str, object]],
    evidence_ids: Sequence[str],
) -> PlanArtifact:
    """Validate one completed plan against initialized requirements and research."""

    document = parse_frontmatter(
        text,
        expected_run_id=run_id,
        expected_stage="plan",
        expected_status="ready",
    )
    body = document.body
    if _TEMPLATE_VARIABLE.search(body):
        raise _failure(
            "Plan artifact still contains a template variable.",
            "Replace every {{ ... }} value with a concrete plan statement.",
        )
    if _PATCH_FENCE.search(body):
        raise _failure(
            "Plan artifact contains a purported implementation patch.",
            "Describe file and interface actions without embedding implementation patches.",
        )
    sections = require_headings_in_order(
        body, REQUIRED_HEADINGS, artifact_name="Plan"
    )
    required_ids = _required_ids(requirements)
    paths = RepositoryPaths(Path(repository_root))
    changes = _parse_changes(sections["## Proposed changes"], paths)
    traceability = _parse_traceability(
        sections["## Requirements traceability"],
        required_ids,
        evidence_ids,
        [change.change_id for change in changes],
    )
    decisions = _parse_decisions(sections["## Open decisions"])
    sequence = sections["## Implementation sequence"]
    if re.search(r"(?m)^\s*[0-9]+[.)]\s+\S", sequence) is None:
        raise _failure(
            "Plan implementation sequence has no ordered steps.",
            "Add a numbered sequence that an implementation agent can follow.",
        )
    return PlanArtifact(
        metadata=document.metadata,
        sections=sections,
        traceability=traceability,
        proposed_changes=changes,
        decisions=decisions,
    )


validate_plan_artifact = validate_plan
validate = validate_plan
