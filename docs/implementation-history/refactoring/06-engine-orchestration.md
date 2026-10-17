# Stage 06 — Reduce the engine to command orchestration

Status: implemented on 2026-10-04.

Prerequisites: Stages 02–05. Preserve public `Engine` methods and responses.

## Purpose and evidence

The engine currently constructs response envelopes, inspects provenance, runs
artifact/command/mutation validation, selects outcomes, and mutates approval
records. Approval handling deliberately loads persisted state before enforcing
pipeline equality so stale approval can be recorded. That ordering is part of
the behavior to preserve, not duplication to remove indiscriminately.

## Proposed file map

- `specromancy/engine.py`: public commands and their explicit orchestration order.
- `specromancy/engine_errors.py` (new): `EngineError`, re-exported by engine.
- `specromancy/provenance.py` (new): pipeline identity comparison and skill/template
  observations, with warning/error decisions left to the caller.
- `specromancy/validation_service.py` (new): the existing validation sequence and
  an internal result carrying checks, command results, mutation result, and failure.
- `specromancy/responses.py` (new): response envelopes using existing action/status
  builders; preserve their schema versions and messages.
- Existing `approvals.py`: retain hash-bound approval records and integrity checks;
  add cohesive pure approval selectors/decisions here only where useful.

## Work items

- [x] Extract response construction first. Keep `actions.py` and `status.py`
  focused on their present payloads/rendering rather than merging them into a
  generic response framework.
- [x] Extract provenance observations. Preserve strict command rejection,
  status warnings, and approval invalidation as three distinct uses of the same
  observations. Status must remain useful when artifact hashes have drifted.
- [x] Move `_perform_validation` with its current order: artifact validation,
  sequential commands, repository snapshot/mutation enforcement, then required
  command failure reporting. Mutation failure currently takes precedence when
  both command and mutation checks fail; preserve that decision order.
- [x] Return explicit validation evidence and failure details to orchestration.
  Ensure failed evidence is persisted once through `record_validation_attempt`
  before the corresponding expected error is returned. Preserve retriable state.
- [x] Keep command execution in `commands.py`: shell disabled, required failures
  stop the sequence, optional failures continue, timeout/missing executable
  results remain distinguishable, raw logs stay in run storage, and manifest
  summaries stay bounded and redacted.
- [x] Extract approval state changes using explicit records/timestamps, retaining
  the store mutation boundary. Preserve pending/approved/stale lookup semantics
  and binding to run, visit, artifact, pipeline, and selected outcome.
- [x] Preserve grant and advancement as recoverable operations. A process stopping
  after approval is granted must be able to resume advancement; revalidation
  must still run and can fail without erasing the approval audit history.
- [x] Keep artifact/pipeline mismatch invalidation durable before emitting the
  stale-approval response. Do not route approval through a strict general loader
  that rejects drift before invalidation can be recorded.
- [x] Retain existing clock/fault injection compatibility. Any new internal clock
  seam defaults to the same production source and does not change timestamp
  fields, ordering, or constructor call compatibility.

## Verification

```sh
python -m unittest tests.engine.unit.test_engine tests.engine.unit.test_validation tests.engine.unit.test_git
python -m unittest tests.engine.contract.test_safety tests.engine.contract.test_interruptions tests.engine.contract.test_recovery
python -m unittest tests.engine.contract.test_cli tests.engine.contract.test_multi_pipeline
python -m unittest discover
bin/specromancy adapters generate --check
```

Compare action/status/approval/error payloads against Stage 01. Include stale
pending and granted approval, changed pipeline, missing output, provenance drift,
failed revalidation, blocked repeat, terminal repeat, and paused resume. Run a
validation command that changes a protected file to confirm mutation checks still
occur after command execution. Preserve command-output fault hooks.

## Exit criteria and rollback

The engine visibly coordinates named responsibilities, while no helper becomes
a second hidden engine. Validation and approval failures retain evidence and
the same durable state. Response schemas, messages, codes, and idempotency remain
compatible. Deliver response/provenance moves before validation/approval moves
so each can be reverted without unravelling the whole stage.


## Implementation record

Response construction was extracted first into `responses.py`, leaving action
packets and status projections in their existing modules. `EngineError` now
lives in `engine_errors.py` and is re-exported from `engine` and the package;
`engine.RESPONSE_SCHEMA_VERSION` remains available. Public command signatures,
response schemas, messages, diagnostics, and constructor arguments are unchanged.

`provenance.py` provides pipeline identity comparison and skill/template
observations. The engine still decides whether to reject a command, attach
status warnings, or invalidate approval. In particular, `approve` still loads
persisted state before checking current pipeline identity, and `status` still
loads without artifact verification before collecting warnings.

`validation_service.py` returns explicit checks, command results, mutation
results, and expected failure/cause details. It does not import the engine or
store. The engine persists a failed attempt exactly once before raising the
returned error. Artifact validation, sequential commands, snapshot capture,
mutation enforcement, and required-command failure reporting retain their order.
`commands.py` and its output fault hooks were unchanged.

`approvals.py` contains pure selectors and detached pending/granted/stale state
changes. Engine callbacks apply these changes to the freshly loaded manifest
inside `RunStore.mutate`; clocks, event names/payloads, and durable writes remain
in orchestration. Grant and advancement remain separate recoverable operations.
No internal clock was added: approval timestamps still use `engine.utc_now`,
preserving the existing patch seam and call ordering.

The first full-suite run exposed tests using the private `_perform_validation`,
`_pending_approval`, and `_approved_record` entry points. These entry points were
retained as thin orchestration/selector delegates, preserving existing overlap
injection coverage without restoring the extracted implementation. The internal
validation return value is now a named evidence record.

### Verification

Python 3.14.4 was used via `python3` because this shell has no `python` executable.

- Engine, artifact validation, and Git unit checks: **20 passed**.
- Safety, interruption, and recovery contracts: **17 passed**.
- CLI and multi-pipeline contracts: **10 passed**.
- Architecture isolation, compatibility baseline, and initial orchestration
  regressions: **18 passed**.
- Record selectors, overlapping transitions, compatibility, and initial
  orchestration regressions after preserving the private seams: **27 passed**.
- All **5 new orchestration contract tests** also passed against the original
  Stage 05 engine loaded from a temporary source copy. These cover blocked and
  terminal repeats; stale pending/granted approvals after artifact, missing
  output, and pipeline drift; failed revalidation retaining the grant through
  retry; provenance warnings/rejections and readable status after input drift;
  and one persisted retriable missing-artifact failure.
- Stage 01 response/error envelopes and complete persisted fixture bytes match
  without regenerating the compatibility fixtures. Existing tests cover paused
  resume, command-induced protected-file changes (including a failing command),
  optional command continuation, timeout/missing executable distinctions,
  redacted summaries, raw logs, and command-output interruption.
- Final `python3 -m unittest discover`: **215 passed** in 24.930 seconds.
- `bin/specromancy adapters generate --check`: passed; no generated writes.
- `git diff --check`: passed.

### Deviations and deferred issues

No scope or public contract deviation. The existing pre-grant overlapping
approval assertion documented in Stage 05 remains characterized and deferred;
this extraction does not alter concurrency policy or claim protection against
arbitrary concurrent file edits. No workflow, adapter, command runner, or store
implementation was changed.
