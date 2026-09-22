"""Small deterministic helpers for phase-specific Markdown contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from ..errors import ValidationError


@dataclass(frozen=True)
class MarkdownTable:
    headers: tuple[str, ...]
    rows: tuple[Mapping[str, str], ...]


def _failure(message: str, hint: str) -> ValidationError:
    return ValidationError(message, hint=hint)


def require_headings_in_order(
    body: str,
    required: Sequence[str],
    *,
    artifact_name: str = "Research",
) -> dict[str, str]:
    """Return required section bodies after checking uniqueness and order."""

    lines = body.splitlines()
    locations: dict[str, int] = {}
    for heading in required:
        matches = [index for index, line in enumerate(lines) if line == heading]
        if not matches:
            raise _failure(
                f"{artifact_name} artifact is missing required heading '{heading}'.",
                f"Add '{heading}' once in the documented section order.",
            )
        if len(matches) != 1:
            raise _failure(
                f"{artifact_name} artifact repeats required heading '{heading}'.",
                f"Keep exactly one '{heading}' section.",
            )
        locations[heading] = matches[0]
    positions = [locations[heading] for heading in required]
    if positions != sorted(positions):
        raise _failure(
            f"{artifact_name} artifact headings are out of order.",
            f"Reorder the required sections to match the {artifact_name.casefold()} template.",
        )

    sections: dict[str, str] = {}
    for heading in required:
        start = locations[heading] + 1
        end = len(lines)
        for index in range(start, len(lines)):
            if re.match(r"^##\s+", lines[index]):
                end = index
                break
        value = "\n".join(lines[start:end]).strip()
        if not value:
            raise _failure(
                f"{artifact_name} section '{heading}' is empty.",
                "Add grounded content or explicitly record that the item is unknown.",
            )
        sections[heading] = value
    return sections


def parse_markdown_table(
    section: str,
    expected_headers: Sequence[str],
    *,
    table_name: str,
) -> MarkdownTable:
    """Parse one pipe table without attempting to interpret general Markdown."""

    table_lines = [line.strip() for line in section.splitlines() if line.strip().startswith("|")]
    if len(table_lines) < 3:
        raise _failure(
            f"{table_name} table is missing or has no data rows.",
            f"Add a pipe table with headers: {', '.join(expected_headers)}.",
        )

    def cells(line: str) -> list[str]:
        if not line.endswith("|"):
            raise _failure(
                f"{table_name} table row is malformed.",
                "Start and end every table row with | and keep the column count stable.",
            )
        return [cell.strip() for cell in line[1:-1].split("|")]

    headers = cells(table_lines[0])
    expected = [header.casefold() for header in expected_headers]
    if [header.casefold() for header in headers] != expected:
        raise _failure(
            f"{table_name} table has unexpected columns.",
            f"Use these columns in order: {', '.join(expected_headers)}.",
        )
    separator = cells(table_lines[1])
    if len(separator) != len(headers) or any(
        re.fullmatch(r":?-{3,}:?", cell) is None for cell in separator
    ):
        raise _failure(
            f"{table_name} table separator is malformed.",
            "Use at least three dashes beneath every table header.",
        )
    rows: list[Mapping[str, str]] = []
    for line in table_lines[2:]:
        values = cells(line)
        if len(values) != len(headers):
            raise _failure(
                f"{table_name} table row has the wrong number of cells.",
                f"Provide exactly {len(headers)} nonempty cells in every row.",
            )
        if any(not value or value in {"-", "—"} for value in values):
            raise _failure(
                f"{table_name} table contains an empty template row.",
                "Fill every cell or remove the unused row.",
            )
        rows.append(dict(zip(expected_headers, values)))
    return MarkdownTable(tuple(expected_headers), tuple(rows))


# Stable descriptive aliases for phase validators that prefer verb-oriented names.
validate_heading_order = require_headings_in_order
parse_table_rows = parse_markdown_table
