# Stage 13 — Handle concurrent approval decisions under the run lock

Status: complete. Prerequisite: Stage 12.
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
- `docs/reference/contracts.md`: document new conflict/idempotency semantics.

Do not change general `RunStore.mutate`: it intentionally commits even when its
callback leaves data unchanged. The new approval operation needs an explicit
no-op result so duplicate decisions do not manufacture an audit event.

## Stage 09 decision contract

Decided on 2026-10-04; **not implemented by Stage 09**. Ordinary sequential
responses remain unchanged. This table governs commands whose earlier observation
has been overtaken before their locked approval decision. Lock acquisition itself
still reports existing `LOCK_HELD` (10), without waiting/retrying implicitly.

An observed request identity consists of `run_id`, `visit_number`, `phase_id`,
`reason`, `details`, `requested_at`, `outcome`, `pipeline_sha256`, and
`artifact_sha256`. All must match the persisted record; status/decision/actor/
`decided_at` are mutable decision fields, not identity. Match the containing run
and referenced visit as well. Multiple matching records, missing identity fields,
an invalid phase/visit association, or a replacement with different identity are
ambiguous: return conflict, never select the latest record or match by phase alone.
No persisted request ID is added.

For *creation* of a duplicate request, compare that same binding **except
`requested_at`**: overlapping creators have different local timestamps. Return
the winning persisted request with its original timestamp/details/evidence; do
not append or overwrite it. A changed details string is a different request.
Fresh evidence belongs only to the visit observed for the request, even if a
successor reuses the same phase ID. This check is part of the locked decision.

Counts below are additional manifest revisions / audit events caused by the
losing or deciding command, measured from the state it sees under lock. They
exclude already committed winner work and separately identified continuation.

| State under lock | Outcome / diagnostic | Revisions / events |
| --- | --- | --- |
| Expected visit still active, no conflicting pending/granted record | Store new request/evidence; existing `approval is required` response (7) | +1 / +1 `approval-requested` |
| Identical creation binding already pending | Return winning pending record, `approval is already pending` (7) | 0 / 0 |
| Conflicting creation binding, or active visit changed | Conflict below; no old evidence attached to current visit | 0 / 0 |
| Exact observed request pending on the current awaiting-approval visit | Grant identified record, then continue from returned state | +1 / +1 `approval-granted`, plus continuation |
| Exact request already granted, still awaiting advancement | Reuse grant; revalidate/continue saved outcome | 0 / 0 for grant, plus continuation |
| Exact granted request's visit completed with its saved outcome and configured target; run may be terminal, paused or on a successor | Return current state with existing `approval was already recorded` response family; never advance the successor | 0 / 0 |
| Request replaced, absent, ambiguous, differently bound, or completed with a conflicting outcome/target | Conflict below; preserve winner | 0 / 0 |
| Integrity observation finds stale artifact/pipeline, same pending or granted request still eligible on current awaiting-approval visit | Invalidate exactly it; existing `stale-approval` (7) with ordered mismatches (`artifact`, then `pipeline`) | +1 / +1 `approval-invalidated` |
| Same in-flight stale decision arrives after that exact request was already invalidated, with no replacement/current-visit change | Return `stale-approval` again | 0 / 0 |
| Stale decision arrives after replacement or visit advancement | Conflict; do not invalidate replacement or reopen completed visit | 0 / 0 |

Conflict envelope: existing `EngineError` / `ILLEGAL_TRANSITION` (5), diagnostic
`approval-state-changed`, message **approval state changed before the command
could be applied**, details `run_id`, `phase` (observed phase ID), and
`visit_number` (observed ordinal), alongside `error_code`. It must not expose a
traceback or create an audit event. A fresh sequential command finding a different
pending request retains its existing `illegal-transition` diagnostic. A fresh
`approve` after invalidation still has no pending request and retains the existing
illegal-transition behavior; the duplicate-stale row is for an in-flight decision
already bound to that request.

Continuation preserves separate durable operations: successful validation adds
+1 / +1 `visit-transitioned` (or `loop-limit-exceeded` when applicable); each
expected failed validation adds +1 / +1 `validation-failed` and leaves the grant
intact. Interruption before evidence recording adds neither. An exact transition
retry after a competing completion adds 0 / 0. Duplicate continuations can each
run validation commands; this stage prevents duplicate grants/transitions, not
all duplicate command execution or command-log interleavings.

Concrete terminal overlap trace using `OverlappingAttemptTests.prepare_approval`:
revisions/events 1–6 are `run-created`, `visit-prepared`, `visit-activated`,
`visit-transitioned`, `visit-activated`, `approval-requested`. The winning approve
adds revision/event 7 `approval-granted` and 8 `visit-transitioned`. The losing
before-grant command currently asserts without changing either file; Stage 13
must instead return the already-recorded response with files still at 8/8.
If the winner stops immediately after grant, files are at 7/7; the loser adds
only transition 8/8, or failure 8/8 if revalidation fails. Each further failed
retry adds one failure event and never another grant. From an active state, two
identical request attempts add only one request event; conflicting attempts add
one winner request event and zero loser events.

For any new approval commit interrupted after manifest replacement but before
append, the manifest has advanced once and the log is one event short. Load
appends the existing `recovery` event, without another revision or synthesizing
the missing approval event type; subsequent loads/retries add no duplicate
recovery. The decision operation uses the existing persistence protocol.

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
python -m unittest tests.engine.unit.test_visit_transition_store tests.engine.unit.test_run_persistence tests.engine.contract.test_engine_orchestration tests.engine.contract.test_compatibility tests.engine.contract.test_recovery tests.engine.contract.test_cli
```

Run shared gates. Completion requires the decision table to be fully covered,
sequential behavior unchanged, and all intentional differences documented.
Schema versions and existing stored records remain compatible. If the design
requires a new persisted identity or new exit code, split that proposal out;
do not expand this stage into a migration.

Rollback reverts the narrow behavior change and retains its documented reproducer;
it must not undo successful user approvals or rewrite run history.

## Execution record — 2026-10-06

Completed from clean starting revision
`e043d79260118039afe55483090ca2b989448c6c`.

- Reproduced the before-grant assertion with the original deterministic two-engine
  test before implementation. Replaced it with the already-recorded response:
  winner grant/transition end at revision/event 8/8 and the loser changes neither
  file. A winner interrupted after grant ends at 7/7; the loser continues to 8/8
  without another grant.
- Added pure approval decisions with complete observed bindings, explicit no-ops,
  and the specified `approval-state-changed` error. Creation ignores only the
  request timestamp when matching duplicate pending requests. Grant and stale
  decisions reject absent, ambiguous, replaced, or incorrectly associated records.
- Added `RunStore.decide_approval`, resolving against state loaded under the run
  lock and using the existing shared commit path. No nested lock or change to
  general `mutate` behavior was introduced. Returned records are detached copies.
- Routed request, grant, invalidation, and approved continuation through locked
  decisions. Continuation uses current returned records and the saved outcome.
  Completed grants return current terminal/paused/successor state without advancing
  that successor. The old grant-hook test now observes the approval decision seam.
- Added deterministic coverage for identical/conflicting requests, grant overlaps,
  failed continuation and retry, stale duplicates/replacements/advancement, reused
  phase IDs, identity fields, ambiguous records, conflicting completion bindings,
  lock scope, detached results, and recovery for all three approval event types.
  Paused, pending, active, and completed successor cases are separate from the
  unchanged sequential compatibility replay and its checked-in byte captures.
- Documented the diagnostic, revision/event semantics, binding rules, and recovery
  behavior in the public contracts and architecture map.

Verification used Python 3.14.4 through `python3`, because this shell has no
`python` executable. The initial command using `python` could not run; its
`python3` equivalent reproduced the original test successfully. An intermediate
focused run exposed the old test hook still wrapping `mutate`; moving that hook
to `decide_approval` retained the existing validation/timestamp assertions.

| Command | Result |
| --- | --- |
| `python3 -m unittest tests.engine.unit.test_visit_transition_store.OverlappingAttemptTests.test_overlap_before_approval_grant_exposes_existing_assertion` (before change) | 1 passed; reproduced the expected assertion |
| Stage focused command below | 48 passed in 2.028s |
| `python3 -m unittest discover` | 246 passed in 27.429s |
| `bin/specromancy adapters generate --check` | Passed; generated adapters are up to date |
| `git diff --check` | Passed |

```sh
python3 -m unittest tests.engine.unit.test_visit_transition_store tests.engine.unit.test_run_persistence tests.engine.contract.test_engine_orchestration tests.engine.contract.test_compatibility tests.engine.contract.test_recovery tests.engine.contract.test_cli
```

No schema, exit-code, dependency, workflow, adapter, or compatibility-fixture
changes. No scope deviations. Python 3.11 was not rerun; minimum-version execution
remains a Stage 15 gate. External file edits versus validation, duplicate command
execution/log interleavings, broader engine interleavings, and partial
initialization remain outside this stage. Stages 14–15 were not executed.
