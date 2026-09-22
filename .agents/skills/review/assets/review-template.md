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

<!-- For actionable findings, replace None with:
| Finding ID | Severity | Blocking | Title | Location | Observed | Expected | Impact | Repair guidance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| REV-001 | Medium | Yes | Concise title | path/to/file.py:42 | Observed behavior. | REQ-001 requires expected behavior. | Concrete impact or reproduction reasoning. | Minimal repair. |
-->

## Requirement coverage

| Requirement ID | Status | Evidence |
| --- | --- | --- |
| REQ-001 | Covered | {{ Concrete diff, artifact, or verification evidence. }} |

## Verification assessment

{{ Distinguish author-recorded command results from checks re-run by the reviewer. For a blocked review, include `Blocker:` and name the missing indispensable evidence. }}

## Residual risks

{{ Record non-actionable risks, open questions, and any reduced independence. Use None when there are none. }}

## Repair guidance

None.

<!-- In a repair review, replace None with:
| Finding ID | Status | Evidence |
| --- | --- | --- |
| REV-001 | Fixed | Concrete evidence that the repair resolves the finding. |
-->
