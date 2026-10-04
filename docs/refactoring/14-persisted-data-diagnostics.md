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

## Nested-validation decision matrix

| Area | Questions to resolve for a later hardening change |
| --- | --- |
| Approval dictionaries | Which consumers require each field? How should unknown/extra fields and orphaned visit references be handled? |
| Git and mutation metadata | Which fields are necessary to enforce read-only/allowlist policies? Can malformed historical data remain inspectable? |
| Validation checks / command results | Which types are consumed by runtime gates versus presentation? What constitutes stale evidence? |
| Integers and versions | Which booleans/floats are accepted today through equality or `isinstance`, and would rejection break loading? |
| Visit/run cross references | Which inconsistent statuses, ordinals, targets, and timestamps are currently accepted? |
| Open terminal/block payloads | Which shapes are deliberately arbitrary user/configuration data and must remain open? |

Default decision for this plan: preserve version-1 acceptance beyond the narrow
status correction. A stricter reader requires a separate compatibility proposal
covering schema versioning, old-run reads, diagnostics, and any migration policy.
Never normalize or rewrite stored data merely to satisfy new annotations.

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
