# Stage 04 — Extract the durable persistence protocol

Prerequisite: Stage 03. This is a high-risk boundary; split the work into small
mechanical moves before consolidating duplicated code.

Status: implemented on 2026-10-04; no migration or adapter regeneration required.

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

- [x] Move read/serialize/hash/event functions first, preserving bytes, file
  modes, newline rules, JSON options, error mapping, and directory fsync behavior.
- [x] Keep the fault-injector names and their positions relative to temp writes,
  manifest replacement, and event append. Keep existing constructor injection
  and tests that configure the store's injector functional during the move.
- [x] Make lock ownership explicit: one context acquires the run lock, reads the
  current manifest, validates/reconciles events, applies a change, validates the
  result, replaces the manifest, and appends its event. Internal locked helpers
  must not recursively acquire a second lock.
- [x] Consolidate revision increment and updated timestamp assignment only after
  per-operation traces match. Distinguish an idempotent return from a mutation;
  no-op commands must not accidentally emit another revision or event.
- [x] Preserve `load(recover=False)` and `load(verify_artifacts=False)` separately.
  Normal loads may repair a permitted event gap even when invoked from status;
  do not advertise status as wholly free of persistence effects.
- [x] Retain exact corruption behavior for truncated logs, empty records,
  non-contiguous events, hash mismatch, and gaps outside the recovery rule.
- [x] Characterize `create` separately: it creates a directory/request before
  the first manifest, and engine initialization prepares a visit afterward.
  Do not silently turn those operations into a new transaction or add automatic
  cleanup of partially initialized runs in this extraction.
- [x] Compare temporary writers before sharing code. Artifact replacement rules,
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


## Execution results

`run_persistence.py` now owns manifest/event reads, serialization, canonical
manifest hashes, event construction, consistency checking, recovery, durable
replacement/append, and directory fsync. `RunStore` delegates to this internal
component while retaining path ownership checks, creation layout/request writes,
artifact verification, defensive copies, and all existing visit decisions.
Artifact and adapter writers remain separate; no shared filesystem primitive or
new transaction abstraction was introduced.

The extraction proceeded in two steps: first move the IO/recovery routines and
replay the compatibility/fault tests, then consolidate lock acquisition and
revision/timestamp assignment. A single `locked` context holds the run lock
across loading, reconciliation, domain changes, validation, and commit. The
commit helper never acquires a second lock. Revision stamping remains explicit
at each operation's original clock boundary; idempotent returns bypass it, while
`mutate` still always commits and resets a callback-supplied revision from the
previous persisted revision. The constructor injector and later assignments to
`store._fault_injector` both retain all six fault points and their ordering.

Creation uses the same commit implementation for revision 1 under its own lock,
without attempting to load a nonexistent manifest. Directory creation, immutable
request writing, first manifest commit, and engine visit preparation remain
separate interruption boundaries. Tests confirm that partial creation is not
cleaned up and that interruption between creation and visit preparation leaves a
valid revision-1 run with no visit. This is characterized existing behavior, not
a new guarantee that initialization is transactional or automatically retriable.
Command-output capture remains an independent engine boundary with its existing
retriable-visit semantics; exactly-once command execution is not promised.

Verification on Python 3.14.4:

- Before extraction, the new protocol characterizations, store tests, and Stage
  01 compatibility replay: **29 passed**.
- After the initial mechanical move, those tests plus interruption and recovery
  contracts: **36 passed**.
- Final focused store/protocol, interruption/recovery, engine/safety,
  compatibility, and architecture checks: **62 passed**.
- All **8 added tests** also passed against the original store implementation,
  loaded from a temporary pre-extraction source copy.
- `python3 -m unittest discover`: **199 passed** in 23.801 seconds.
- `bin/specromancy adapters generate --check`: passed without generated writes.
- `git diff --check`: passed.

The new coverage inspects both persisted files at every fault boundary and
reloads through a fresh store, asserting exact recovery counts, revisions,
sequences, hashes, file modes, cleanup of temporary files, and unchanged committed
bytes before replacement. It also checks independent recovery/artifact options,
lock contention, invalid/raising mutations, unrecoverable revision gaps, partial
creation, and timestamp generation with an advancing clock. Existing tests
retain malformed/truncated/empty log, sequence/revision/hash mismatch,
command-capture interruption, and fresh-process reload coverage. The Stage 01
fixtures still reproduce exact manifest/event bytes, responses, and hashes.
Architecture checks include the new component and verify that it imports without
the store, engine, CLI, artifact layer, or response builders.

An AST comparison of all ten extracted protocol routines confirms unchanged
bodies after accounting for direct validator dispatch, the commit helper's name
and lock-ownership docstring, and returning already-checked events from strict
consistency checking. JSON options, newline handling, error mapping, temporary
file modes, hook positions, and fsync behavior are preserved.

The public contracts now explicitly describe load-time recovery (including
status), independent load options, idempotent returns versus general mutations,
and partial initialization. No workflow sources, adapters, schemas, or Stage 01
fixtures changed. No transition extraction was undertaken. There are no deferred
Stage 04 failures; partial-initialization behavior remains a candidate for a
separate behavior change. The documented `python3` equivalent was used because
this environment has no `python` executable. Python 3.11 execution remains
unverified in this environment.
