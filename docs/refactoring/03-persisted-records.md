# Stage 03 — Isolate persisted records and invariants

Prerequisites: Stages 01–02. Keep the stored representation as dictionaries.

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

- [ ] Extract run errors and identity helpers first, retaining exception identity
  and generated run-ID syntax. Preserve zero-argument and sized random-source
  compatibility and UTC timestamp formatting.
- [ ] Define record annotations matching the current schema exactly, including
  nullable hashes/timestamps and intentionally open payloads. Do not make runtime
  constructors silently insert missing fields.
- [ ] Move runtime validators without expanding or tightening accepted values in
  the extraction change. Preserve required-key sets, ordering checks, and error
  codes. Document weakly validated nested fields as follow-up candidates.
- [ ] Compare validators with `schemas/run.schema.json` and `event.schema.json`.
  Identify differences explicitly; the artifact schema subset is not a general
  replacement for cross-record run validation.
- [ ] Consolidate identical current-visit and approval-record selection only
  after comparing absent/current/completed semantics. Do not replace a tolerant
  presentation lookup with a raising persistence lookup merely to remove lines.
- [ ] Annotate data crossing store/engine/presentation boundaries incrementally.
  Use standard-library typing; add neither a runtime validator dependency nor a
  mandatory static-analysis tool.
- [ ] Preserve defensive copies returned by `RunStore`; helper reuse must not
  expose mutable store state or change caller-visible record contents.

## Verification

```sh
python -m unittest tests.features.unit.test_run_store tests.features.unit.test_engine
python -m unittest tests.features.contract.test_recovery tests.features.contract.test_cli tests.features.contract.test_safety
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
