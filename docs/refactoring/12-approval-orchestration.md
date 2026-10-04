# Stage 12 — Isolate approval command orchestration

Status: planned. Prerequisites: stages 09–11.
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
python -m unittest tests.features.unit.test_engine tests.features.unit.test_visit_transition_store tests.features.contract.test_engine_orchestration tests.features.contract.test_interruptions tests.features.contract.test_safety tests.features.contract.test_compatibility tests.features.contract.test_cli
```

Then run shared verification gates. Tests should inspect public responses and
persisted evidence rather than assert that the new service was invoked.

## Exit criteria and rollback

- [ ] Approval lifecycle orchestration has one owner without a dependency cycle.
- [ ] Engine remains the same public API and preserves injected test seams.
- [ ] Validation/approval/provenance order and durable boundaries are unchanged.
- [ ] Known concurrency behavior is characterized, not silently changed.
- [ ] All focused and shared checks pass without refreshing baseline fixtures.

An ordering regression blocks Stage 13. Reverse the smallest extraction or fix
the collaborator boundary; do not compensate by changing approval data or tests.
