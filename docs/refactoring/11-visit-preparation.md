# Stage 11 — Make visit preparation observations explicit

Status: planned. Prerequisites: stages 09–10.
Category: behavior-preserving refactoring. Risk: resource binding and lock timing.

## Objective and evidence

`RunStore._new_visit` resolves symbolic inputs, checks output collisions, reads
skill/template hashes, calculates ordinal/attempt, and calls the already pure
`visit_transitions.new_visit`. Extract the observation responsibility without
moving it outside the existing lock or duplicating transition decisions.

## Files and boundaries

- Add `specromancy/visit_preparation.py` for resource collection from explicit
  directory, manifest, pipeline, and phase arguments. It may read files; it must
  not acquire locks, write artifacts, commit state, or build CLI responses.
- Keep `run_store.py` responsible for run/path ownership, lock acquisition,
  operation order, timestamps, and applying decisions.
- Keep record construction and transition/limit decisions in `visit_transitions.py`.
- Reuse `artifacts.py` and `hashing.py`; do not create another path or hash policy.
- Extend `test_visit_transition_store.py`, `test_run_store.py`, and architecture
  coverage only where extraction exposes an untested timing/ownership contract.

## Implementation sequence

1. List all `_new_visit` call sites: active start, pending preparation, and pending
   successor preparation. Record the manifest version and lock scope each uses.
2. Extract the resource-read sequence into one helper with a small named result
   for inputs, output path, skill provenance, and optional template provenance.
   Use borrowed input state and detached result data; do not mutate the manifest.
3. Preserve phase lookup, ordinal/attempt computation, collision checking order,
   and exceptions. Keep the caller's timestamp evaluation after resource reads
   for active creation; pending preparation must not gain a start timestamp.
4. Keep `_new_visit` as a thin compatibility delegate combining observations with
   `visit_transitions.new_visit`. Supply phase/identity arguments explicitly so
   the new helper does not need a `RunStore` instance or access to its private API.
5. Verify transition successors observe the **sealed proposal** inside the same
   lock, so symbolic latest/visit inputs refer to the just-completed output.
   Do not prepare successors from the earlier, unsealed manifest.
6. Document resource capture at preparation and its lack of refresh on activation.
   Retain the distinct low-level start/complete methods and their existing guards.

## Required scenarios

| Scenario | Expected invariant |
| --- | --- |
| Prepare pending then change skill/template | Activation does not silently refresh provenance |
| Start active versus prepare pending | Timestamp and mutation-baseline behavior stays distinct |
| Complete and create successor | One manifest revision seals output and binds successor inputs |
| Transition reaches limit | Block without sealing output or creating a successor |
| Reserved or existing output path | Controlled collision failure with no replacement of the artifact |
| Exact transition retry | No resource refresh, extra revision, or extra event |
| Preparation read fails | No partial successor commit; prior manifest/event state remains coherent |

Use deterministic fixture edits or hooks, not sleeps. The run lock coordinates
store operations, not arbitrary external filesystem writers; this stage does
not claim to fix concurrent validation evidence or filesystem races.

```sh
python -m unittest tests.features.unit.test_visit_transitions tests.features.unit.test_visit_transition_store tests.features.unit.test_run_store tests.features.unit.test_run_persistence tests.features.contract.test_compatibility tests.features.contract.test_safety
```

Then run shared verification gates.

## Exit criteria and rollback

- [ ] Resource observations have an explicit internal boundary.
- [ ] Lock span, resource-read order, timestamp calls, and defensive copies match.
- [ ] Exact stored/event bytes and retry behavior remain compatible.
- [ ] No persistence protocol, recovery behavior, or artifact ownership changed.

If an extraction changes the failure point, restore the caller order before
proceeding. Roll back the helper/delegate change only; never rewrite artifacts or
delete partial runs to make verification pass.

## Stage 09 decisions to preserve

The [baseline resource sequence](09-follow-on-baseline.md#extraction-to-test-map)
records all three `_new_visit` callers and the sealed-successor lock boundary.
New store tests cover resource capture before active timestamps, skill-before-
template capture under a held lock, reserved/existing collisions before missing
skill reads, and successor read failure without sealing/committing. Keep raw IO
failure behavior during this extraction. Retain `_new_visit`; pending activation
and exact transition retries must not refresh provenance. No new snapshot or
filesystem concurrency guarantee is implied by the store lock.
