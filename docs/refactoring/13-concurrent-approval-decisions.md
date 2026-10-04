# Stage 13 — Handle concurrent approval decisions under the run lock

Status: planned. Prerequisite: Stage 12.
Category: explicit behavior correction, delivered separately from extraction.
Risk: incorrect approval binding, duplicate events, or stale advancement.

## Evidence and intended behavior

`test_overlap_before_approval_grant_exposes_existing_assertion` demonstrates a
second command completing before the first command reaches its grant callback.
The callback then calls `granted_state` with no pending record and asserts.
The winning state is intact, but the losing command lacks a controlled result.
Replace that failure with an explicit decision against current locked state.

Scope includes request/grant/invalidation callbacks involved in this approval
lifecycle, because selecting the latest record from an old observation can target
a replacement request. It does not claim to make external file edits atomic with
validation or solve every engine interleaving.

## Files and design

- `approvals.py`: pure decisions returning changed state, explicit no-op, or a
  controlled conflict. Inputs include the observed approval binding.
- `run_store.py`: a narrow internal approval-decision entry point that loads and
  decides under one run lock, then uses the existing commit protocol.
- `approval_service.py`: translates decision outcomes into existing public
  response families; performs continuation only from returned current state.
- `test_visit_transition_store.py`, `test_engine_orchestration.py`, and
  `test_compatibility.py`: deterministic interleavings and sequential replay.
- `docs/poc-v3/contracts.md`: document new conflict/idempotency semantics.

Do not change general `RunStore.mutate`: it intentionally commits even when its
callback leaves data unchanged. The new approval operation needs an explicit
no-op result so duplicate decisions do not manufacture an audit event.

## Proposed decision table

Finalize exact diagnostic text in Stage 09; use existing exit-code families.

| State observed under lock | Result | New revision/event |
| --- | --- | --- |
| Exact pending request still current | Grant the identified request | One `approval-granted` |
| Same request already granted | Return current state; use existing continuation/revalidation | None for duplicate grant |
| Same bound request already advanced/completed | Return the compatible already-approved result | None |
| Another request replaced it or outcome/binding differs | Controlled conflict, proposed `approval-state-changed`, `ILLEGAL_TRANSITION` | None |
| Identified request becomes stale | Invalidate only that request if still eligible; return stale-approval behavior | One invalidation; retry adds none |
| Identical approval request already pending | Return the current request | None for duplicate request |
| Active visit changed before a request commit | Controlled conflict; do not attach old evidence to a new visit | None |

Match the existing run/visit/reason/requested-at/outcome/pipeline/artifact binding;
do not introduce a persisted request ID in this stage. If that binding is
ambiguous, reject with a controlled conflict rather than guessing. Do not select
only by phase name or newest pending record across the run.

## Implementation sequence

1. Reproduce the demonstrated overlap with two store/engine instances and a
   deterministic hook. Record winner and loser manifest/event traces.
2. Add the pure decision and locked store operation. Preserve validation,
   timestamps, defensive copies, and the single commit path. No nested locks.
3. Bind request, grant, and invalidation to the expected visit/request. Recheck
   these preconditions against locked state before applying any mutation.
4. Route the coordinator through the new operation. Distinguish duplicate grant
   from whether advancement still needs to run; retry must keep the saved outcome.
5. Replace the assertion-characterization expectation with the specified result.
   Keep sequential compatibility expectations unchanged and add a separate trace
   for each intentional concurrency correction.
6. Document behavior and diagnostic changes in the same implementation change.

## Verification and exit criteria

Test identical and conflicting simultaneous requests; grant-before-grant and
grant-after-advancement; stale invalidation versus a replacement request; and
revalidation failure after a winning grant. Verify no unhandled assertions,
duplicate grants/transitions, altered winner state, or lost audit history.
Recover a fault between manifest replacement and event append through the same
permitted recovery event as other mutations.

```sh
python -m unittest tests.features.unit.test_visit_transition_store tests.features.unit.test_run_persistence tests.features.contract.test_engine_orchestration tests.features.contract.test_compatibility tests.features.contract.test_recovery tests.features.contract.test_cli
```

Run shared gates. Completion requires the decision table to be fully covered,
sequential behavior unchanged, and all intentional differences documented.
Schema versions and existing stored records remain compatible. If the design
requires a new persisted identity or new exit code, split that proposal out;
do not expand this stage into a migration.

Rollback reverts the narrow behavior change and retains its documented reproducer;
it must not undo successful user approvals or rewrite run history.
