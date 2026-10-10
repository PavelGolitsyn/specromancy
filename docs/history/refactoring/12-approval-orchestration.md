# Stage 12 — Isolate approval command orchestration

Status: complete on 2026-10-04. Prerequisites: stages 09–11 complete.
Category: behavior-preserving refactoring. Risk: gate order and audit history.

## Objective and evidence

Pure record updates already live in `approvals.py`. The remaining approval flow
is spread across `Engine.request_approval`, `approve`, `_advance_approved`,
`_invalidate_approval`, and `_idempotent_approval_result`. Introduce a cohesive
coordinator for these operations without duplicating validation, provenance, or
responses, and without fixing the known overlap assertion in the same change.

## Files and target responsibilities

- Add `specromancy/approval_service.py` for request/grant/invalidate/advance
  orchestration over a pipeline, store, and explicit collaborators.
- Keep `engine.py` public method signatures and response contracts stable.
  Engine retains ordinary command dispatch and calls the approval coordinator.
- Keep `approvals.py` pure and free of storage, clocks, CLI, and response imports.
- Reuse `validation_service.py`, `provenance.py`, and `responses.py` directly
  where possible. Do not pass the entire Engine into the coordinator.
- Preserve the engine clock and fault-injection seams used by compatibility tests
  through explicit dependencies evaluated at the original call sites.

## Implementation sequence

1. Write down the existing call order for request, grant, already-granted retry,
   invalidation, and advancement. Include resource reads, validation commands,
   evidence writes, approval mutation, transition, and response construction.
2. Extract outcome/reason resolution only if needed to avoid a dependency back
   into Engine. Keep a small shared helper rather than copying the policy or
   building a registry of command handlers. Preserve error ordering.
3. Move invalidation and approved advancement first, then request/grant handling.
   Preserve delegates where existing callers/tests depend on them.
4. Make evidence collection/recording an explicit collaboration. Expected
   validation failures still record one failed attempt; unexpected interruptions
   propagate. Do not execute validation commands twice during the extraction.
5. Retain `approve`'s persisted-state load before strict pipeline checking so
   drift can become a durable stale-approval event. Normal command provenance
   rejection and tolerant `status` warnings must remain separate.
6. Preserve the grant commit followed by revalidation/advancement as separate
   durable operations. A failed revalidation keeps the grant and audit history.
7. Audit imports and update the architecture map. If the coordinator requires
   many callbacks into Engine, revise the boundary before adding more delegates.

Suggested review units: shared resolution seam, approved continuation and
invalidation, then request/grant delegation. No wire-format changes are allowed.

## Verification

Check exact envelopes, diagnostics, revisions, events, and command execution
order for pending requests, grants, stale artifact/pipeline bindings, provenance
drift, failed revalidation, interruptions after grant, duplicate approvals, and
phase/outcome mismatch. Keep the existing assertion-characterization test until
Stage 13 deliberately replaces its expected outcome.

```sh
python -m unittest tests.engine.unit.test_engine tests.engine.unit.test_visit_transition_store tests.engine.contract.test_engine_orchestration tests.engine.contract.test_interruptions tests.engine.contract.test_safety tests.engine.contract.test_compatibility tests.engine.contract.test_cli
```

Then run shared verification gates. Tests should inspect public responses and
persisted evidence rather than assert that the new service was invoked.

## Exit criteria and rollback

- [x] Approval lifecycle orchestration has one owner without a dependency cycle.
- [x] Engine remains the same public API and preserves injected test seams.
- [x] Validation/approval/provenance order and durable boundaries are unchanged.
- [x] Known concurrency behavior is characterized, not silently changed.
- [x] All focused and shared checks pass without refreshing baseline fixtures.

An ordering regression blocks Stage 13. Reverse the smallest extraction or fix
the collaborator boundary; do not compensate by changing approval data or tests.

## Stage 09 decisions to preserve

Follow the [recorded gate order](09-follow-on-baseline.md#approval-order-and-durable-boundary)
and [seam inventory](09-follow-on-baseline.md#import-and-injection-inventory).
Keep public signatures and private delegates, instance `_perform_validation`
interception, store fault injection, and late lookup of `engine.utc_now` even
when patched after Engine construction. Store timestamps are a different clock.
The new gate-precedence test covers competing request failures and stale-binding
invalidation before provenance rejection. Existing compatibility captures already
exercise the interrupted grant/advance boundary and its saved outcome; reuse them.
Stage 13's decided concurrency table is not authorization to change behavior in 12.

## Execution record

Starting revision: `7f71a986396b5f0663b160e31907ad507edde360`; clean checkout.

### Call-order audit before extraction

| Path | Existing observation, mutation, and response order |
| --- | --- |
| Request | Strict store/artifact load, pipeline identity and prepared-resource provenance; current visit guard; reason then outcome resolution; artifact validation, commands, mutation policy, required-command failure; pending/approved selection; request timestamp; pending record plus successful evidence in one `approval-requested` commit; approval response |
| Identical pending request | Same request gates and validation before comparing reason, details, artifact hash, and outcome; approval response without a commit |
| Grant | Persisted store/artifact load before strict pipeline checking; visit/phase checks and idempotent lookup; pending selection; output hash then pipeline binding; durable invalidation on mismatch; prepared-resource provenance; decision timestamp; `approval-granted` commit; approved continuation |
| Already-granted retry | Wrong/currently absent phase uses the approved-for-phase selector and state response without a commit; awaiting visit with a saved grant uses approved continuation without another grant |
| Invalidation | Decision timestamp; detached stale state through `store.mutate`; `approval-invalidated` commit retaining bindings; caller raises its existing stale diagnostic |
| Approved continuation | Output hash and pipeline binding; invalidation on mismatch; artifact validation, commands, mutation policy, required-command failure; saved-outcome transition lookup; transition commit with evidence and sealed output/successor or terminal state; transition response |

Expected validation failure records one failed attempt before raising; unexpected
interruptions propagate. A successful grant and its transition remain separate
durable operations. Requesting approval after a saved grant currently validates
both before selecting that grant and again during continuation; preserve this
existing order while avoiding any additional validation during extraction.

### Completed boundary and import audit

`approval_service.ApprovalService` now owns request, grant, invalidation,
approved advancement, output binding reads, and idempotent approval responses.
It takes a pipeline and store plus exactly two callbacks: validation with expected
failure recording, and a formatted decision timestamp. It does not import or
receive an Engine, and calls provenance observations and response builders
directly. `approvals.py` remains unchanged and pure.

Engine keeps its public signatures and private approval, artifact-hash, selector,
and outcome delegates. Normal strict loading remains in `_load`, including the
load before requesting approval. The coordinator owns approve's distinct
persisted-state-first load. Status still observes drift tolerantly. The shared
`command_decisions` functions preserve reason/outcome and illegal-transition
diagnostics without copying policy or introducing callbacks into Engine.

Validation and timestamp callbacks use late lookup at each original call site,
including an instance validation hook replaced during the grant commit. Engine's
unchanged `_perform_validation` collects evidence through `validation_service`,
records one expected failed attempt, and propagates unexpected interruptions.
Successful evidence remains part of request/transition commits. Store fault
injection and its independent clock retain their existing boundaries.

### Coverage and limitations

- Added public-command coverage using real validation commands that record the
  persisted status they observe. This checks identical pending requests, wrong
  phase rejection, interruption during command output capture after grant,
  approve/run/request continuation, exact command counts, and idempotent final
  approval. Grant and transition each add one revision; interrupted validation
  retains the grant and earlier evidence without a failed-attempt event.
- Added a late-hook interruption test that replaces instance validation after
  the durable grant and checks the saved grant and patched engine timestamp.
- Extended isolated imports to cover the coordinator and shared decisions,
  enforce their lack of Engine/CLI dependencies, and keep decisions/approval
  records independent of storage, timestamps, responses, and validation effects.
- Existing compatibility captures, gate precedence, stale bindings, provenance
  drift, failed revalidation, persisted saved-outcome retry, and overlap tests
  remain unchanged. The architecture map now documents the coordinator.

No scope or behavior deviations. The known before-grant overlap assertion is
still characterized and intentionally remains for Stage 13. No wire formats,
canonical workflow files, adapters, or baseline fixtures changed. The existing
filesystem race and partial-initialization limitations remain outside this stage.
Stages 13–15 were not executed.

### Verification

Executed on Python 3.14.4 using the documented `python3` equivalent. Python 3.11
was not rerun in this stage; minimum-version execution remains a Stage 15 gate.

| Command / checkpoint | Result |
| --- | --- |
| Stage focused command (above, using `python3`) before extraction | 50 passed in 3.003s |
| Same command after extraction | 50 passed in 3.038s |
| Expanded focused command below, with final behavior/import coverage | 59 passed in 4.055s |
| `python3 -m unittest discover` | 234 passed in 27.283s |
| `bin/specromancy adapters generate --check` | Passed: generated adapters are up to date |
| `git diff --check` | Passed |

Expanded focused command:

```sh
python3 -m unittest tests.engine.unit.test_engine tests.engine.unit.test_visit_transition_store tests.engine.contract.test_engine_orchestration tests.engine.contract.test_interruptions tests.engine.contract.test_safety tests.engine.contract.test_compatibility tests.engine.contract.test_cli tests.engine.contract.test_architecture
```

During test construction, the new clock assertion omitted the existing six-digit
fractional seconds. Its expected literal was corrected to match the unchanged
format; no runtime behavior or compatibility fixture was changed for that failure.
