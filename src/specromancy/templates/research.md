---
schema-version: "1"
run-id: "{{ run_id }}"
stage: "research"
status: "draft"
created-at: "{{ created_at }}"
---

## Request interpretation

{{ Interpret the requested outcome, known acceptance criteria, and scope. }}

## Repository map

{{ List only relevant areas and explain why each matters. }}

## Current behavior

{{ Describe observed behavior and reference evidence IDs. }}

## Constraints and invariants

{{ Record applicable instructions, compatibility boundaries, and invariants. }}

## Evidence

| Evidence ID | Claim | Source | Location | Confidence |
| --- | --- | --- | --- | --- |
| E-001 | {{ supported claim }} | {{ relative/path.py }} | line {{ line number }} | High |

## Unknowns and assumptions

{{ Record unresolved questions and every assumption. Use "None" if fully resolved. }}

## Risks

{{ Record research and planning risks. }}

## Planning inputs

- Affected areas: {{ files, packages, or interfaces }}
- Acceptance criteria gaps: {{ missing or ambiguous criteria, or None }}
- Recommended verification: {{ focused checks and broader regression checks }}
