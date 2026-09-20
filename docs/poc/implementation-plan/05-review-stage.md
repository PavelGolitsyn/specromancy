# Stage 5: Review Stage

## Objective

Implement an independent review phase that compares the actual diff with the request, research, approved plan, and verification evidence, then returns evidence-backed findings and a deterministic verdict.

## Dependencies

- Stage 0 review states and repair-loop contract.
- Stage 1 foundation.
- Stage 4 changed-file and verification records.

## Deliverables

- `.agents/skills/review/SKILL.md`
- `.agents/skills/review/references/review-policy.md`
- `.agents/skills/review/assets/review-template.md`
- `src/specromancy/phases/review.py`
- `src/specromancy/artifacts/review.py`
- `specromancy/templates/review.md`
- `tests/contract/test_review_artifact.py`
- `tests/evals/review/`

## Input and output contract

Inputs:

- Request, research, approved plan, and implementation artifacts.
- Current repository diff relative to the recorded baseline.
- Verification command results.
- Prior review artifact when reviewing a repair cycle.

Output:

- `.specromancy/runs/<run-id>/review.md`

Required sections:

1. `## Verdict`
2. `## Findings`
3. `## Requirement coverage`
4. `## Verification assessment`
5. `## Residual risks`
6. `## Repair guidance`

Allowed verdicts:

- `passed`
- `changes_requested`
- `blocked`

## Finding contract

Each actionable finding has:

- stable ID such as `REV-001`;
- severity: `critical`, `high`, `medium`, or `low`;
- concise title;
- file and line or another precise location;
- observed behavior;
- expected behavior tied to a requirement, plan item, or repository invariant;
- impact and reproduction or reasoning;
- minimal repair guidance.

Do not create findings for personal style preferences already accepted by repository conventions. Questions and residual risks that do not justify code changes belong outside the findings table.

## Skill behavior

The review skill must:

1. Prefer execution in a fresh context or independent agent when the harness supports it.
2. Verify artifact digests and transition to `review_in_progress`.
3. Inspect the actual diff before reading the implementation author's summary in detail.
4. Check correctness, regressions, security, data handling, compatibility, tests, and documentation in proportion to the change.
5. Map actual behavior back to every request requirement.
6. Re-run focused verification when feasible; distinguish observed results from recorded results.
7. Avoid modifying repository code.
8. Write findings in severity order with evidence.
9. Validate `review.md` and derive the verdict from its contents.
10. Transition to `passed`, `changes_requested`, or `blocked`.

Verdict rules:

- Any `critical`, `high`, or `medium` actionable finding results in `changes_requested`.
- Low findings may coexist with `passed` only when explicitly nonblocking.
- Inability to inspect required evidence or run indispensable verification results in `blocked`, not `passed`.
- No-findings text is valid only when requirement coverage and verification assessment are complete.

## Independence safeguards

- Review instructions must not preload the implement skill.
- Native harness adapters should deny edits to a dedicated reviewer where the harness supports permissions.
- The canonical workflow must still work in one conversation by explicitly switching to read-only review behavior.
- Review completion captures a fresh diff digest so later code modifications invalidate the verdict.
- A prior review does not suppress re-checking repaired areas and adjacent regression risks.

## Validator behavior

The review validator checks:

- required artifact and diff digests match current state;
- verdict is one of the allowed values;
- finding IDs are unique and stable within a run;
- every actionable finding has severity, location, expectation, impact, and repair guidance;
- findings are ordered by severity;
- every requirement has a coverage status and evidence;
- verdict agrees with findings and blockers;
- a repair review accounts for every prior blocking finding as fixed, still present, superseded, or invalid;
- reviewer made no repository changes outside the run artifact.

## Implementation tasks

1. Define severity semantics and verdict derivation in the review policy.
2. Implement finding-table and requirement-coverage parsers.
3. Create the review template and canonical skill.
4. Implement review start and completion handlers.
5. Compute and bind the reviewed diff digest.
6. Detect repository mutation during review.
7. Implement prior-finding reconciliation for repair cycles.
8. Add transition logic for passed, changes requested, and blocked.
9. Add precise error messages for inconsistent verdicts.
10. Document how harness adapters may strengthen reviewer isolation.

## Tests and evaluations

Contract tests:

- passed review with no findings;
- medium finding paired with an invalid passed verdict;
- missing finding location;
- duplicate finding ID;
- incomplete requirement coverage;
- blocked review with missing evidence;
- diff changed after review;
- repository mutation during review;
- repaired and unresolved prior findings;
- maximum review-cycle boundary.

Behavioral evaluations:

- correct small change that should pass;
- change with subtle acceptance-criteria omission;
- change with security regression;
- change with misleading implementation summary;
- repair that fixes the symptom but introduces a regression;
- false-positive style complaint not grounded in instructions.

Measure true-positive coverage, false-positive rate, evidence precision, requirement coverage, and verdict consistency.

## Exit criteria

- Review verdicts are derived from validated evidence rather than free-form prose.
- A code change after review invalidates the previous verdict.
- Review performs no source mutation.
- Repair cycles retain stable finding identity and history.
- A passed run demonstrates coverage of every declared requirement.

## Risks and mitigations

- **Reviewer anchoring:** inspect the diff before relying on the implementation summary and prefer fresh context.
- **Review theater:** require requirement coverage and verification evidence even when there are no findings.
- **Excessive false positives:** demand concrete impact and repository-grounded expectations.
- **Self-review limitations:** document reduced independence when only a single context is available rather than pretending isolation.

