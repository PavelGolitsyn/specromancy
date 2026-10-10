# Stage 01 — Establish a compatibility baseline

Prerequisites: none. Deliver this before moving runtime code.

Status: implemented on 2026-10-03; runtime unchanged. Execution started from
`7f8aafab4a4f7b6597fded823deb5cd49889450f` with a clean checkout.

## Purpose and evidence

The repository already has extensive unit, CLI, safety, recovery, and generated
adapter tests. The first task is to identify gaps relevant to extraction, not
replace that suite. `test_architecture.py` lists specific generic modules, while
its subprocess scan and `test_release.py` use nonrecursive source globs. Moving
code can otherwise make checks pass by taking code outside their coverage.

The planning inspection used commit
`594c2983895903f09ac15f4b1d12a9309d39bbf8`, Python 3.14.4, and a clean checkout.
`bin/specromancy adapters generate --check` passed. The planning-time full-suite
baseline passed: `python3 -m unittest discover` ran 166 tests in 22.515 seconds.
The repository-prescribed `python -m unittest discover` could not start because
the shell has no `python` executable. Python 3.11 was not exercised during planning.
These results establish the current baseline, not completion of this stage's
future characterization work.

## Files and outputs

- Update `tests/features/contract/test_architecture.py` and `test_release.py`.
- Extend existing config, run-store, engine, CLI, and adapter tests only where
  the matrix below is not already covered.
- Add small compatibility fixtures under
  `tests/features/fixtures/refactoring-compatibility/` if captured records are
  needed. Keep all new fixture data independent of shipped workflow settings.
- Record command results and compatibility decisions in this document.

## Work items

- [x] Inventory documented imports in `specromancy/__init__.py`, module-level
  aliases, constructor injection points, and externally exercised methods.
  Include `load_config`, hash helper aliases, run-store aliases, and artifact
  aliases even when they are absent from `__all__`.
- [x] Make source scans recursive, with explicit justified exclusions for
  harness-specific boundaries. Test newly extracted generic modules too; retain
  the separation between workflow policy and runtime behavior.
- [x] Map each contract below to an existing test and add only missing cases.
- [x] Capture representative canonical pipeline strings and expected hashes,
  including non-ASCII text, absent defaults, `pause = false`, and `pause = true`.
- [x] Capture representative action, approval, paused, blocked, terminal, and
  error envelopes, retaining meaningful ordering and exact diagnostic fields.
- [x] Prepare version-1 persisted examples for active, pending, approved-but-not-
  advanced, paused, completed, and recoverable states. Obtain them through the
  baseline API in isolated fixtures; do not manufacture valid history by editing
  an actual user's state.
- [x] Use fixed clocks/random sources where supported. Normalize only documented
  volatile fields such as temporary roots and command durations. Never normalize
  away revisions, hashes, event types, outcomes, or decision order.

## Required behavior matrix

| Boundary | Evidence required |
| --- | --- |
| Configuration | Exact canonical bytes and hashes; stable rejection codes and locations; bounded graph validation; supported schema subset |
| Run commits | Pre-replacement failure preserves old state; permitted post-replacement gap recovers once; malformed or inconsistent history rejects |
| Visits | Distinct loop outputs; literal input resolution at the existing lifecycle point; idempotent retries; pause/resume; atomic successor preparation |
| Approval | Artifact and pipeline drift invalidate; approval can recover after grant before advancement; approved outcome stays bound |
| Mutation safety | Clean and already-dirty edits detected; symlink/mode behavior; allowlists; command-induced changes checked |
| CLI | Both launchers; flags before/after commands; one JSON object; stream routing; help without registry; dynamic aliases and explicit selection |
| Multi-pipeline | Registry reordering and unrelated edits do not alter a run; removed registration still allows recorded-path access |
| Adapters | Stable bytes/hashes; no writes in check mode; protection of unowned/modified files; stale manifest-owned cleanup only |

Tests supporting this matrix already exist in `tests/features/unit/` and
`tests/features/contract/`; use their current assertions as the starting point.
Investigate race windows and unsupported malformed inputs separately from the
behavior-preserving extraction baseline.

## Verification

```sh
python -m unittest tests.features.contract.test_architecture tests.features.contract.test_release
python -m unittest tests.features.unit.test_config tests.features.unit.test_run_store tests.features.unit.test_engine
python -m unittest discover
bin/specromancy adapters generate --check
python -m unittest tests.features.contract.test_compatibility tests.features.contract.test_safety
```

Run version-sensitive checks on Python 3.11 and the current development
interpreter when available. A pass on 3.14 alone does not establish the minimum
supported version.

## Compatibility inventory and decisions

Keep existing import paths and callable signatures during extraction. The
inventory includes intentionally exposed aliases, even outside `__all__`; it
does not promote underscored helpers to public APIs.

| Surface | Contracts to retain |
| --- | --- |
| Package exports | `ExitCode`, `Engine`, `EngineError`, `PipelineConfig`, `PipelineConfigError`, `PipelineRegistry`, `PipelineRegistration`, `RunCorruptionError`, `RunNotFoundError`, `RunStore`, `generate_run_id`, `load_pipeline`, `load_registry`, `validate_run_id`; `__version__` remains release metadata |
| Configuration | `load_pipeline(path, repository_root=None)`, its `load_config` wrapper, `canonicalize_pipeline`, `hash_pipeline`, `require_pipeline_hash`; immutable `ValidationCommand`, `ValidatorConfig`, `TransitionConfig`, `PhaseConfig`, `PipelineConfig`; `phase`, `phase_ids`, `hash`, `validation_commands` properties; diagnostic attributes and `as_dict()` |
| Hashing | `canonical_json_bytes`, `sha256_bytes/text/json/file`, `hash_bytes/text/json/file` aliases, path normalization/resolution helpers; pipeline canonicalization escapes Unicode, while generic JSON hashing emits UTF-8 |
| Store aliases | `new_run_id = generate_run_id`, `CorruptRunError = RunCorruptionError`; `create_run = create`, `load_run = load`, `create_visit = start_visit`, `update = mutate`; `is_valid_run_id`, `format_timestamp`, `utc_now`, `RunStoreError` remain available in their modules |
| Store methods | `new_run_id`, `run_directory`, `lock`, `create`, `load`, `read_events`, `start_visit`, `prepare_visit`, `activate_visit`, `write_visit_output`, `record_validation_attempt`, `complete_visit`, `transition_visit`, `resume_paused`, `mutate`, `block`, `complete`; preserve `recover` and `verify_artifacts` load options |
| Artifact helpers | `ArtifactError`, `render_output_path`, `artifact_record`, `resolve_input_reference`, `verify_manifest_artifacts`, `write_artifact_atomic`; aliases `resolve_artifact_reference` and `verify_artifacts` |
| Engine commands | `initialize`, `start_phase`, `validate`, `request_approval`, `approve`, `block`, `status`, `resume`, `run`; preserve errors, envelopes, outcome/input ordering and approval decision order |
| Other exercised boundaries | `PipelineRegistry.load/load_all/canonical_json`, `load_registry`; `cli.main`, `build_parser`, `discover_repository_root`, `adapter_command_metadata`, `RESERVED_COMMANDS`; `generate_adapters`, `AdapterError`, `MANIFEST_PATH`; graph traversal helpers; validation/schema helpers and errors; `execute_validation_commands`; Git snapshot/comparison/enforcement helpers, `GitError`, `snapshot_repository` alias; `RunLock`, `LockHeldError` |

Injection contracts are `RunStore(repository_root, *, clock, random_source,
fault_injector)`, `generate_run_id(*, clock, random_source)` (including random
callables accepting zero arguments), `Engine(pipeline, store=None, *,
command_fault_injector)`, `RunLock(path, *, clock)`, and
`execute_validation_commands(..., summary_bytes=..., fault_injector=...)`.
`cli.main(argv=None, *, stdout=None, stderr=None)` supports injected streams.
Existing tests also replace a store's `_fault_injector`; retain this test seam
while extracting the commit protocol. Engine timestamps currently call its
module-level `utc_now`; the new fixture freezes that reference without adding
a runtime constructor parameter.

Source discovery now shares recursive `rglob("*.py")` coverage across workflow
policy, subprocess and standard-library dependency checks, including nested
package initializers. Only the exact `adapters.py` file is excluded from the
phase-name check because harness rendering is its explicit boundary. It is
still scanned for subprocess and dependency constraints; adapter policy has
separate behavioral checks. Newly extracted modules are included by default;
no directory-wide exclusion is granted to future adapter internals.

The baseline records and capture/replay policy are documented in
[`refactoring-compatibility/README.md`](../../tests/features/fixtures/refactoring-compatibility/README.md).
No runtime, shipped configuration, canonical procedures, or generated adapter
files changed. Snapshots do not involve live runs. Fixed records cover default
omission and non-ASCII canonicalization, both pause values, all requested
envelopes and version-1 states, and exact adapter bytes/hashes.

## Named evidence for every matrix row

Names below are relative to `tests.features`; each method is prefixed with
`test_` in the source. Existing tests were retained rather than duplicated.

| Boundary | Named evidence |
| --- | --- |
| Configuration | `contract.test_compatibility`: `canonical_pipeline_bytes_and_hashes_match_baseline`, `exact_error_envelopes_locations_and_cli_streams`; `unit.test_config`: `hash_is_stable_across_toml_key_order`, `unbounded_cycle_is_rejected`, `parallel_unbounded_edge_does_not_borrow_another_outcomes_bound`, `input_producer_must_dominate_all_incoming_routes`, `unsupported_json_schema_keyword_is_rejected_at_load`; `unit.test_validation`: `json_subset_accepts_and_rejects_values` |
| Run commits | `unit.test_run_store`: `before_replace_fault_preserves_the_previous_complete_manifest`, `after_replace_fault_is_recovered_with_an_audit_event`, `valid_but_unaudited_manifest_edit_is_detected_as_corruption`, `malformed_manifest_is_never_guessed_back_into_shape`, `event_log_corruption_is_never_guessed_back_into_shape`; `contract.test_compatibility`: `version_one_records_replay_and_recovery_is_exactly_once`; `contract.test_interruptions`: `manifest_faults_before_replace_preserve_previous_state` |
| Visits | `unit.test_run_store`: `repeated_phase_visits_have_distinct_ordinals_paths_and_attempts`, `symbolic_inputs_fail_safely_and_resolve_only_completed_outputs`; `unit.test_engine`: `happy_path_is_generic_and_idempotent`, `paused_transition_requires_atomic_explicit_resume`, `paused_resume_recovers_around_atomic_manifest_replacement`, **new** `successor_inputs_and_completion_commit_in_one_revision`; `contract.test_compatibility`: `response_envelopes_and_persisted_bytes_match_baseline` |
| Approval | `contract.test_safety`: `artifact_edit_invalidates_pending_approval`, `pipeline_edit_invalidates_pending_approval`; `unit.test_engine`: `approval_binds_hash_and_advances_once`; `contract.test_compatibility`: `version_one_records_replay_and_recovery_is_exactly_once` resumes the granted approval into its bound `z-next` outcome despite the alternate `a-stop` outcome, and `exact_error_envelopes_locations_and_cli_streams` preserves artifact/pipeline mismatch order |
| Mutation safety | `contract.test_safety`: `real_git_read_only_phase_rejects_clean_and_preexisting_dirty_edits`, **new** `command_mutation_is_checked_before_required_command_failure`; `unit.test_git`: `content_snapshot_detects_dirty_untracked_delete_rename_and_mode`, `symlink_target_is_hashed_without_following_it`, `read_only_and_allowlist_enforcement`, `read_only_rejects_index_head_and_branch_only_changes`, `allowlist_never_allows_git_metadata_changes` |
| CLI | `contract.test_launcher`: `launcher_imports_local_package_from_nested_directory`, `module_entry_point_uses_the_same_help`; `contract.test_multi_pipeline`: `common_option_positions_and_description_file`, `init_requires_registered_id_even_for_one_pipeline`, `alias_and_selector_cannot_switch_a_runs_graph`; `contract.test_cli`: `fresh_process_drives_full_run_with_dynamic_alias`; `unit.test_cli`: `json_help_is_exactly_one_object`, `json_error_has_stable_shape`; `contract.test_compatibility`: `exact_error_envelopes_locations_and_cli_streams` |
| Multi-pipeline | `contract.test_multi_pipeline`: `unrelated_graph_edits_and_registry_reordering_preserve_run`, `removed_registration_disables_init_and_preserves_existing_run`, `fresh_processes_complete_two_graphs_using_recorded_selection`, `overlapping_phase_names_keep_pipeline_provenance` |
| Adapters | `contract.test_compatibility`: `generated_adapter_bytes_and_hashes_match_baseline`; `unit.test_adapters`: `two_generations_are_byte_identical`, `check_detects_changes_without_writing_generated_output`, `generation_never_overwrites_an_unowned_destination`, `stale_unchanged_file_is_removed`, `stale_modified_file_is_preserved_with_an_error`, `tampered_manifest_cannot_claim_an_unrelated_path`; `unit.test_multi_pipeline_adapters`: `unowned_and_modified_stale_native_skills_are_preserved`, `manifest_cannot_claim_a_canonical_skill`; `contract.test_adapter_drift`: `generated_adapters_contain_no_workflow_logic` |

No production correctness defect was found in these characterization scenarios.
Race-window exploration, unsupported malformed nested records, and interrupted
initialization remain outside this extraction baseline, as specified by the
parent plan. Python 3.11 verification remains an environment limitation, not a
claim established by the development-interpreter results.

## Execution results

All commands ran from the repository root on 2026-10-03. The shell still has
no `python` executable, so verification used Python 3.14.4 via `python3`, as
permitted by the parent plan. Python 3.11 was not on PATH or in the installed
framework/Homebrew/local interpreter locations; it was not installed for this
test-only stage.

| Command | Result |
| --- | --- |
| `python -m unittest discover` | Could not start: `python` not found |
| `python3 -m unittest discover` before changes | 166 tests passed, 22.271 seconds |
| `python3 -m unittest tests.features.contract.test_architecture tests.features.contract.test_release` | 10 tests passed, 0.468 seconds |
| `python3 -m unittest tests.features.unit.test_config tests.features.unit.test_run_store tests.features.unit.test_engine` | 54 tests passed, 0.305 seconds |
| `python3 -m unittest tests.features.contract.test_compatibility tests.features.contract.test_safety` | 15 tests passed, 1.377 seconds |
| `python3 -m unittest discover` after changes | 175 tests passed, 22.532 seconds |
| `bin/specromancy adapters generate --check` | Passed: generated adapters are up to date |
| `git diff --check` | Passed |

The three captured pipeline hashes are:

- Omitted pause and explicit false:
  `afc26c5846a111af2dbc104e98647ae2959d198de6b601e0bea8e44b8e349efe`.
- Explicit true:
  `955de83d8f9589493e5a14402d0b4cb8a5f4dc8c423869acdc44eca9a09db525`.

All available gates passed. Nine tests were added; existing feature, release,
and shipped-configuration tests still pass. Minimum-version execution remains
to be performed on a host with Python 3.11 before claiming that verification.

## Exit criteria and rollback

Every matrix row has named test evidence; new source modules cannot evade
architecture checks; baseline generated bytes and pipeline hashes are captured.
The full suite passes without runtime behavior changes. If baseline failures
exist, document and resolve them before using this stage as an equivalence gate.
This stage is reversible as a test/documentation change and writes no live runs.
