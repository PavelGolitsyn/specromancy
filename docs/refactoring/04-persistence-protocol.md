# Stage 04 — Extract the durable persistence protocol

Prerequisite: Stage 03. This is a high-risk boundary; split the work into small
mechanical moves before consolidating duplicated code.

## Purpose and evidence

Run-store methods repeat lock acquisition, manifest/event loading, copying,
revision updates, and `_commit_locked` calls. Serialization, recovery, and domain
transitions currently share the same class. Isolate the durable protocol while
preserving every interruption boundary and the documented one-event recovery rule.

## Proposed file map

- `specromancy/run_persistence.py` (new): internal manifest/event IO, consistency
  checking, recovery, event construction, and locked commit implementation.
- `specromancy/run_store.py`: public API and existing visit operations delegated
  to that persistence boundary; retain repository/run path ownership checks.
- Existing `locking.py`, `artifacts.py`, and `hashing.py`: retain their distinct
  responsibilities. Shared filesystem primitives are optional, not a prerequisite.

## Work items

- [ ] Move read/serialize/hash/event functions first, preserving bytes, file
  modes, newline rules, JSON options, error mapping, and directory fsync behavior.
- [ ] Keep the fault-injector names and their positions relative to temp writes,
  manifest replacement, and event append. Keep existing constructor injection
  and tests that configure the store's injector functional during the move.
- [ ] Make lock ownership explicit: one context acquires the run lock, reads the
  current manifest, validates/reconciles events, applies a change, validates the
  result, replaces the manifest, and appends its event. Internal locked helpers
  must not recursively acquire a second lock.
- [ ] Consolidate revision increment and updated timestamp assignment only after
  per-operation traces match. Distinguish an idempotent return from a mutation;
  no-op commands must not accidentally emit another revision or event.
- [ ] Preserve `load(recover=False)` and `load(verify_artifacts=False)` separately.
  Normal loads may repair a permitted event gap even when invoked from status;
  do not advertise status as wholly free of persistence effects.
- [ ] Retain exact corruption behavior for truncated logs, empty records,
  non-contiguous events, hash mismatch, and gaps outside the recovery rule.
- [ ] Characterize `create` separately: it creates a directory/request before
  the first manifest, and engine initialization prepares a visit afterward.
  Do not silently turn those operations into a new transaction or add automatic
  cleanup of partially initialized runs in this extraction.
- [ ] Compare temporary writers before sharing code. Artifact replacement rules,
  adapter ownership checks, and run fault hooks differ. Keep authorization and
  domain error conversion in each owner even if a low-level write primitive is
  eventually shared.

## Fault acceptance matrix

| Interruption | Required preserved result |
| --- | --- |
| Before manifest replacement | Previous committed manifest/events remain usable |
| After replacement, before append | Load records the allowed recovery event once |
| After event append | Load observes a consistent new revision without duplicate recovery |
| Lock contention | Caller receives lock-held behavior without changing run contents |
| Unexpected manifest/log disagreement | Corruption error; no heuristic reconstruction |
| Interrupted command output capture | Current visit remains retriable under existing semantics |

The last row belongs to the engine integration tests too. Preserve the division
between command-output capture and run-state commits; this stage does not promise
exactly-once external command execution.

## Verification

```sh
python -m unittest tests.features.unit.test_run_store
python -m unittest tests.features.contract.test_interruptions tests.features.contract.test_recovery
python -m unittest tests.features.unit.test_engine tests.features.contract.test_safety
python -m unittest discover
bin/specromancy adapters generate --check
```

Use temporary repositories for fault injection and reload through a new store or
process. Inspect both `run.json` and `events.jsonl`, not only returned payloads.
Compare event sequences, revisions, hashes, and timestamp generation behavior to
Stage 01 traces.

## Exit criteria and rollback

One internal component implements the manifest/event commit protocol. Domain
methods no longer duplicate serialization/recovery internals. Fault traces and
existing schema-version-1 data remain compatible. Do not proceed to transition
extraction while any recovery or locking regression remains. Rollback is a code
revert through normal review; never repair a failing refactor by changing run data.
