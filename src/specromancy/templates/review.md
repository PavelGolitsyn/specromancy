---
schema-version: "1"
run-id: "{{ run_id }}"
stage: "review"
status: "draft"
created-at: "{{ created_at }}"
---

## Verdict

{{ passed, changes_requested, or blocked }}

{{ For blocked only, explain the unavailable evidence. }}

## Findings

None.

## Requirement coverage

| Requirement ID | Status | Evidence |
| --- | --- | --- |
| REQ-001 | Covered | {{ Concrete diff, artifact, or verification evidence. }} |

## Verification assessment

{{ Distinguish recorded results from checks re-run by the reviewer. }}

## Residual risks

None.

## Repair guidance

None.
