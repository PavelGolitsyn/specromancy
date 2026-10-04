# Stage 15 — Verify integration and hand off deferred work

Status: planned. Prerequisites: stages 09–14.
Category: integration, documentation, and release evidence.

## Objective

Verify the follow-on boundaries as one system, show exactly which behaviors
changed, and leave a usable record for future work. Each earlier stage must
already have passed its own checks; this stage is not a substitute for them.

## Work sequence and files

1. Replay the original compatibility fixtures through the final code using
   `test_compatibility.py`. Continue restored pending, active, granted, paused,
   terminal, and recoverable runs. Sequential bytes, hashes, packets, and
   diagnostics must still match their unchanged captures.
2. Review Stage 13 overlap traces and Stage 14 malformed-status diagnostics as
   the only intended behavior corrections. Link each difference to its test and
   public-contract description; investigate any additional change.
3. Audit imports and responsibility ownership. Field parsing must not depend on
   engine/storage; visit preparation may read resources but not persist; pure
   approvals/transitions must not perform IO; services must not import Engine;
   persistence must remain independent of CLI responses and workflow phase names.
4. Confirm facade imports, error identity, injected clocks/fault points, source
   export, and standard-library-only execution still work. Remove abandoned
   duplicate implementations, retaining compatibility delegates that are required.
5. Update `docs/poc-v3/architecture.md`, `contracts.md`, `cli.md` where relevant,
   and `tests/README.md`. Describe actual code and behavior, not proposed modules
   that were omitted during implementation.
6. Record exact interpreter versions, commands, results, and changed paths here.
   Mark completed stage checklists and update the refactoring index. Preserve
   earlier evidence and explicitly document any skipped or revised scope.

## Final verification

```sh
python -m unittest discover -s tests/features -t .
python -m unittest discover -s tests/shipped_configuration -t .
python -m unittest discover
bin/specromancy adapters generate --check
git diff --check
git status --short
```

Run the full suite on Python 3.11 and the available development Python. Put the
selected interpreter's directory first on PATH so subprocess `python3` launchers
exercise the same version. Use an available `python3` spelling when necessary;
record unavailable interpreters as unverified. Do not install new dependencies
or claim historical test results apply to changed code. If split groups already
passed for the final unchanged revision, avoid repeating them unnecessarily.

Generated adapters should remain byte-identical because this plan does not
change their canonical inputs or metadata. A drift failure must be investigated,
not fixed by blindly regenerating. Keep generation experiments in temporary
fixture repositories and review ownership behavior there.

## Deferred investigations and completion boundaries

These items are not implicitly included as implementation work in stages 09–15.
Each requires a separate scoped design after collecting the listed evidence.

| Follow-up | Current evidence | Required investigation and decision |
| --- | --- | --- |
| Validation evidence across edits | `perform_validation` observes files/commands/mutation state outside the store commit lock; the closeout calls the race unverified | Deterministically edit output/repository after validation but before transition; establish whether validated bytes differ from sealed bytes. Compare revision/hash preconditions and revalidation approaches; a run lock alone does not prevent external edits. Define retry/event behavior before implementing. |
| Interrupted initialization | `test_create_faults_leave_request_and_do_not_clean_up_partial_run`; creation and first preparation are separate commits | Enumerate directory-only, request-only, manifest/event-gap, and revision-1-without-visit states. Define recoverable versus corrupt states, idempotent continuation, and path ownership without deleting artifacts, guessing user intent, or rewriting events. |
| Strong nested record validation | Stage 14 matrix and deliberately permissive version-1 tests | Decide accepted old-run behavior and schema/version policy; define controlled diagnostics for each tightened invariant. No opportunistic loader/schema replacement. |
| Broader engine callback interleavings | This plan only hardens approval operations | Characterize stale validation-evidence writes, block decisions, and command-log overlap before claiming command-level concurrency safety. Scope each demonstrated issue separately. |

## Completion record to fill during execution

| Gate | Evidence required | Result |
| --- | --- | --- |
| Minimum Python | Version, full-suite count/result, matching launcher PATH | Pending |
| Development Python | Version and full-suite count/result | Pending |
| Compatibility | Original fixture replay, facade/import checks | Pending |
| Intentional corrections | Approval interleavings and malformed-status cases | Pending |
| Durability and safety | Recovery/fault tests, ownership and immutable-artifact tests | Pending |
| Adapters | Check mode and deterministic fixture generation | Pending |
| Documentation and scope | Final module map, behavior changes, reviewed diff | Pending |

## Exit criteria and rollback

- [ ] All required gates pass for the final code, with limitations stated honestly.
- [ ] Structural changes are distinguishable from the two intentional corrections.
- [ ] Runtime remains generic, dependency-free, and Python 3.11 compatible.
- [ ] No unrelated workflow, generated, or repository content changed.
- [ ] Deferred investigations have evidence and decision criteria, not vague TODOs.

Rollback is a normal reviewed code change to the smallest responsible stage.
Do not stage, commit, reset, delete repository work, or rewrite user run artifacts
as a side effect of validation. The preserved formats allow old runs to remain
readable without a rollback migration.
