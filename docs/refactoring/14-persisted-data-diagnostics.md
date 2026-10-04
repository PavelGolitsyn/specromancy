# Stage 14 — Bound malformed-data errors and decide validation compatibility

Status: planned. Prerequisites: stages 09 and 13.
Category: narrow diagnostic correction plus a compatibility decision record.
Risk: accidentally rejecting previously accepted version-1 runs.

## Objective and evidence

`run_validation.validate_manifest` and `validate_visit` perform membership checks
against status sets before checking whether the value is a string. An array or
object status can therefore raise `TypeError`. Correct that diagnostic path.
Separately inventory weak nested checks; tightening all of them is outside this
stage because the prior refactoring deliberately preserved their acceptance.

The evidence is `test_legacy_weak_validation_is_not_silently_tightened` and the
[Stage 03 schema comparison](03-persisted-records.md#schema-comparison-and-deferred-validation-issues).
TypedDict declarations and the artifact JSON Schema subset are not substitutes
for run/event validation or cross-record consistency checks.

## Files

- `specromancy/run_validation.py`: explicit guards for run and visit status types.
- `tests/features/unit/test_run_records.py`: table of invalid status shapes and
  retained version-1 acceptance cases.
- `tests/features/contract/test_cli.py` or `test_recovery.py`: user-visible
  corruption envelope and non-mutation behavior for malformed persisted state.
- `docs/poc-v3/contracts.md`: clarify malformed-status diagnostics.
- This stage document: record the nested-validation compatibility decision.
- `run_records.py` and `schemas/run.schema.json` / `event.schema.json`: inspect
  for discrepancies; do not automatically synchronize or tighten them.

## Implementation sequence

1. Add reproductions for list/object status values at manifest and visit levels.
   Include null, booleans, numbers, and unknown strings to verify a controlled
   corruption diagnostic for all invalid JSON status shapes.
2. Guard membership checks with a string check. Preserve existing messages and
   the `RunCorruptionError` family wherever possible. Do not catch arbitrary
   exceptions around the whole loader, which could hide programming errors.
3. Assert validation remains read-only. A malformed manifest fails before any
   recovery append; validate this separately from a valid recoverable manifest
   whose artifact verification may fail after recovery.
4. Keep intentionally accepted version-1 shapes unchanged: boolean/integer
   quirks, open approval dictionaries, and weak metadata fields. If another
   accidental exception is discovered, enumerate it and scope a separate fix
   rather than expanding this change invisibly.
5. Complete the decision matrix below from actual readers/writers and fixtures.
   Record required fields, consumers, accepted historical shapes, and desired
   cross-record invariants before recommending stronger validation.

## Stage 09 acceptance inventory

Inspected at `226e510a34389672c1f414221a3451ff4052ced8`; no reader behavior
changed in Stage 09. The Stage 03 schema comparison remains authoritative context.
`test_status_shape_baseline_separates_controlled_errors_from_crashes` adds the
missing status observations; `test_invalid_records_keep_diagnostics`,
`test_event_fields_identity_and_hash_are_checked`, closed-key tests, and
`test_legacy_weak_validation_is_not_silently_tightened` retain the other categories.

| Category | Concrete values / current result | Stage 14 acceptance limit |
| --- | --- | --- |
| Already rejected status | At run and visit levels: null, booleans, numbers, unknown strings raise `RunCorruptionError`, `corrupt-run` (12) | Preserve message: `manifest status is invalid` or `visit identity or status is invalid`; details remain `error_code` and `run_id` |
| Status crashes | At either level: `[]` and `{}` cause unhashable membership `TypeError` when earlier fields are valid | Only intended diagnostic change: same corruption messages/details as above; preserve validation order, no manifest/event edits or recovery append |
| Already rejected other records | Missing/extra closed keys; invalid run ID, paths, hashes, timestamps, current bounds, ordinal/attempt ordering, missing completed timestamp/hash, non-null mutable hash, non-object approvals, non-list evidence fields | Preserve existing errors and ordering; do not broaden a status fix to these paths |
| Weakly accepted numeric/identifier data | `revision=True`, `schema_version=1.0`, pipeline version/current visit/attempt `True`, ordinal `1.0`, empty pipeline/phase IDs and input references | Keep accepted as version 1; annotations/schema do not authorize stricter loading |
| Weakly accepted nested/visit data | Approvals `{}` or `{"status":42,"unknown":[null]}`; object mutation policy, array chosen outcome, numeric transition target, unstructured check/command entries, completion timestamp on active visit | Keep load acceptance, without claiming later engine consumption is safe |
| Deliberately open data | Git base/head values, mutation snapshots/results, terminal/block payloads and deviation entries; finite JSON serialization is still required for manifests | Remain open; no normalization, default injection or rewriting |
| Standalone event limitation | Boolean counters/visit numbers and equality-compatible schema version pass; dictionary payload may contain NaN until append serialization rejects it | Deferred separately; status guards must not alter event validation/serialization |

Manifest validation happens before event reconciliation in
`RunPersistence.locked`. Stage 14 must test disk-level non-mutation for malformed
status even when the event log is one revision behind. This differs from a
**valid** recoverable manifest whose later artifact check fails after appending
recovery. Pure validator non-mutation is covered now; the new CLI/disk-level
malformed-load contract belongs with the Stage 14 correction.

## Nested-validation decision matrix

All rows preserve version-1 reader acceptance in Stage 14. Desired invariants
below are requirements for a separate hardening proposal, not new checks to add.

| Area | Writers and consumers / current accepted shape | Concrete disposition and future acceptance criterion |
| --- | --- | --- |
| Approval dictionaries | `build_approval_record` writes binding, status, decision, actor and times. Selectors/status tolerate missing keys via `get`; request reads reason/details/hash/outcome directly, advance indexes outcome/reason, invalidation matches visit/time. Runtime/schema allow arbitrary objects; `ApprovalRecord` has no required keys | Preserve open dictionaries, unknown fields and orphan references on load. Stage 13 rejects ambiguous operational bindings without tightening the loader. Future schema proposal must require engine-consumed fields, unique request identity and valid visit/outcome references, and specify inspectability/migration for legacy objects |
| Git and mutation metadata | Store create takes base/head; snapshot capture writes worktree/head/branch/index/file records. `validation_service` requires a dictionary baseline; `git.compare_snapshots` consumes `files` mappings and file hash/kind/mode records. Transition evidence copies a dictionary result head into Git head; nested values otherwise pass through | Preserve open metadata. Reproducer: an active fixture with `mutation_baseline={"files":[]}` passes record validation but is unsuitable for snapshot comparison. Hardening must separate inspection from safe enforcement, type file records, preserve dirty-file/mode detection, and never treat absent/malformed evidence as a clean baseline |
| Validation checks / command results | Validation and command runner write structured checks and result records; transition/store persist them. Approval creation uses fresh `checks[0]["sha256"]`; commands are rerun for advancement, not trusted solely because saved checks say passed. Runtime only requires evidence/deviation containers to be lists | Keep `[null,42]` checks and `["unstructured"]` results accepted on load. Future proposal must distinguish display/history from trusted fresh gate evidence, bind any reusable evidence to artifact/config/repository observations and define stale-evidence retry/audit behavior |
| Integers and versions | Runtime positive-int checks accept booleans; equality allows schema version `1.0`/`True` and ordinal 1 as `1.0`/`True`. Integral floats fail ordinary int checks (for example revision `1.0`). Event counters share bool acceptance | Preserve exact quirks. Future change needs old-run/event examples, explicit version/equality policy and controlled diagnostics rather than silently adopting JSON Schema's integer definition |
| Visit/run cross references and times | Validators enforce ordinal sequence, attempt order, current bounds, required start/completion times and mutable/sealed hashes. They do not ensure status agreement, target/outcome existence, chronological times or null unfinished completion. Selectors/status and transitions consume those fields differently | Preserve accepted inconsistencies. Reproducer: active fixture with run status `completed`, or active completion timestamp equal to its start, validates. Future proposal must specify consistency invariants with exceptions for pending/paused/terminal/recovery states and an old-run read policy |
| Open terminal/block payloads | Engine normally writes outcome/phase/visit/approval-reason terminal dictionaries and reason/details/time blocks; store APIs accept arbitrary finite JSON. Status passes payloads through; repeated `block` expects dictionary-like content | Preserve open payloads; do not close their schemas to current engine examples. Reproducer: finite array terminal/block payload validates. Any future safety guard belongs at an operational consumer or requires an explicit compatibility proposal; inspection must retain original user data |

TypedDict field vocabulary and JSON Schema required-key equality tests remain
useful checks, but do not establish safe runtime consumption or cross-record
consistency. Stronger validation requires a separately scoped proposal covering
schema versioning, old-run reads, controlled diagnostics, and any migration policy.

## Verification and exit criteria

```sh
python -m unittest tests.features.unit.test_run_records tests.features.unit.test_run_store tests.features.unit.test_run_persistence tests.features.contract.test_cli tests.features.contract.test_recovery tests.features.contract.test_compatibility
```

Then run shared gates.

- [ ] Invalid status shapes produce controlled corruption errors, not TypeError.
- [ ] No manifest/event mutation occurs on those malformed-load paths.
- [ ] Existing valid fixtures and deliberate weak-acceptance tests still pass.
- [ ] The nested-validation matrix records a concrete disposition for each area.
- [ ] No persisted format, schema version, or general acceptance tightening slipped in.

Rollback is limited to type guards/tests/docs. It must not edit run data, mask
unrelated exceptions, or remove the deferred compatibility findings.
