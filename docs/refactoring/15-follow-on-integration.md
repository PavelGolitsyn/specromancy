# Stage 15 — Verify integration and hand off deferred work

Status: complete on 2026-10-06. Prerequisites: stages 09–14 complete.
Category: integration, documentation, and release evidence.

## Objective

Verify the follow-on boundaries as one system, show exactly which behaviors
changed, and leave a usable record for future work. Each earlier stage must
already have passed its own checks; this stage is not a substitute for them.

## Work sequence and files

1. Replay the original compatibility fixtures through the final code using
   `test_compatibility.py`. Continue restored pending, active, granted, paused,
   terminal, and recoverable runs. Sequential bytes, hashes, packets, and
   diagnostics must still match their unchanged captures.
2. Review Stage 13 overlap traces and Stage 14 malformed-status diagnostics as
   the only intended behavior corrections. Link each difference to its test and
   public-contract description; investigate any additional change.
3. Audit imports and responsibility ownership. Field parsing must not depend on
   engine/storage; visit preparation may read resources but not persist; pure
   approvals/transitions must not perform IO; services must not import Engine;
   persistence must remain independent of CLI responses and workflow phase names.
4. Confirm facade imports, error identity, injected clocks/fault points, source
   export, and standard-library-only execution still work. Remove abandoned
   duplicate implementations, retaining compatibility delegates that are required.
5. Update `docs/poc-v3/architecture.md`, `contracts.md`, `cli.md` where relevant,
   and `tests/README.md`. Describe actual code and behavior, not proposed modules
   that were omitted during implementation.
6. Record exact interpreter versions, commands, results, and changed paths here.
   Mark completed stage checklists and update the refactoring index. Preserve
   earlier evidence and explicitly document any skipped or revised scope.

## Final verification

```sh
python -m unittest discover -s tests/features -t .
python -m unittest discover -s tests/shipped_configuration -t .
python -m unittest discover
bin/specromancy adapters generate --check
git diff --check
git status --short
```

Run the full suite on Python 3.11 and the available development Python. Put the
selected interpreter's directory first on PATH so subprocess `python3` launchers
exercise the same version. Use an available `python3` spelling when necessary;
record unavailable interpreters as unverified. Do not install new dependencies
or claim historical test results apply to changed code. If split groups already
passed for the final unchanged revision, avoid repeating them unnecessarily.

Generated adapters should remain byte-identical because this plan does not
change their canonical inputs or metadata. A drift failure must be investigated,
not fixed by blindly regenerating. Keep generation experiments in temporary
fixture repositories and review ownership behavior there.

## Deferred investigations and completion boundaries

These items are not implicitly included as implementation work in stages 09–15.
Each requires a separate scoped design after collecting the listed evidence.

| Follow-up | Current evidence | Required investigation and decision |
| --- | --- | --- |
| Validation evidence across edits | `perform_validation` observes files/commands/mutation state outside the store commit lock; the closeout calls the race unverified | Deterministically edit output/repository after validation but before transition; establish whether validated bytes differ from sealed bytes. Compare revision/hash preconditions and revalidation approaches; a run lock alone does not prevent external edits. Define retry/event behavior before implementing. |
| Interrupted initialization | `test_create_faults_leave_request_and_do_not_clean_up_partial_run`; creation and first preparation are separate commits | Enumerate directory-only, request-only, manifest/event-gap, and revision-1-without-visit states. Define recoverable versus corrupt states, idempotent continuation, and path ownership without deleting artifacts, guessing user intent, or rewriting events. |
| Strong nested record validation | Stage 14 matrix and deliberately permissive version-1 tests | Decide accepted old-run behavior and schema/version policy; define controlled diagnostics for each tightened invariant. No opportunistic loader/schema replacement. |
| Broader engine callback interleavings | This plan only hardens approval operations | Characterize stale validation-evidence writes, block decisions, and command-log overlap before claiming command-level concurrency safety. Scope each demonstrated issue separately. |

## Completion record

| Gate | Evidence required | Result |
| --- | --- | --- |
| Minimum Python | Version, full-suite count/result, matching launcher PATH | Python 3.11.15: 249 passed in 29.182s; matching interpreter directory first on PATH |
| Development Python | Version and full-suite count/result | Python 3.14.4: 249 passed in 34.702s |
| Compatibility | Original fixture replay, facade/import checks | 9 compatibility tests passed; architecture, facade identities, source exports, and injection checks passed in both full suites; captures unchanged |
| Intentional corrections | Approval interleavings and malformed-status cases | All overlap/status cases passed in both full suites; traces and public-contract links below |
| Durability and safety | Recovery/fault tests, ownership and immutable-artifact tests | Persistence, transition, interruption, recovery, and safety suites passed on both interpreters |
| Adapters | Check mode and deterministic fixture generation | Check mode passed; deterministic generation and ownership tests passed in temporary fixture repositories; checkout adapters unchanged |
| Documentation and scope | Final module map, behavior changes, reviewed diff | Six documentation paths reviewed; `git diff --check` passed; no runtime, fixture, workflow, or generated changes |

## Exit criteria and rollback

- [x] All required gates pass for the final code, with limitations stated honestly.
- [x] Structural changes are distinguishable from the two intentional corrections.
- [x] Runtime remains generic, dependency-free, and Python 3.11 compatible.
- [x] No unrelated workflow, generated, or repository content changed.
- [x] Deferred investigations have evidence and decision criteria, not vague TODOs.

Rollback is a normal reviewed code change to the smallest responsible stage.
Do not stage, commit, reset, delete repository work, or rewrite user run artifacts
as a side effect of validation. The preserved formats allow old runs to remain
readable without a rollback migration.

## Stage 09 handoff

Stage 09 is complete; the [scoped decisions](09-follow-on-baseline.md#scoped-decisions)
remain the follow-up ledger. Stages 10–12 retain all identified imports, delegates,
clock/fault seams and sequential captures. Stage 13 has a decided request-identity,
conflict and audit-count table; Stage 14 has a three-category acceptance inventory
and concrete nested-validation dispositions. Neither correction is implemented
by the baseline stage. Minimum-Python execution remains a Stage 15 gate, not an
inference from the Stage 09 development-Python run.

## Execution record — 2026-10-06

Started from clean revision `11cd11d8b3e69dc59ae900580042c97fe08c1b06`.
Stages 09–14 already had completed focused/full-suite and adapter-check records;
their historical evidence is preserved. This stage audits and verifies their
combined result. No runtime change or new test was needed: existing tests cover
the integration gates, and no abandoned duplicate implementation was found.

### Responsibility and compatibility audit

| Boundary | Inspected implementation and retained contract |
| --- | --- |
| Configuration | `config_fields` imports only `config_errors` from the package; `config_phase_parser` uses the field context, models, command vocabulary, and schema reader. Neither imports engine/storage. `_Loader` inherits field checks and delegates phase parsing; facade helpers and class/error identities remain available. |
| Preparation | `visit_preparation.collect_resources` resolves inputs, checks collisions, then hashes skill/template resources without writing or mutating state. `RunStore._new_visit` owns identity and timestamps; preparation remains under the store lock. Sealed successor input resolution and retry skipping are retained. |
| Pure decisions | `approvals`, `command_decisions`, and `visit_transitions` consume supplied records, timestamps, and evidence. They contain no IO, clocks, or lock acquisition; detached proposals are committed by the store. |
| Services | `approval_service` receives pipeline/store plus validation and timestamp callbacks; it has no Engine dependency. `validation_service` collects evidence without committing. Engine's late-resolved validation/clock seams and approval delegates remain. |
| Persistence | `RunPersistence` imports locking, hashing, record validation/vocabulary, and errors, with no CLI/response/harness or workflow-phase dependency. One lock covers load/decision/commit; manifest replacement still precedes event append and permits exactly the documented recovery gap. |
| Compatibility delegates | Retained configuration facade exports, `_Loader` parser methods, Engine approval/selector methods, and RunStore validator/identity aliases. `requested_state` remains the shared helper used by `request_decision`; obsolete `granted_state`/`invalidated_state` implementations are absent. |

The architecture import tests independently load internal modules without eager
facade initialization. Compatibility replay checks canonical bytes/hashes,
response packets, diagnostics, adapters, and persisted records against original
captures, then continues pending, active, pending-approval, granted, paused,
terminal, and recoverable runs. Injection coverage checks store clocks/random
sources, Engine clock patches, validation hooks replaced after grant, command
faults, and manifest/event fault points. Release/launcher tests exercise an
uninstalled source export and recursively check standard-library imports.

### Intentional behavior corrections

All test paths below are relative to `tests/features/`. These are the only
intended behavioral differences; stages 10–12 changed responsibility ownership.
Original captures were neither rewritten nor regenerated.

| Correction and observed trace | Test evidence | Public contract |
| --- | --- | --- |
| Stage 13: an approve overtaken before grant returns the winning completion instead of the prior assertion; winner ends at revision/event 8/8 and loser preserves bytes. If the winner stops after grant at 7/7, continuation reaches 8/8 without another grant. | [`unit/test_visit_transition_store.py`](../../tests/features/unit/test_visit_transition_store.py): `test_overlap_before_approval_grant_returns_winning_completion`, `test_overlapping_grant_resumes_after_winner_stops_at_grant` | [Approval consistency](../poc-v3/contracts.md#approval-consistency) |
| Identical request creators preserve the winner's timestamp/evidence at 6/6; conflicts preserve its state. Stale duplicates add only one invalidation (7/7); replacements, ambiguous/missing bindings, and changed visits return `approval-state-changed` (5). | Same file: `test_two_fresh_identical_requests_keep_winning_timestamp_and_evidence`, `test_overlapping_request_creators_reuse_only_identical_binding`, `test_stale_overlap_duplicate_replacement_and_advancement`, `test_each_identity_field_and_ambiguous_record_conflicts_without_mutation`, `test_request_evidence_never_attaches_to_successor_with_same_phase` | [Approval consistency](../poc-v3/contracts.md#approval-consistency) |
| Completed approvals return current paused/pending/active/completed successor state without advancing it. Failed continuation retains the grant; retry uses its saved outcome. Interrupted approval commits recover once without inventing the missing approval event. | [`contract/test_compatibility.py`](../../tests/features/contract/test_compatibility.py): `test_overtaken_approval_returns_paused_or_successor_without_advancing_it`; [`contract/test_engine_orchestration.py`](../../tests/features/contract/test_engine_orchestration.py): `test_overtaken_grant_failure_retains_winner_and_retries_saved_outcome`; store overlap suite: `test_all_approval_commits_recover_once_without_replayed_event` | [Approval consistency](../poc-v3/contracts.md#approval-consistency) |
| Stage 14: list/object run and visit statuses now produce `RunCorruptionError`, `corrupt-run` (12), instead of unhashable `TypeError`. Other invalid status diagnostics retain their messages/order. All 18 value/level combinations are checked with complete and one-revision-behind logs (36 CLI cases), with unchanged file names/bytes. | [`unit/test_run_records.py`](../../tests/features/unit/test_run_records.py): `test_invalid_status_shapes_raise_corruption_without_mutation`; [`contract/test_cli.py`](../../tests/features/contract/test_cli.py): `test_malformed_status_fails_before_recovery_without_changing_files` | [Malformed persisted statuses](../poc-v3/contracts.md#malformed-persisted-statuses) |

Weak nested version-1 acceptance remains covered by
`test_legacy_weak_validation_is_not_silently_tightened` and
`test_nested_compatibility_matrix_remains_accepted_without_mutation`. A valid
manifest still recovers before a later artifact-verification failure, as checked
by `test_valid_manifest_recovers_before_artifact_verification_fails`; this is not
an additional correction. No additional behavior change was found in the audit
or compatibility replay.

### Verification commands and results

The available development interpreter is Python 3.14.4 at
`/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`.
The existing minimum interpreter is Python 3.11.15 at
`/Users/sg/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3`.
No `python` executable is on the default PATH, so the documented `python3`
equivalent is used. Each full-suite command puts the selected interpreter's
directory first on PATH, including for subprocess `env python3` launchers.
No interpreter or dependency was installed.

Commands executed from the repository root:

```sh
env PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:$PATH" python3 --version
env PATH="/Users/sg/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin:$PATH" /Users/sg/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3 --version
env PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:$PATH" python3 -c 'import shutil, sys; print(sys.version); print(sys.executable); print(shutil.which("python3"))'
env PATH="/Users/sg/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin:$PATH" /Users/sg/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3 -c 'import shutil, sys; print(sys.version); print(sys.executable); print(shutil.which("python3"))'
env PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:$PATH" python3 -m unittest discover -s tests/features -t .
env PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:$PATH" python3 -m unittest discover -s tests/shipped_configuration -t .
env PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:$PATH" python3 -m unittest tests.features.contract.test_compatibility
env PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:$PATH" python3 -m unittest discover
env PATH="/Users/sg/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin:$PATH" /Users/sg/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3 -m unittest discover
env PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:$PATH" bin/specromancy adapters generate --check
git diff --check
git status --short
```

| Check | Result |
| --- | --- |
| Interpreter and launcher resolution | Versions above; `sys.executable` and `shutil.which("python3")` both select the intended interpreter for each PATH |
| Feature group, Python 3.14.4 | 233 passed in 15.617s |
| Shipped-configuration group, Python 3.14.4 | 16 passed in 17.460s |
| Explicit original compatibility replay, Python 3.14.4 | 9 passed in 0.380s |
| Full suite, Python 3.14.4 | 249 passed in 34.702s |
| Full suite, Python 3.11.15 | 249 passed in 29.182s |
| Checkout adapter check | Passed: `generated adapters are up to date` |
| Diff whitespace and ownership review | Passed; final status contains only the six documentation paths listed below |

All gates used this stage's unchanged runtime and test sources. Full suites ran
after the public-documentation updates; subsequent edits only finalized this
execution record and the refactoring index. The already-passing split groups were
not repeated. Both full suites include generation/ownership checks in temporary
repositories, source-export execution, and the correction cases. Checkout adapter
generation was never run in write mode.

### Changed paths and scope

- `docs/poc-v3/architecture.md`: complete the store-to-approval dependency map
  and state the limits of approval locking and remaining investigations.
- `docs/poc-v3/contracts.md`: add direct anchors for the existing status and
  approval contracts and link the correction evidence.
- `docs/poc-v3/cli.md`: document overlap responses/conflicts and malformed-status
  diagnostics for CLI callers.
- `tests/README.md`: map final boundaries, compatibility, corrections, durability,
  generation, and release checks to their suites.
- `docs/refactoring/15-follow-on-integration.md`: record integration evidence,
  exact verification, completed gates, and scope.
- `docs/refactoring/README.md`: record completion of stages 09–15.

No scope expansion or skipped implementation work. The four deferred
investigations above remain separate design work with evidence and decision
criteria; this stage does not claim they are resolved. No runtime, test source,
fixture, schema, canonical workflow, generated adapter, dependency, or user run
artifact changed. No repository work was staged, committed, reset, or deleted.
