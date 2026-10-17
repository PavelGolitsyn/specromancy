# Stage 08 — Verify integration and finish documentation

Prerequisites: all earlier stages. Do not defer their focused verification until
this stage; this is the final cross-boundary check.

Status: completed on 2026-10-04. Execution started from clean commit
`21b870db3f9081995426a3a4d9d31321dea1324b`. No runtime, canonical workflow,
generated files, schemas, or captured baseline records changed in this stage.

## Purpose

Confirm that the refactoring improved responsibility boundaries without changing
how users run pipelines, recover interruptions, approve artifacts, or regenerate
adapters. Update documentation to describe the final code rather than only this
proposed structure.

## Files and outputs

- Update `docs/reference/architecture.md` with the final dependency/responsibility map.
- Update `docs/reference/contracts.md` and `cli.md` if clarification is needed, keeping
  the existing public contract explicit and recording any separately approved
  behavior changes rather than describing them as mechanical moves.
- Update `tests/README.md` for genuinely new fixture/test organization.
- Update this plan's stage checklists and evidence; retain the original baseline.
- Touch generated paths only if canonical inputs intentionally changed in an
  independently justified change and normal ownership-safe generation permits it.

## Work items

- [x] Replay Stage 01 version-1 fixtures through the final implementation. Verify
  active, pending, approved, paused, terminal, and recoverable states remain usable.
- [x] Compare canonical pipeline bytes/hashes, action packets, error envelopes,
  event traces, and adapter outputs against baseline expectations. Investigate
  all differences before adjusting expected values.
- [x] Audit dependency direction: models/validators are leaves; persistence does
  not depend on engine/CLI; state decisions do not perform IO; adapter rendering
  does not implement workflow policy.
- [x] Remove obsolete private code and duplicated implementations only after all
  callers have moved. Keep documented/public compatibility aliases; do not remove
  them as cleanup without a separate deprecation decision.
- [x] Review tests for meaningful behavior, fixture independence, and recursive
  architecture coverage. Avoid introducing dependence on shipped phase names in
  generic tests or new tests that only assert an internal helper was called.
- [x] Run compatibility checks on Python 3.11 and the current development Python.
  Record unavailable interpreters as unverified instead of claiming full coverage.
- [x] Run source-export/launcher tests and confirm no third-party runtime imports
  were added. Confirm the CLI still works without package installation.
- [x] Inspect changes for ownership violations or unrelated edits. Do not stage,
  commit, reset, or delete user work as a side effect of verification.
- [x] Record separately deferred defects and enhancements with concrete evidence,
  affected contracts, and suggested follow-up scope.

## Final verification commands

```sh
python -m unittest discover -s tests/engine -t .
python -m unittest discover -s tests/shipped_configuration -t .
python -m unittest discover
bin/specromancy adapters generate --check
git diff --check
git status --short
```

The split runs help diagnose fixture/configuration coupling. If they have already
passed for the unchanged final revision, do not repeat them unnecessarily; the
full suite is the required final gate. Use `python3` when that is the interpreter
available locally, and record the exact version.

## Completion evidence

The final suite includes the extended replay assertions described below.

| Gate | Required evidence | Result |
| --- | --- | --- |
| Python 3.11 | Full-suite result and interpreter version | Python 3.11.15: 223 passed, 22.750 s; launcher PATH uses the same interpreter |
| Development Python | Full-suite result and interpreter version | Python 3.14.4: 223 passed, 26.551 s |
| Persisted compatibility | Fixture replay and trace comparisons | All 8 Stage 01 states load; continuation, exact bytes/hashes, responses, diagnostics, and recovery-once checks pass on both interpreters |
| CLI/launcher | Contract and fresh-export tests | CLI, module/script launchers, adapter entry point, and fresh source export pass on both interpreters without installation |
| Generated files | Drift check plus deterministic fixture generation | Checkout check passes; fixture generation bytes/hashes and repeated-generation checks pass; no checkout regeneration |
| Architecture | Generic policy/dependency/ownership checks | Recursive policy/subprocess/stdlib scans, isolated imports, safety and ownership tests pass; dependency audit below |
| Documentation | Final file map and unchanged public contracts reviewed | Architecture, contracts, CLI, test guide, and plan status updated; no new runtime behavior |
| Scope | Diff has only planned or explicitly justified changes | Six documentation files and one compatibility test; no runtime, fixture, workflow, adapter, or unrelated edits |

### Commands and environment

The feature and shipped-configuration groups passed independently before the
replay assertion extension: 207 tests in 13.086 s and 16 tests in 13.961 s,
respectively. The focused final replay passed all 7 tests in 0.210 s. Both final
full-suite runs then included those assertions and both groups:

```sh
python3 -m unittest discover -s tests/engine -t .
python3 -m unittest discover -s tests/shipped_configuration -t .
python3 -m unittest tests.engine.contract.test_compatibility
python3 -m unittest discover
env PATH="/Users/sg/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin:$PATH" \
  /Users/sg/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3 -m unittest discover
bin/specromancy adapters generate --check
git diff --check
git status --short
```

The development `python3` is Python 3.14.4 under
`/Library/Frameworks/Python.framework/Versions/3.14/bin/`. The shell still has
no default `python` executable. Python 3.11.15 was found in the existing uv
interpreter directory; no interpreter or dependency was installed. Placing its
`bin` directory first on PATH also tests exported `env python3` launchers with
3.11. Historical earlier-stage limitations remain unchanged; this final run
supplies the previously missing minimum-version evidence.

### Compatibility and dependency audit

The original Stage 01 baseline remains untouched. `test_compatibility` compares
canonical JSON (including non-ASCII encoding and pause default omission), full
action/approval/pause/block/terminal envelopes, error locations and streams,
complete manifest/event/artifact bytes, and adapter bytes/source hashes.
No baseline differences required investigation or expected-value changes.

Replay now also activates the restored pending fixture, retries restored active
and recovered visits without extra events, grants a restored pending approval,
and resumes a paused fixture through terminal completion. These assertions use
the original recorded responses and persisted bytes; only the existing clock
seam is frozen for approval. Approved-before-advancement replay still preserves
its bound outcome, terminal replay stays unchanged, and the recoverable fixture
still appends exactly one recovery event. All fixture writes remain temporary.

The dependency audit checked imports and callers in the extracted modules:

- Configuration models, record types/selectors, and persisted-data validation
  remain below loaders, engine, CLI, and storage. Schema algorithms are separate
  from artifact validation; the existing schema-file loader intentionally reads IO.
- `run_persistence` has one commit/reconciliation implementation and depends on
  locks, hashing, records, errors, and validators, never engine/CLI/responses.
  `RunStore` retains path and artifact ownership and supplies observations to
  `visit_transitions`; decision and approval-state functions perform no IO.
- Engine collaborators separate evidence collection, provenance, pure approval
  changes, and response construction. Store commits validate current persisted
  state under a lock; this does not imply a lock across engine command validation.
- Adapter source capture, rendering, and ownership are separate. Rendering
  projects canonical procedures and command metadata without graph policy;
  ownership enforces preflight, stale-hash rechecks, and manifest-last writes.

No obsolete duplicate implementation remained to remove. Existing facade
delegates and compatibility aliases are retained, including the validation
delegates documented in Stage 03 and the engine selector/fault-injection seams.
Artifact, run-manifest, and adapter writers retain their distinct ownership,
fault-hook, and durability policies; their superficially similar writes were
not consolidated into an unproven shared implementation.

Recursive `runtime_sources` coverage includes nested modules and package
initializers; the only phase-name exemption remains the exact `adapters.py`
facade, not its extracted internals. Isolated-import tests exercise the new
boundaries without eager package exports masking cycles. Generic behavior tests
use test-owned workflows, including the independent compatibility capture;
shipped tests check the editable checkout's consistency. Existing decision tables,
fault/interleaving tests, safety tests, and generated-output checks were retained
instead of adding tests that mirror helper calls.

Documentation now describes the final module map, store versus persistence
responsibilities, input binding at preparation, and load-time recovery for
`status`/`resume`. These clarify existing behavior. Stage 07's already documented
optional adapter metadata argument remains the only additive API convenience
from that stage; closeout introduces no behavior change.

### Deferred defects and enhancements

These are follow-ups to existing behavior, not failed closeout gates or claims
of new regressions:

| Follow-up | Concrete evidence and affected contract | Suggested scope |
| --- | --- | --- |
| Concurrent approval grant assertion | `test_visit_transition_store.test_overlap_before_approval_grant_exposes_existing_assertion`: a second attempt completes before the first grant callback; `approvals.granted_state` asserts when its pending record is absent. The winning manifest/events remain intact, but the losing command lacks a controlled retry/conflict diagnostic. | Separately define and test grant idempotency/conflict handling under the store lock, preserving outcome binding and revision/event counts; see Stage 05. |
| Weak persisted nested validation and diagnostic gaps | `test_run_records.test_legacy_weak_validation_is_not_silently_tightened` and the Stage 03 schema comparison document accepted malformed metadata, boolean/integer differences, and open approval objects. Unhashable status values can raise `TypeError` rather than corruption diagnostics. | Review accepted-version-1 compatibility and strengthen nested/cross-record validation with explicit structured diagnostics; do not silently replace it with the artifact schema subset. |
| Partial initialization recovery | `test_run_persistence.test_create_faults_leave_request_and_do_not_clean_up_partial_run` covers all six commit fault points; pre-replacement faults retain request/directory without a manifest. Stage 04 also characterizes a revision-1 run without a visit between creation and preparation. | Define an explicit, ownership-safe initialization resume/recovery contract; never rewrite history or automatically delete user work. |
| Validation evidence across concurrent edits | Stage 05 interleavings cover matching/conflicting outcomes, not arbitrary edits between `validation_service` observations and `RunStore.transition_visit`. Engine validation occurs outside the commit lock. | Investigate with deterministic file-edit interleavings before selecting evidence revalidation or revision/hash preconditions; currently an unverified race window, not a newly demonstrated defect. |

The pre-refactoring planning baseline and each earlier stage's dated results are
preserved. Stages 01–08 are complete with all required closeout gates passing.

## Exit criteria and rollback

All required gates pass, public contracts are documented, generated output is
reproducible, and no unrelated content changed. Report completed stages and
remaining limitations using evidence rather than a file-size reduction target.
If an integration regression appears, identify and repair or revert the smallest
responsible code change. Do not migrate or rewrite runs to make compatibility
tests pass, and do not delete old public entry points just to make the new layout
look cleaner.
