# Stage 0: Architecture and Contracts

## Objective

Freeze the POC's architecture, terminology, trust boundaries, state model, and public interfaces before implementation. This prevents phase skills and harness adapters from inventing incompatible conventions.

## Dependencies

None.

## Deliverables

- `docs/architecture/poc.md`
- `docs/architecture/decisions/0001-artifact-driven-pipeline.md`
- `docs/architecture/decisions/0002-python-stdlib-cli.md`
- `docs/architecture/decisions/0003-canonical-agent-skills.md`
- `specromancy/contracts/pipeline.json`
- `specromancy/contracts/run.schema.json`
- `specromancy/contracts/artifact.schema.json`
- `specromancy/contracts/exit-codes.json`
- Initial terminology section in `README.md`

## Required decisions

### 1. Source-of-truth boundaries

Adopt the following ownership rules:

- `AGENTS.md` is the canonical always-on instruction file.
- `.agents/skills/<name>/` is the canonical skill source.
- `specromancy/contracts/` defines machine-enforced pipeline behavior.
- `specromancy/templates/` defines initial human-readable artifacts.
- Harness-specific files are generated adapters and must never contain unique workflow logic.
- `.specromancy/runs/<run-id>/` is the durable runtime state.
- Conversation history is never an authoritative input to a later phase.

### 2. POC execution model

The CLI coordinates work but does not invoke a model provider. A user or harness invokes a skill; the skill uses the CLI to start a phase, discovers declared inputs, authors the artifact or code change, validates it, and asks the CLI to complete the phase.

This split keeps the POC harness- and model-agnostic. Direct non-interactive harness runners may be added after the POC as optional adapters.

### 3. State machine

Define these durable statuses:

```text
initialized
research_in_progress
research_ready
plan_in_progress
plan_ready
plan_approved
implementation_in_progress
implementation_ready
review_in_progress
changes_requested
passed
blocked
cancelled
```

Required transition rules:

- Only `initialized` can begin research.
- Research completion requires a valid research artifact.
- Planning requires `research_ready`.
- Implementation requires both `plan_ready` and a recorded plan approval.
- Review requires `implementation_ready`.
- `changes_requested` can return only to implementation.
- `passed`, `blocked`, and `cancelled` are terminal for the POC.
- The implementation/review cycle is bounded by `max_review_cycles`, defaulting to 3.
- Re-running a completion command must be idempotent when inputs are unchanged.

### 4. Run manifest

Specify `run.json` with at least:

- `schema_version`
- `run_id`
- `title`
- `created_at` and `updated_at` in UTC
- `status`
- `current_phase`
- `repository_root`
- `git_base`
- `git_head`
- `artifacts`, including relative path, SHA-256 digest, and validation time
- `approvals`, including subject, approver, time, and artifact digest
- `review_cycle`
- `max_review_cycles`
- `last_error`
- append-only `events.jsonl` path

Do not store secrets, full prompts, access tokens, or provider credentials.

### 5. Artifact contract

Every Markdown artifact begins with portable YAML frontmatter containing only scalar values that the POC parser supports:

```yaml
---
schema-version: "1"
run-id: "20260920-example"
stage: "research"
status: "ready"
created-at: "2026-09-20T10:00:00Z"
---
```

The POC parser must reject duplicate keys, missing delimiters, unknown stage names, and mismatched run IDs. Phase-specific validators enforce required headings and structured tables.

### 6. Stable exit codes

Reserve and document:

| Code | Meaning |
|---:|---|
| 0 | Success |
| 2 | Invalid arguments or malformed input |
| 3 | Invalid state transition |
| 4 | Artifact or repository validation failed |
| 5 | Explicit approval required |
| 6 | External command failed |
| 7 | Safety or policy check rejected the operation |
| 8 | Run lock or concurrent modification conflict |

### 7. Trust and permission model

- Research: read repository and optional web sources; no repository writes outside its run artifact.
- Plan: read-only except its run artifact.
- Implement: repository writes permitted within the task scope.
- Review: read-only except its run artifact.
- Orchestrator: may update run metadata but may not silently bypass gates.
- Destructive commands, production changes, secrets access, and dependency additions require user approval.

Harness permissions can strengthen these rules but cannot weaken the canonical policy.

## Implementation tasks

1. Write the architecture overview with a component diagram and data-flow description.
2. Record the three initial architecture decisions and their rejected alternatives.
3. Write the state transition table in `pipeline.json`.
4. Define version `1` of the run and artifact schemas.
5. Define exit codes and error-envelope fields.
6. Specify atomic-write behavior: temporary file in the target directory, flush, then `os.replace`.
7. Specify locking: exclusive `run.lock` creation with owner metadata and a documented stale-lock recovery command.
8. Specify path safety: all resolved run and artifact paths must remain inside the repository root.
9. Add examples for a successful run, rejected transition, approval mismatch, and repair-loop exhaustion.
10. Review all contracts against the five target harnesses without adding harness-specific semantics.

## Validation

- Parse every JSON contract with the Python standard library.
- Check that every state except terminal states has at least one outbound transition.
- Check that every transition names a known phase and validator.
- Check that all documented exit codes are unique.
- Walk through one complete state sequence and one changes-requested sequence manually.

## Exit criteria

- All public vocabulary and state names are fixed for POC version 1.
- The state transition table has no ambiguous or implicit transitions.
- Artifact metadata and approval binding are fully specified.
- The CLI can be implemented without making new architectural decisions.
- Phase skill authors can identify exactly what they consume and produce.

## Risks and mitigations

- **Overdesign:** keep the contract local and single-repository; defer provider runners and remote state.
- **Markdown parsing ambiguity:** restrict frontmatter and validate required section headings rather than implementing general YAML.
- **Harness permission mismatch:** treat native permissions as optional enforcement, not pipeline semantics.
- **Schema churn:** add `schema_version` immediately and require decision records for breaking changes.

