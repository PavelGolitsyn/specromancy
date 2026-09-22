"""Validation for evidence-backed review artifacts and deterministic verdicts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Mapping, Sequence

from ..errors import ValidationError
from .frontmatter import parse_frontmatter
from .markdown import parse_markdown_table, require_headings_in_order


REQUIRED_HEADINGS: Final = (
    "## Verdict",
    "## Findings",
    "## Requirement coverage",
    "## Verification assessment",
    "## Residual risks",
    "## Repair guidance",
)
FINDING_HEADERS: Final = (
    "Finding ID",
    "Severity",
    "Blocking",
    "Title",
    "Location",
    "Observed",
    "Expected",
    "Impact",
    "Repair guidance",
)
COVERAGE_HEADERS: Final = ("Requirement ID", "Status", "Evidence")
RECONCILIATION_HEADERS: Final = ("Finding ID", "Status", "Evidence")
VERDICTS: Final = {"passed", "changes_requested", "blocked"}
SEVERITIES: Final = ("critical", "high", "medium", "low")
COVERAGE_STATUSES: Final = {"covered", "partial", "missing", "blocked"}
RECONCILIATION_STATUSES: Final = {"fixed", "still_present", "superseded", "invalid"}
_REQUIREMENT_ID: Final = re.compile(r"REQ-[0-9]{3,}")
_FINDING_ID: Final = re.compile(r"REV-[0-9]{3,}")
_EXPECTATION_REFERENCE: Final = re.compile(
    r"(?:REQ-[0-9]{3,}|CHG-[0-9]{3,}|\b(?:contract|invariant|policy)\b)", re.I
)
_TEMPLATE: Final = re.compile(r"\{\{[^}\n]+\}\}|\b(?:TODO|TBD)\b", re.I)


@dataclass(frozen=True)
class ReviewFinding:
    finding_id: str
    severity: str
    blocking: bool
    title: str
    location: str
    observed: str
    expected: str
    impact: str
    repair_guidance: str


@dataclass(frozen=True)
class RequirementCoverage:
    requirement_id: str
    status: str
    evidence: str


@dataclass(frozen=True)
class FindingReconciliation:
    finding_id: str
    status: str
    evidence: str


@dataclass(frozen=True)
class ReviewArtifact:
    metadata: Mapping[str, str]
    sections: Mapping[str, str]
    verdict: str
    findings: tuple[ReviewFinding, ...]
    coverage: tuple[RequirementCoverage, ...]
    reconciliations: tuple[FindingReconciliation, ...]


def _failure(message: str, hint: str, **details: object) -> ValidationError:
    return ValidationError(message, hint=hint, details=details)


def _none(section: str) -> bool:
    return section.strip().rstrip(".").casefold() in {
        "none",
        "no findings",
        "no actionable findings",
        "not applicable",
    }


def _required_ids(requirements: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    result: list[str] = []
    for index, requirement in enumerate(requirements, start=1):
        requirement_id = requirement.get("id")
        if not isinstance(requirement_id, str) or _REQUIREMENT_ID.fullmatch(requirement_id) is None:
            raise _failure(
                f"Run requirement {index} has no valid stable ID.",
                "Restore version 1 REQ-NNN identifiers before review.",
            )
        if requirement_id in result:
            raise _failure(
                f"Run requirement '{requirement_id}' is duplicated.",
                "Give every run requirement one stable identifier.",
            )
        result.append(requirement_id)
    if not result:
        raise _failure(
            "The run has no requirements to review.",
            "Restore the initialized request requirements before review.",
        )
    return tuple(result)


def _verdict(section: str) -> tuple[str, str]:
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    verdict = lines[0].strip("`*").casefold() if lines else ""
    if verdict not in VERDICTS:
        raise _failure(
            f"Review verdict '{verdict}' is invalid.",
            "Use passed, changes_requested, or blocked on the first line of the Verdict section.",
        )
    rationale = "\n".join(lines[1:]).strip()
    if verdict == "blocked" and not rationale:
        raise _failure(
            "A blocked review has no blocker rationale.",
            "After the blocked verdict, explain which required evidence or verification is unavailable.",
        )
    return verdict, rationale


def _findings(section: str) -> tuple[ReviewFinding, ...]:
    if _none(section):
        return ()
    table = parse_markdown_table(section, FINDING_HEADERS, table_name="Findings")
    findings: list[ReviewFinding] = []
    identifiers: set[str] = set()
    previous_rank = -1
    for values in table.rows:
        finding_id = values["Finding ID"]
        if _FINDING_ID.fullmatch(finding_id) is None:
            raise _failure(
                f"Finding ID '{finding_id}' is malformed.",
                "Use a stable identifier such as REV-001.",
            )
        if finding_id in identifiers:
            raise _failure(
                f"Finding ID '{finding_id}' is duplicated.",
                "Keep one row per actionable finding.",
            )
        severity = values["Severity"].casefold()
        if severity not in SEVERITIES:
            raise _failure(
                f"Finding '{finding_id}' has invalid severity '{values['Severity']}'.",
                "Use critical, high, medium, or low.",
            )
        rank = SEVERITIES.index(severity)
        if rank < previous_rank:
            raise _failure(
                "Review findings are not ordered by severity.",
                "Order findings critical, high, medium, then low.",
            )
        previous_rank = rank
        blocking_label = values["Blocking"].casefold()
        if blocking_label not in {"yes", "no"}:
            raise _failure(
                f"Finding '{finding_id}' has an invalid blocking label.",
                "Use Yes or No.",
            )
        blocking = blocking_label == "yes"
        if severity in {"critical", "high", "medium"} and not blocking:
            raise _failure(
                f"Finding '{finding_id}' cannot be nonblocking at severity {severity}.",
                "Mark critical, high, and medium findings as blocking.",
            )
        location = values["Location"].strip().replace("`", "")
        if (
            location.casefold() in {"none", "unknown", "n/a", "not applicable"}
            or (":" not in location and re.search(r"\bCMD-[0-9]{3,}\b", location) is None)
        ):
            raise _failure(
                f"Finding '{finding_id}' has no precise location.",
                "Name a file and line, artifact section, command record, or other reproducible location.",
            )
        if _EXPECTATION_REFERENCE.search(values["Expected"]) is None:
            raise _failure(
                f"Finding '{finding_id}' has no grounded expectation.",
                "Tie expected behavior to a REQ-NNN, CHG-NNN, contract, policy, or repository invariant.",
            )
        identifiers.add(finding_id)
        findings.append(
            ReviewFinding(
                finding_id=finding_id,
                severity=severity,
                blocking=blocking,
                title=values["Title"],
                location=location,
                observed=values["Observed"],
                expected=values["Expected"],
                impact=values["Impact"],
                repair_guidance=values["Repair guidance"],
            )
        )
    return tuple(findings)


def _coverage(
    section: str, requirements: Sequence[Mapping[str, object]]
) -> tuple[RequirementCoverage, ...]:
    required_ids = _required_ids(requirements)
    table = parse_markdown_table(
        section, COVERAGE_HEADERS, table_name="Requirement coverage"
    )
    rows: list[RequirementCoverage] = []
    observed: set[str] = set()
    for values in table.rows:
        requirement_id = values["Requirement ID"]
        if requirement_id not in required_ids:
            raise _failure(
                f"Requirement coverage names unknown requirement '{requirement_id}'.",
                "Use only the REQ-NNN identifiers from run.json.",
            )
        if requirement_id in observed:
            raise _failure(
                f"Requirement '{requirement_id}' has duplicate coverage rows.",
                "Combine the status and evidence into one row.",
            )
        status = values["Status"].casefold().replace(" ", "_").replace("-", "_")
        if status not in COVERAGE_STATUSES:
            raise _failure(
                f"Requirement '{requirement_id}' has invalid coverage status.",
                "Use Covered, Partial, Missing, or Blocked.",
            )
        observed.add(requirement_id)
        rows.append(RequirementCoverage(requirement_id, status, values["Evidence"]))
    missing = [requirement_id for requirement_id in required_ids if requirement_id not in observed]
    if missing:
        raise _failure(
            "Review does not account for every request requirement.",
            "Add one coverage row with evidence for every REQ-NNN identifier.",
            missing_requirement_ids=missing,
        )
    return tuple(rows)


def _reconciliations(
    section: str,
    prior_finding_ids: Sequence[str],
    findings: Sequence[ReviewFinding],
) -> tuple[FindingReconciliation, ...]:
    prior = tuple(dict.fromkeys(prior_finding_ids))
    if not prior:
        if not _none(section):
            raise _failure(
                "Initial review contains prior-finding reconciliation rows.",
                "Use None when there is no earlier changes-requested review.",
            )
        return ()
    if _none(section):
        raise _failure(
            "Repair review does not reconcile prior findings.",
            "Account for every prior REV-NNN identifier as fixed, still present, superseded, or invalid.",
        )
    table = parse_markdown_table(
        section, RECONCILIATION_HEADERS, table_name="Repair guidance"
    )
    current = {finding.finding_id for finding in findings}
    rows: list[FindingReconciliation] = []
    observed: set[str] = set()
    for values in table.rows:
        finding_id = values["Finding ID"]
        if finding_id not in prior:
            raise _failure(
                f"Repair reconciliation names unknown prior finding '{finding_id}'.",
                "Use each finding ID from the immediately preceding review exactly once.",
            )
        if finding_id in observed:
            raise _failure(
                f"Prior finding '{finding_id}' is reconciled more than once.",
                "Keep one reconciliation row per prior finding.",
            )
        status = values["Status"].casefold().replace(" ", "_").replace("-", "_")
        if status not in RECONCILIATION_STATUSES:
            raise _failure(
                f"Prior finding '{finding_id}' has invalid reconciliation status.",
                "Use Fixed, Still present, Superseded, or Invalid.",
            )
        if status == "still_present" and finding_id not in current:
            raise _failure(
                f"Prior finding '{finding_id}' is still present but missing from Findings.",
                "Retain the stable finding ID in the current findings table.",
            )
        if status in {"fixed", "invalid"} and finding_id in current:
            raise _failure(
                f"Prior finding '{finding_id}' is both resolved and currently actionable.",
                "Either keep it as still present or remove it from current findings.",
            )
        if status == "superseded":
            replacements = {
                item for item in _FINDING_ID.findall(values["Evidence"]) if item != finding_id
            }
            if not replacements.intersection(current):
                raise _failure(
                    f"Superseded finding '{finding_id}' names no current replacement.",
                    "Cite the replacement REV-NNN identifier in the evidence cell.",
                )
        observed.add(finding_id)
        rows.append(FindingReconciliation(finding_id, status, values["Evidence"]))
    missing = [finding_id for finding_id in prior if finding_id not in observed]
    if missing:
        raise _failure(
            "Repair review does not account for every prior finding.",
            "Add one reconciliation row for every prior REV-NNN identifier.",
            missing_finding_ids=missing,
        )
    return tuple(rows)


def validate_review(
    text: str,
    run_id: str,
    requirements: Sequence[Mapping[str, object]],
    *,
    prior_finding_ids: Sequence[str] = (),
) -> ReviewArtifact:
    document = parse_frontmatter(text, expected_run_id=run_id, expected_stage="review")
    if document.metadata["status"] == "draft":
        raise _failure(
            "Review artifact is still a draft.",
            "Set its status to the final derived verdict after completing the evidence sections.",
        )
    if _TEMPLATE.search(document.body):
        raise _failure(
            "Review artifact still contains a placeholder marker.",
            "Replace every template value with concrete review evidence.",
        )
    sections = require_headings_in_order(
        document.body, REQUIRED_HEADINGS, artifact_name="Review"
    )
    verdict, _ = _verdict(sections["## Verdict"])
    if document.metadata["status"] != verdict:
        raise _failure(
            "Review frontmatter status does not match the Verdict section.",
            f'Set both values to "{verdict}".',
        )
    findings = _findings(sections["## Findings"])
    coverage = _coverage(sections["## Requirement coverage"], requirements)
    reconciliations = _reconciliations(
        sections["## Repair guidance"], prior_finding_ids, findings
    )
    blocking = [finding.finding_id for finding in findings if finding.blocking]
    uncovered = [row.requirement_id for row in coverage if row.status != "covered"]
    if verdict == "passed":
        if blocking:
            raise _failure(
                "Passed review contains blocking findings.",
                "Use changes_requested or remove findings only after they are demonstrably resolved.",
                blocking_finding_ids=blocking,
            )
        if uncovered:
            raise _failure(
                "Passed review does not demonstrate complete requirement coverage.",
                "Cover every requirement with concrete evidence before passing the run.",
                uncovered_requirement_ids=uncovered,
            )
    elif verdict == "changes_requested":
        if not blocking:
            raise _failure(
                "Changes-requested review has no blocking actionable finding.",
                (
                    "Add an evidence-backed blocking finding or use passed when only "
                    "nonblocking low findings remain."
                ),
            )
    else:
        blocker_text = "\n".join(
            (
                sections["## Verdict"],
                sections["## Verification assessment"],
                sections["## Residual risks"],
            )
        )
        if "blocker:" not in blocker_text.casefold():
            raise _failure(
                "Blocked review does not identify an evidence blocker.",
                (
                    "Record a 'Blocker:' statement naming the unavailable evidence or "
                    "indispensable verification."
                ),
            )
        if blocking:
            raise _failure(
                "Blocked review also contains actionable blocking findings.",
                (
                    "Use changes_requested for repairable findings; reserve blocked for "
                    "unavailable required evidence."
                ),
                blocking_finding_ids=blocking,
            )
    return ReviewArtifact(
        metadata=document.metadata,
        sections=sections,
        verdict=verdict,
        findings=findings,
        coverage=coverage,
        reconciliations=reconciliations,
    )
