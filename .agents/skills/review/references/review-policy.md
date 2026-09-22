# Review policy

## Evidence and independence

The repository diff, durable phase artifacts, and recorded or newly observed command results are evidence. The implementation summary is not authoritative. Inspect the diff first, then use the handoff to identify claims that require confirmation.

Review is read-only outside the active run's `review.md`. Do not repair code, update tests, reformat files, regenerate outputs, or alter verification records. A repository mutation during review invalidates the subject and must be resolved through a fresh implementation boundary.

## Severity semantics

- `critical`: exploitation, irreversible data loss, or systemic failure is likely or already demonstrated.
- `high`: a core requirement is absent or a serious security, correctness, compatibility, or data-handling regression exists.
- `medium`: a material requirement, edge case, or regression is incorrect and warrants repair before acceptance.
- `low`: a concrete but limited defect with small impact; personal style preferences are not findings.

Critical, high, and medium findings are always blocking. A low finding may be explicitly nonblocking when accepting it does not violate a request requirement, approved plan item, or repository invariant.

Every finding must state a stable ID, severity, blocking status, title, precise location, observed behavior, grounded expected behavior, impact or reproduction reasoning, and minimal repair guidance. Ground expectations in a `REQ-NNN`, `CHG-NNN`, contract, policy, or repository invariant.

## Verdict derivation

- `changes_requested`: one or more blocking actionable findings exist. Any critical, high, or medium finding requires this verdict.
- `passed`: there are no blocking findings, every requirement is covered with evidence, and indispensable verification evidence is available. Explicitly nonblocking low findings may remain.
- `blocked`: the reviewer cannot inspect required evidence or run indispensable verification. Record the unavailable evidence with a `Blocker:` statement. Do not use blocked for a repairable code defect.

No-findings text is valid only when every requirement has a coverage row and the verification assessment distinguishes recorded evidence from newly observed checks.

## Repair review

Re-check each prior finding and adjacent regression risks. Reconcile every prior ID:

- `Fixed`: the current subject resolves the finding; cite evidence.
- `Still present`: the defect remains and the current findings table retains the same ID.
- `Superseded`: a better-scoped current finding replaces it; cite the replacement `REV-NNN`.
- `Invalid`: repository-grounded evidence demonstrates that the prior expectation did not apply.

Never renumber a still-present finding or mark a finding invalid merely to avoid repair.

## Requirement coverage

Use `Covered`, `Partial`, `Missing`, or `Blocked`. Evidence should identify concrete diff locations, artifact statements, command records, or newly observed results. A passed review requires every requirement to be `Covered`.

Questions, assumptions, reduced reviewer independence, and risks that do not justify a code change belong in `Residual risks`, not the findings table.
