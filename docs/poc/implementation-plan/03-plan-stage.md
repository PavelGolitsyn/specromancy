# Stage 3: Plan Stage

## Objective

Implement a planning phase that converts approved research into a reviewable, testable change plan with explicit requirement traceability, file-level actions, risks, and approval binding.

## Dependencies

- Stage 0 contracts.
- Stage 1 foundation.
- Stage 2 frontmatter and artifact helpers.

## Deliverables

- `.agents/skills/plan/SKILL.md`
- `.agents/skills/plan/references/plan-quality.md`
- `.agents/skills/plan/assets/plan-template.md`
- `src/specromancy/phases/plan.py`
- `src/specromancy/artifacts/plan.py`
- `specromancy/templates/plan.md`
- `tests/contract/test_plan_artifact.py`
- `tests/evals/plan/`

## Input and output contract

Inputs:

- Validated `request.md`.
- Validated `research.md` whose digest matches `run.json`.
- Current repository state.

Output:

- `.specromancy/runs/<run-id>/plan.md`

Required sections:

1. `## Outcome`
2. `## Scope`
3. `## Requirements traceability`
4. `## Proposed changes`
5. `## Data and interface changes`
6. `## Verification strategy`
7. `## Rollout and rollback`
8. `## Risks and mitigations`
9. `## Open decisions`
10. `## Implementation sequence`

The traceability table maps stable requirement IDs to evidence IDs, planned changes, and verification. Proposed changes identify intended files or explicitly state that a file will be created.

## Skill behavior

The plan skill must:

1. Refuse to plan from unvalidated or stale research.
2. Transition the run to `plan_in_progress`.
3. Re-inspect only repository areas needed to verify research claims.
4. Translate every acceptance criterion into one or more verification steps.
5. Identify migrations, compatibility concerns, generated files, and documentation updates.
6. Describe changes at file and interface level without writing implementation code.
7. Make open decisions explicit and mark blocking ones.
8. Prefer the smallest coherent implementation that meets the request.
9. Write and validate `plan.md`.
10. Complete as `plan_ready`; never self-approve the plan.

## Approval contract

`specromancy approve <run-id> plan --by <identity>` must:

- require status `plan_ready`;
- validate the plan immediately before approval;
- record the plan SHA-256 digest, approver identity, UTC timestamp, and optional note;
- transition to `plan_approved`;
- be idempotent for the same approver and digest;
- reject approval reuse if `plan.md` changes afterward;
- avoid interpreting an agent's prose as approval.

For the POC, identity is user-provided and auditable but not cryptographically authenticated.

## Validator behavior

The plan validator checks:

- valid frontmatter and correct run binding;
- matching research digest;
- required headings and nonempty implementation sequence;
- every request requirement has a traceability row;
- every traceability row has at least one verification method;
- proposed existing files resolve inside the repository;
- new files are explicitly marked `create`;
- destructive operations, new dependencies, schema migrations, public API changes, and production actions are labeled as approval-sensitive;
- open blocking decisions prevent approval;
- no code blocks contain purported full implementation patches.

## Implementation tasks

1. Define stable requirement-ID extraction or generation during run initialization.
2. Implement parsing and validation for traceability and proposed-change tables.
3. Create the plan template, quality checklist, and canonical skill.
4. Implement plan phase start and completion handlers.
5. Implement explicit approval storage and digest comparison.
6. Add a stale-plan check used by every implementation entry point.
7. Add a command to revoke approval when the plan changes or the user requests replanning.
8. Append plan and approval events without rewriting prior events.
9. Produce actionable error messages that identify missing requirement IDs or verification rows.
10. Document the difference between a blocking decision and a nonblocking assumption.

## Tests and evaluations

Contract tests:

- valid plan with complete traceability;
- missing requirement mapping;
- verification omitted for one requirement;
- invalid existing path;
- unmarked new file;
- blocking decision still open;
- approval before validation;
- artifact modification after approval;
- repeated identical approval;
- approval revocation.

Behavioral evaluations:

- narrowly scoped bug fix;
- cross-cutting feature requiring docs and tests;
- database migration with rollback concerns;
- request with unresolved product choice;
- plan that could be over-engineered.

Score completeness, minimality, testability, traceability, risk recognition, and absence of implementation edits.

## Exit criteria

- Every requirement is visibly linked to planned work and verification.
- Implementation cannot start without digest-bound approval.
- Blocking decisions prevent approval rather than becoming silent assumptions.
- The plan is usable by an implementation agent with no access to prior chat history.
- Replanning and approval revocation have defined, tested behavior.

## Risks and mitigations

- **False precision:** allow directory or component targets when exact files cannot be known, but require an explanation and discovery step.
- **Plans that merely restate research:** require concrete file/interface actions and verification commands.
- **Approval ambiguity:** only the CLI approval record counts.
- **Plan drift during implementation:** compare the approved digest before every implementation or repair cycle.

