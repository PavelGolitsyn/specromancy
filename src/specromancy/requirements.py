"""Deterministic request requirement extraction for run initialization."""

from __future__ import annotations

import re
from typing import TypedDict

from .artifacts.frontmatter import parse_frontmatter
from .io import normalized_text


class RequirementRecord(TypedDict):
    id: str
    text: str
    source: str


_ACCEPTANCE_HEADING = re.compile(
    r"^##\s+(?:acceptance criteria|requirements)\s*$", re.IGNORECASE
)
_GOAL_HEADING = re.compile(r"^##\s+(?:goal|outcome|request)\s*$", re.IGNORECASE)
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]\s+(?:\[[ xX]\]\s*)?|[0-9]+[.)]\s+)(.+?)\s*$")


def _body(request_text: str) -> str:
    content = normalized_text(request_text)
    if content.startswith("---\n"):
        return parse_frontmatter(
            content, expected_stage="request", expected_status="ready"
        ).body
    return content


def _section(lines: list[str], heading: re.Pattern[str]) -> list[str]:
    start: int | None = None
    result: list[str] = []
    for index, line in enumerate(lines):
        if start is None:
            if heading.fullmatch(line.strip()):
                start = index + 1
            continue
        if line.startswith("## "):
            break
        result.append(line)
    return result


def _paragraph(lines: list[str]) -> str | None:
    parts: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if parts:
                break
            continue
        if stripped.startswith("#"):
            continue
        match = _LIST_ITEM.fullmatch(stripped)
        parts.append(match.group(1) if match else stripped)
    value = " ".join(parts).strip()
    return value or None


def extract_requirements(request_text: str) -> tuple[RequirementRecord, ...]:
    """Assign stable IDs to explicit criteria, or fall back to the request goal."""

    lines = _body(request_text).splitlines()
    criteria = []
    for line in _section(lines, _ACCEPTANCE_HEADING):
        match = _LIST_ITEM.fullmatch(line)
        if match:
            criterion = match.group(1).strip()
            if criterion:
                criteria.append(criterion)
    if criteria:
        return tuple(
            {
                "id": f"REQ-{index:03d}",
                "text": text,
                "source": "explicit_acceptance_criterion",
            }
            for index, text in enumerate(criteria, start=1)
        )

    goal_lines = _section(lines, _GOAL_HEADING)
    goal = _paragraph(goal_lines) if goal_lines else _paragraph(lines)
    if goal is None:
        raise ValueError("Request contains no goal or acceptance criterion to initialize.")
    return ({"id": "REQ-001", "text": goal, "source": "request_goal"},)
