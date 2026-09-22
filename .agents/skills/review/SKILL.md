---
name: review
description: Independently review a completed Specromancy implementation against its durable request, research, approved plan, actual repository diff, and verification evidence without modifying source files.
---

# Review

Review the current implementation subject independently and leave a deterministic, evidence-backed verdict that can be consumed without chat history.

## Inputs

- Active Specromancy run ID and `run.json`.
- Current request, research, approved plan, and implementation artifacts.
- Repository diff and verification records bound by the implementation artifact.
- Immediately preceding review when this is a repair cycle.

## Output

- Validated `.specromancy/runs/<run-id>/review.md`.
- A run transitioned to `passed`, `changes_requested`, or `blocked` with the reviewed diff digest still current.

## Procedure

1. Prefer a fresh context or an independent agent when the harness supports it. Do not preload the implementation skill into the reviewer context.
2. Run `specromancy phase start <run-id> review`. Stop if required artifacts are stale, the implementation subject changed, or another writer owns the run lock.
3. Read this skill's `references/review-policy.md`, the request, research, approved plan, and applicable repository instructions.
4. Inspect the actual repository diff before reading the implementation summary in detail. Treat the implementation handoff as a claim to verify, not as evidence by itself.
5. Check correctness, regressions, security, data handling, compatibility, tests, and documentation in proportion to the change. Map observed behavior to every `REQ-NNN` requirement.
6. Inspect recorded verification and re-run focused checks when feasible. Clearly distinguish newly observed results from author-recorded results.
7. Do not modify repository source, tests, documentation, configuration, generated files, or command records. Only the active run's `review.md` may be authored during review. If a code change is needed, record a finding.
8. Copy `assets/review-template.md` to the review artifact path. Record actionable findings in severity order with stable `REV-NNN` IDs and concrete evidence. Put questions and non-actionable uncertainty in residual risks.
9. For a repair review, re-check repaired and adjacent behavior and reconcile every prior finding as `Fixed`, `Still present`, `Superseded`, or `Invalid`. Retain the original ID for a still-present finding.
10. Derive the verdict from the policy, replace every placeholder, set frontmatter status to the same verdict, and run `specromancy validate <run-id> review`.
11. Run `specromancy phase complete <run-id> review`. Completion rechecks every artifact digest, the reviewed diff digest, reviewer write scope, finding consistency, and requirement coverage immediately before transition.

If indispensable evidence cannot be inspected or re-created, use `blocked`, name the limitation with a `Blocker:` statement, and do not guess. A single-context review must disclose its reduced independence in residual risks, but that limitation alone does not force a blocked verdict.

Harness adapters may strengthen isolation with read-only filesystem permissions or a dedicated reviewer agent. Those controls supplement this procedure; they do not replace the CLI's digest and mutation checks.
