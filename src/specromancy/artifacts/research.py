"""Contract validation for the evidence-backed research artifact."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final, Mapping
from urllib.parse import urlparse

from ..errors import SafetyError, ValidationError
from ..paths import RepositoryPaths
from .frontmatter import parse_frontmatter
from .markdown import parse_markdown_table, require_headings_in_order


REQUIRED_HEADINGS: Final = (
    "## Request interpretation",
    "## Repository map",
    "## Current behavior",
    "## Constraints and invariants",
    "## Evidence",
    "## Unknowns and assumptions",
    "## Risks",
    "## Planning inputs",
)
EVIDENCE_HEADERS: Final = ("Evidence ID", "Claim", "Source", "Location", "Confidence")
_PLACEHOLDER: Final = re.compile(r"\b(?:TODO|TBD)\b|\{\{[^}\n]+\}\}", re.IGNORECASE)
_ACCESS_DATE: Final = re.compile(r"\b(?:accessed\s+)?(20[0-9]{2}-[0-9]{2}-[0-9]{2})\b", re.I)
_ASSUMPTION: Final = re.compile(
    r"(?:\[assumption\]|\bassumption\s*:|\bwe\s+assume\s+)(.+)", re.IGNORECASE
)
_SECRET_PATTERNS: Final = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(
        r"\b(?:password|passwd|api[_-]?key|access[_-]?token|secret)\s*[:=]\s*[\"']?[^\s\"']{8,}",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class EvidenceRow:
    evidence_id: str
    claim: str
    source: str
    location: str
    confidence: str


@dataclass(frozen=True)
class ResearchArtifact:
    metadata: Mapping[str, str]
    sections: Mapping[str, str]
    evidence: tuple[EvidenceRow, ...]
    warnings: tuple[str, ...] = ()


def _failure(message: str, hint: str, **details: object) -> ValidationError:
    return ValidationError(message, hint=hint, details=details)


def _is_url(value: str) -> bool:
    parsed = urlparse(value.strip("`<>[]() "))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _extract_url(value: str) -> str | None:
    match = re.search(r"https?://[^\s<>|)]+", value)
    return match.group(0).rstrip(".,") if match else None


def _local_location(raw: str) -> tuple[str, int | None]:
    value = raw.strip().replace("`", "")
    line_number: int | None = None
    line_match = re.fullmatch(r"(.+?)(?::(?:L)?([0-9]+)(?:-[0-9]+)?|#L([0-9]+))?", value)
    if line_match is None:
        return value, None
    path = line_match.group(1).strip()
    raw_line = line_match.group(2) or line_match.group(3)
    if raw_line:
        line_number = int(raw_line)
    return path, line_number


def _line_from_location(value: str) -> int | None:
    match = re.search(r"(?:\blines?\s+|\bL)?([0-9]+)(?:-[0-9]+)?\b", value, re.I)
    return int(match.group(1)) if match else None


def _validate_local_evidence(
    paths: RepositoryPaths,
    row: EvidenceRow,
    warnings: list[str],
    *,
    source_is_kind: bool,
) -> None:
    if source_is_kind:
        serialized, line_number = _local_location(row.location)
    else:
        serialized, embedded_line = _local_location(row.source)
        line_number = _line_from_location(row.location) or embedded_line
    try:
        target = paths.resolve_relative(serialized)
    except (SafetyError, ValidationError) as exc:
        raise _failure(
            f"Evidence '{row.evidence_id}' uses an unsafe repository path.",
            "Use a repository-relative POSIX path with no '..' components.",
            evidence_id=row.evidence_id,
            location=row.location,
        ) from exc
    if not target.is_file():
        raise _failure(
            f"Evidence '{row.evidence_id}' cites a local file that does not exist.",
            "Correct the repository-relative location or remove the unsupported claim.",
            evidence_id=row.evidence_id,
            location=serialized,
        )
    if line_number is not None:
        try:
            with target.open("r", encoding="utf-8", errors="replace") as handle:
                line_count = sum(1 for _ in handle)
        except OSError as exc:
            raise _failure(
                f"Evidence '{row.evidence_id}' could not be checked.",
                "Make the cited local file readable and run validation again.",
                evidence_id=row.evidence_id,
            ) from exc
        if line_number > line_count:
            warnings.append(
                f"Evidence {row.evidence_id} cites line {line_number} in {serialized}, "
                f"which currently has {line_count} lines. The path remains valid."
            )


def _validate_external_evidence(row: EvidenceRow) -> None:
    combined = f"{row.source} {row.location}"
    url = _extract_url(combined)
    if url is None or not _is_url(url):
        raise _failure(
            f"External evidence '{row.evidence_id}' has no direct HTTP(S) URL.",
            "Cite a direct source URL in the Source or Location cell.",
            evidence_id=row.evidence_id,
        )
    access = _ACCESS_DATE.search(combined)
    if access is None:
        raise _failure(
            f"External evidence '{row.evidence_id}' has no access date.",
            "Add an access date in YYYY-MM-DD form to the Location cell.",
            evidence_id=row.evidence_id,
        )
    try:
        date.fromisoformat(access.group(1))
    except ValueError as exc:
        raise _failure(
            f"External evidence '{row.evidence_id}' has an invalid access date.",
            "Use a real calendar date in YYYY-MM-DD form.",
            evidence_id=row.evidence_id,
        ) from exc


def _check_assumptions(body: str, assumptions: str) -> None:
    body_without_section = body.replace(assumptions, "", 1)
    recorded = assumptions.casefold()
    for match in _ASSUMPTION.finditer(body_without_section):
        statement = match.group(1).strip(" -*.`").casefold()
        if statement and statement not in recorded:
            raise _failure(
                "A stated assumption is not recorded in the assumptions section.",
                (
                    "Copy every assumption into '## Unknowns and assumptions' "
                    "or rewrite it as evidence."
                ),
                assumption=statement[:160],
            )


def validate_research(text: str, repository_root: str | Path, run_id: str) -> ResearchArtifact:
    """Validate one completed research artifact and return its parsed content."""

    document = parse_frontmatter(
        text,
        expected_run_id=run_id,
        expected_stage="research",
        expected_status="ready",
    )
    body = document.body
    if _PLACEHOLDER.search(body):
        raise _failure(
            "Research artifact still contains a placeholder marker.",
            "Replace TODO, TBD, and template variables with findings or explicit unknowns.",
        )
    for pattern in _SECRET_PATTERNS:
        if pattern.search(body):
            raise _failure(
                "Research artifact contains a value that looks like a secret.",
                "Remove the value and summarize the sensitive configuration without copying it.",
            )

    sections = require_headings_in_order(body, REQUIRED_HEADINGS)
    table = parse_markdown_table(
        sections["## Evidence"], EVIDENCE_HEADERS, table_name="Evidence"
    )
    evidence: list[EvidenceRow] = []
    identifiers: set[str] = set()
    repository_count = 0
    warnings: list[str] = []
    paths = RepositoryPaths(Path(repository_root))
    for values in table.rows:
        row = EvidenceRow(
            evidence_id=values["Evidence ID"],
            claim=values["Claim"],
            source=values["Source"],
            location=values["Location"],
            confidence=values["Confidence"],
        )
        if re.fullmatch(r"E-[0-9]{3,}", row.evidence_id) is None:
            raise _failure(
                f"Evidence ID '{row.evidence_id}' is malformed.",
                "Use stable IDs such as E-001, E-002, and E-003.",
            )
        if row.evidence_id in identifiers:
            raise _failure(
                f"Evidence ID '{row.evidence_id}' is duplicated.",
                "Give every evidence row a unique stable ID.",
            )
        identifiers.add(row.evidence_id)
        if row.confidence.casefold() not in {"low", "medium", "high"}:
            raise _failure(
                f"Evidence '{row.evidence_id}' has an unknown confidence value.",
                "Use Low, Medium, or High and explain uncertainty in the artifact prose.",
            )
        source_kind = row.source.strip().casefold()
        if source_kind in {"repository", "repo", "local", "codebase"}:
            repository_count += 1
            _validate_local_evidence(paths, row, warnings, source_is_kind=True)
        elif _extract_url(f"{row.source} {row.location}") is not None or source_kind in {
            "external",
            "web",
        }:
            _validate_external_evidence(row)
        else:
            repository_count += 1
            _validate_local_evidence(paths, row, warnings, source_is_kind=False)
        evidence.append(row)
    if repository_count == 0:
        raise _failure(
            "Research artifact contains no repository evidence.",
            (
                "Add at least one row with a repository-relative Source path, or use "
                "Repository as Source and put the path in Location."
            ),
        )

    _check_assumptions(body, sections["## Unknowns and assumptions"])
    planning = sections["## Planning inputs"].casefold()
    for label in ("affected areas", "acceptance criteria gaps", "recommended verification"):
        if label not in planning:
            raise _failure(
                f"Planning inputs do not identify {label}.",
                f"Add an explicit '{label.title()}:' entry under '## Planning inputs'.",
            )

    return ResearchArtifact(
        metadata=document.metadata,
        sections=sections,
        evidence=tuple(evidence),
        warnings=tuple(warnings),
    )


# A descriptive alias reads naturally at call sites and keeps a stable public hook.
validate_research_artifact = validate_research
validate = validate_research
