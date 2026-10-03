# Stage 05 — Separate visit decisions from persistence

Prerequisite: Stage 04. Preserve the `RunStore` API and commit boundaries.

## Purpose and evidence

`prepare_visit`, `activate_visit`, `complete_visit`, `transition_visit`,
`resume_paused`, `_new_visit`, and `_transition_limit_block` currently mix state
decisions with hashing, reading artifacts, and committing records. Extract
decisions that can be evaluated with explicit inputs while keeping filesystem
observations inside the appropriate locked operation.

## Proposed file map

- `specromancy/visit_transitions.py` (new): visit record construction from resolved
  inputs, status guards, limit decisions, and successor/terminal state changes.
- `specromancy/run_store.py`: compatibility methods that gather required evidence
  and invoke those decisions through the Stage 04 commit boundary.
- `specromancy/run_records.py`: shared record types and selectors from Stage 03.
- Existing `artifacts.py`: input resolution, output paths, artifact hashing and
  immutability verification remain filesystem-aware operations here.

## Work items

- [ ] Document a transition table for pending, active, awaiting-approval,
  completed, blocked, and paused combinations. Include legal repeats and errors.
- [ ] Extract limit calculations first. Preserve which visits/traversals count,
  when limits block, diagnostic payloads, and the fact that no extra successor
  is created after a limit is reached.
- [ ] Separate `_new_visit` evidence collection from dictionary construction.
  Pass timestamps, literal input records, provenance records, output paths, and
  baseline explicitly; pure constructors do not read files or clocks.
- [ ] Preserve the existing timing of symbolic input resolution and skill/template
  hashing. Do not change when a pending visit captures inputs as part of cleanup.
- [ ] Extract transition decisions using a copied validated record. The result
  should describe the new state and event payload, or an explicit no-op. It must
  not assign persistence revisions, write files, or acquire locks.
- [ ] Route completion plus successor preparation through one commit. Preserve
  terminal payloads, chosen outcomes, Git head updates, and sealed output hashes.
- [ ] Keep paused successors pending. `resume` releases the checkpoint without
  starting the visit; phase/run commands retain their existing pause guards.
- [ ] Keep public low-level methods such as `complete_visit` and `start_visit`
  distinct where they have different semantics; do not collapse them solely
  because their implementations overlap.
- [ ] Preserve locked reloads and existing guards when applying a decision.
  Characterize overlapping validation/approval attempts before proposing any
  expected-revision or new lock-lifetime policy. Such hardening changes behavior
  and needs its own review rather than an incidental refactoring parameter.

## Verification

```sh
python -m unittest tests.features.unit.test_run_store tests.features.unit.test_engine
python -m unittest tests.features.contract.test_default_pipeline tests.features.contract.test_example_pipelines tests.features.contract.test_replacement_pipeline
python -m unittest tests.features.contract.test_interruptions tests.features.contract.test_safety
python -m unittest discover
bin/specromancy adapters generate --check
```

Use table-driven decision tests for meaningful combinations, then verify full
persisted traces for a linear graph, bounded loop, branch, approval, and paused
edge. Test the limit boundary, not only a far-over-limit state. Retry a recorded
transition and verify it does not append a visit, event, or revision twice.

## Exit criteria and rollback

Transition logic can be tested without disk access using explicit evidence.
The store still guarantees immutable historical outputs and one committed
successor transition. Generic modules reference configured IDs rather than
shipped phase names. All event traces, pause semantics, and idempotency checks
match the baseline. Revert individual extracted operations if necessary rather
than changing the wire format or rewriting historical visits.
