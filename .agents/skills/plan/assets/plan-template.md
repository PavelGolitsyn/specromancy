---
schema-version: "1"
run-id: "{{ run_id }}"
stage: "plan"
status: "draft"
created-at: "{{ created_at }}"
---

## Outcome

{{ State the observable result this plan will deliver. }}

## Scope

{{ Define included work and explicit exclusions. }}

## Requirements traceability

| Requirement ID | Evidence IDs | Planned changes | Verification |
| --- | --- | --- | --- |
| REQ-001 | E-001 | CHG-001 | {{ observable check, test, or inspection }} |

## Proposed changes

| Change ID | Action | Path | Description | Approval-sensitive |
| --- | --- | --- | --- | --- |
| CHG-001 | modify | {{ existing/repository/path }} | {{ file or interface-level action }} | No |

## Data and interface changes

{{ Describe data, schema, CLI, API, and compatibility effects, or state None. }}

## Verification strategy

{{ Map focused and regression checks to expected outcomes. }}

## Rollout and rollback

{{ Describe safe adoption and reversal, or explain why no rollout is needed. }}

## Risks and mitigations

{{ Pair each material risk with a mitigation. }}

## Open decisions

None.

## Implementation sequence

1. {{ Implement CHG-001 and its tests. }}
2. {{ Run the focused checks, then the approved broader verification. }}
