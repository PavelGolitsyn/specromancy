# Stage 06 — Reduce the engine to command orchestration

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

- [ ] Extract response construction first. Keep `actions.py` and `status.py`
  focused on their present payloads/rendering rather than merging them into a
  generic response framework.
- [ ] Extract provenance observations. Preserve strict command rejection,
  status warnings, and approval invalidation as three distinct uses of the same
  observations. Status must remain useful when artifact hashes have drifted.
- [ ] Move `_perform_validation` with its current order: artifact validation,
  sequential commands, repository snapshot/mutation enforcement, then required
  command failure reporting. Mutation failure currently takes precedence when
  both command and mutation checks fail; preserve that decision order.
- [ ] Return explicit validation evidence and failure details to orchestration.
  Ensure failed evidence is persisted once through `record_validation_attempt`
  before the corresponding expected error is returned. Preserve retriable state.
- [ ] Keep command execution in `commands.py`: shell disabled, required failures
  stop the sequence, optional failures continue, timeout/missing executable
  results remain distinguishable, raw logs stay in run storage, and manifest
  summaries stay bounded and redacted.
- [ ] Extract approval state changes using explicit records/timestamps, retaining
  the store mutation boundary. Preserve pending/approved/stale lookup semantics
  and binding to run, visit, artifact, pipeline, and selected outcome.
- [ ] Preserve grant and advancement as recoverable operations. A process stopping
  after approval is granted must be able to resume advancement; revalidation
  must still run and can fail without erasing the approval audit history.
- [ ] Keep artifact/pipeline mismatch invalidation durable before emitting the
  stale-approval response. Do not route approval through a strict general loader
  that rejects drift before invalidation can be recorded.
- [ ] Retain existing clock/fault injection compatibility. Any new internal clock
  seam defaults to the same production source and does not change timestamp
  fields, ordering, or constructor call compatibility.

## Verification

```sh
python -m unittest tests.features.unit.test_engine tests.features.unit.test_validation tests.features.unit.test_git
python -m unittest tests.features.contract.test_safety tests.features.contract.test_interruptions tests.features.contract.test_recovery
python -m unittest tests.features.contract.test_cli tests.features.contract.test_multi_pipeline
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
