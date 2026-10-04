# Stage 11 — Make visit preparation observations explicit

Status: complete on 2026-10-04. Prerequisites: stages 09–10 complete.
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

- [x] Resource observations have an explicit internal boundary.
- [x] Lock span, resource-read order, timestamp calls, and defensive copies match.
- [x] Exact stored/event bytes and retry behavior remain compatible.
- [x] No persistence protocol, recovery behavior, or artifact ownership changed.

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

## Execution record

Starting revision: `9d08e388da7bbb07183b92a65232280a8c062897`; clean checkout.

### Call-site and ordering audit

| `_new_visit` caller | Supplied manifest | Existing lock / commit boundary |
| --- | --- | --- |
| `start_visit` | Loaded current manifest at revision N | `RunPersistence.locked` spans pipeline check, active preparation, append decision, and commit at N+1 |
| `prepare_visit` | Loaded current manifest at revision N | Same lock spans pipeline check, pending preparation, append decision, and commit at N+1 |
| `transition_visit` | Sealed, detached proposal still at revision N | Same lock spans loading, retry/limit checks, sealing, pending successor preparation, finish decision, and the single commit at N+1 |

Exact transition retries return before resource collection; a reached limit
blocks without sealing or preparing a successor. No caller or lock scope changed.

`visit_preparation.collect_resources` now receives the run directory, borrowed
manifest, pipeline, resolved phase, repository root, and ordinal explicitly.
It returns `VisitResources` containing fresh input records, output path, skill
provenance, and optional template provenance. It performs no writes, locking,
timestamps, manifest mutation, visit construction, or commits. Artifact and hash
policies remain in their existing modules.

`_new_visit` keeps its signature, initial-status guard, phase lookup and chained
error, ordinal/attempt calculation, active timestamp, and pure construction call.
Resource order remains: inputs in declaration order, output rendering,
reserved/existing collision checks, skill hash, optional template hash. The
active start timestamp follows those reads; pending visits keep it unset.
Existing helper imports through `run_store` remain available.

### Coverage and scope

- Added a resource-boundary test proving the helper works under an already held
  lock, leaves borrowed state and run files unchanged, and returns detached input
  data without creating an output artifact.
- Added successor coverage for both `latest:` and `visit:` bindings against the
  just-sealed output, lock exclusion during successor skill reads, a single
  revision/event, and byte-identical retries after removing that skill file.
- Extended isolated imports to exclude store, persistence, locks, clocks,
  transition construction, and response dependencies from the new module.
- Retained existing tests for preparation timestamps, mutation baselines,
  provenance capture without activation refresh, collision precedence, resource
  failure without a partial commit, limits, defensive copies, and exact bytes.
- Updated the architecture ownership map and preparation contract explanation.

No scope deviations or behavior corrections. Missing resource reads still
propagate raw IO failures. The existing persistence/recovery protocol and
external-filesystem concurrency limitations remain unchanged; stages 12–15 are
not part of this execution.

### Verification

Executed on Python 3.14.4 using the documented `python3` equivalent because this
shell has no `python` executable. Python 3.11 was not rerun in this stage.

| Command / checkpoint | Result |
| --- | --- |
| Focused command below before extraction, excluding architecture | 54 passed in 1.837s |
| Focused command after extraction and import-boundary coverage | 61 passed in 2.443s |
| Focused command with final ownership/successor coverage | 63 passed in 2.372s |
| `python3 -m unittest discover` | 232 passed in 25.536s, including compatibility and source-export coverage |
| `bin/specromancy adapters generate --check` | Passed: generated adapters are up to date |
| `git diff --check` | Passed |

Focused command:

```sh
python3 -m unittest tests.features.unit.test_visit_transitions tests.features.unit.test_visit_transition_store tests.features.unit.test_run_store tests.features.unit.test_run_persistence tests.features.contract.test_compatibility tests.features.contract.test_safety tests.features.contract.test_architecture
```
