# Stage 03 — Isolate persisted records and invariants

Prerequisites: Stages 01–02. Keep the stored representation as dictionaries.

Status: implemented on 2026-10-04; no migration or adapter regeneration required.

## Purpose and evidence

`RunStore._validate_manifest`, `_validate_visit`, and `_validate_event` combine
runtime shape checking with the persistence implementation. The engine, action
builder, and status builder also navigate the same nested dictionaries. A shared
record vocabulary should clarify these boundaries without replacing JSON data
with a new object graph or assuming type annotations validate external data.

## Proposed file map

- `specromancy/run_records.py` (new): `TypedDict` definitions for run, visit,
  artifact, approval, and event records; schema constants; pure selectors.
- `specromancy/run_validation.py` (new): extracted manifest, visit, event,
  provenance, timestamp, and persisted-path validation.
- `specromancy/run_identity.py` (new): current run-ID validation/generation and
  timestamp helpers, preserving injection behavior.
- `specromancy/run_errors.py` (new): existing run-store exception definitions.
- `specromancy/run_store.py`: retain existing imports, aliases, and methods as
  the compatibility surface; delegate validation and identity operations.
- Existing `actions.py`, `status.py`, and `engine.py`: adopt types/selectors only
  where semantics match their current lookups.

## Work items

- [x] Extract run errors and identity helpers first, retaining exception identity
  and generated run-ID syntax. Preserve zero-argument and sized random-source
  compatibility and UTC timestamp formatting.
- [x] Define record annotations matching the current schema exactly, including
  nullable hashes/timestamps and intentionally open payloads. Do not make runtime
  constructors silently insert missing fields.
- [x] Move runtime validators without expanding or tightening accepted values in
  the extraction change. Preserve required-key sets, ordering checks, and error
  codes. Document weakly validated nested fields as follow-up candidates.
- [x] Compare validators with `schemas/run.schema.json` and `event.schema.json`.
  Identify differences explicitly; the artifact schema subset is not a general
  replacement for cross-record run validation.
- [x] Consolidate identical current-visit and approval-record selection only
  after comparing absent/current/completed semantics. Do not replace a tolerant
  presentation lookup with a raising persistence lookup merely to remove lines.
- [x] Annotate data crossing store/engine/presentation boundaries incrementally.
  Use standard-library typing; add neither a runtime validator dependency nor a
  mandatory static-analysis tool.
- [x] Preserve defensive copies returned by `RunStore`; helper reuse must not
  expose mutable store state or change caller-visible record contents.

## Verification

```sh
python -m unittest tests.engine.unit.test_run_store tests.engine.unit.test_engine
python -m unittest tests.engine.contract.test_recovery tests.engine.contract.test_cli tests.engine.contract.test_safety
python -m unittest discover
bin/specromancy adapters generate --check
```

Replay Stage 01 persisted examples through the extracted validators. Exercise
missing/extra keys, invalid identities and paths, out-of-order attempts, mutable
outputs with sealed hashes, missing completion timestamps, and event mismatches.
Check selectors through externally meaningful action/status/approval outcomes.

## Exit criteria and rollback

Stored bytes and schema versions remain unchanged. Validators have no filesystem
mutation and no engine/CLI dependencies. Existing imports, aliases, and exception
handlers continue to work. Any newly discovered invalid-data acceptance is
documented for a separate corrective change. Reverting this extraction requires
no changes to stored runs or schema files.


## Execution results

The proposed module map is implemented. `run_store` re-exports the original
identity helpers, schema/status constants, and exception classes and keeps its
aliases and validation methods. Those methods delegate to pure functions in
`run_validation`. `run_records` describes ordinary dictionaries using Python
3.11-compatible standard-library typing. Nullable output hashes, templates,
timestamps, and approval decisions remain nullable; open metadata and payloads
remain open. Approval annotations describe optional known fields rather than
requiring fields that the runtime has never required. No constructor adds fields.

Store, engine, action, status, and approval boundaries now use record annotations.
The shared current-visit selector preserves absent/unmatched ordinals and returns
completed visits. Approval selection retains reverse ordering, global pending
selection in status, and visit filtering in engine/next-command decisions. The
store's raising visit lookup, approval invalidation's first-match lookup, and
phase-based idempotency lookup remain separate because their semantics differ.
Store copy boundaries and all persistence/recovery code remain in place.

Validation on Python 3.14.4:

- Record, store, and engine unit tests plus architecture contracts: **41 passed**.
- Recovery, CLI, and safety contracts: **12 passed**.
- `python3 -m unittest discover`: **191 passed** in 23.790 seconds.
- `bin/specromancy adapters generate --check`: passed without generated writes.
- `git diff --check`: passed.

The Stage 01 examples pass directly through the extracted validators without
mutation and replay through the store, preserving exact persisted bytes,
responses, hashes, diagnostics, and recovery behavior. New regression coverage
checks missing/extra keys, unsafe paths, invalid identities, attempt ordering,
sealed mutable outputs, missing completion timestamps, event mismatches, legacy
weak acceptance, UTC/random injection, selector outcomes, and copy isolation.
Fresh-interpreter import checks cover all four extracted modules without loading
the store, engine, CLI, artifact layer, or response builders. AST comparison with
the pre-extraction source confirms the validator bodies differ only in removal
of `self`/method dispatch; identity helpers and exception definitions are unchanged.

The prescribed `python` executable is unavailable, so the documented `python3`
equivalent was used. Python 3.11 execution remains unverified in this environment.
No schema files, workflow sources, adapter files, or compatibility fixtures changed.
The only file-map extension is annotation adoption in the existing `approvals.py`.

## Schema comparison and deferred validation issues

The comparison uses `specromancy/schemas/run.schema.json` and
`specromancy/schemas/event.schema.json`. Required-key sets and closed-record shapes
agree for manifests, visits, pipeline provenance, Git metadata, artifacts,
skill/template provenance, and events. Runtime behavior is deliberately preserved:

| Area | Existing runtime behavior versus published schema |
| --- | --- |
| Numeric values | `isinstance(value, int)` accepts booleans for revisions, attempts, pipeline versions, current visits, and event counters/visit numbers. Schema integers exclude booleans. Schema-version equality also accepts `True` and `1.0`; ordinal equality accepts `True` or `1.0` for ordinal 1. Conversely, integer checks reject integral floats accepted by JSON Schema's mathematical integer definition. |
| Identifiers and references | Runtime allows empty pipeline IDs, phase IDs, and input references; the schema requires nonempty strings. Run IDs receive calendar validation and must equal the requested run ID; the schema checks only a pattern. Event validation checks equality with the caller's run ID, relying on the store to validate that ID. |
| Paths and patterns | Runtime additionally requires normalized POSIX spelling and rejects drive prefixes, duplicate separators, and trailing separators. The schema path pattern does not enforce those constraints. Runtime uses full matches for hashes, run IDs, and event types; schema regex anchors can differ for trailing newlines. Neither layer checks file existence here; artifact/store operations own filesystem checks. |
| Timestamps | Runtime requires a final `Z` and successful `datetime.fromisoformat` parsing after suffix replacement; schemas only require the `Z$` pattern. Runtime does not require its own microsecond formatting or chronological ordering. |
| Cross-record visit rules | Runtime checks sequential ordinals, per-phase attempt order, current-visit bounds, completed-output hashes, null hashes for mutable outputs, start timestamps for non-pending visits, and completion timestamps for completed visits. The schemas do not express these relationships. Neither layer requires a null completion timestamp for unfinished visits or a null start timestamp for pending visits. |
| Visit metadata | Runtime does not validate `mutation_policy`, `chosen_outcome`, or `transition_target` values; the schema declares a policy enum and nullable strings. For example, an object policy or array outcome passes the runtime validator. |
| Open nested data | Both accept arbitrary approval objects (including `{}` and unknown fields), arbitrary Git values, mutation snapshots/results, terminal/block payloads, and unstructured list entries in validation checks, command results, and deviations. Their presence is not evidence of engine-safe contents. |
| JSON values and audit relationships | Manifest validation rejects non-JSON values and NaN through serialization. Standalone event validation checks only that payload is a dictionary; it does not check nested JSON serializability or finiteness. Event append serialization enforces that separately. Event continuity, final revision/hash agreement, and recovery remain store checks and are not expressible by validating one event against its schema. |

These differences are follow-up candidates for a separately reviewed corrective
change, not new acceptance rules. In particular, weak approval/visit metadata can
pass validation and later fail at consumption. Unhashable run/visit status values
also currently raise `TypeError` from membership tests rather than a structured
corruption error; the extraction preserves this diagnostic gap. No claim is made
that malformed records are safe merely because the current validator accepts them.

The artifact JSON Schema subset is not a replacement for these validators: it
supports neither the complete published-schema vocabulary (such as `$ref` and
`oneOf`) nor cross-record identity, ordering, hash, or recovery checks. Replacing
runtime validation with it would alter accepted values and diagnostic precedence.
