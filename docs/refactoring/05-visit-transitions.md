# Stage 05 — Separate visit decisions from persistence

Prerequisite: Stage 04. Preserve the `RunStore` API and commit boundaries.

Status: implemented on 2026-10-04; no migration or adapter regeneration required.

## Purpose and evidence

`prepare_visit`, `activate_visit`, `complete_visit`, `transition_visit`,
`resume_paused`, `_new_visit`, and `_transition_limit_block` currently mix state
decisions with hashing, reading artifacts, and committing records. Extract
decisions that can be evaluated with explicit inputs while keeping filesystem
observations inside the appropriate locked operation.

## Proposed file map

- `specromancy/visit_transitions.py` (new): visit record construction from resolved
  inputs, status guards, limit decisions, and successor/terminal state changes.
- `specromancy/run_store.py`: compatibility methods that gather required evidence
  and invoke those decisions through the Stage 04 commit boundary.
- `specromancy/run_records.py`: shared record types and selectors from Stage 03.
- Existing `artifacts.py`: input resolution, output paths, artifact hashing and
  immutability verification remain filesystem-aware operations here.

## Work items

- [x] Document a transition table for pending, active, awaiting-approval,
  completed, blocked, and paused combinations. Include legal repeats and errors.
- [x] Extract limit calculations first. Preserve which visits/traversals count,
  when limits block, diagnostic payloads, and the fact that no extra successor
  is created after a limit is reached.
- [x] Separate `_new_visit` evidence collection from dictionary construction.
  Pass timestamps, literal input records, provenance records, output paths, and
  baseline explicitly; pure constructors do not read files or clocks.
- [x] Preserve the existing timing of symbolic input resolution and skill/template
  hashing. Do not change when a pending visit captures inputs as part of cleanup.
- [x] Extract transition decisions using a copied validated record. The result
  should describe the new state and event payload, or an explicit no-op. It must
  not assign persistence revisions, write files, or acquire locks.
- [x] Route completion plus successor preparation through one commit. Preserve
  terminal payloads, chosen outcomes, Git head updates, and sealed output hashes.
- [x] Keep paused successors pending. `resume` releases the checkpoint without
  starting the visit; phase/run commands retain their existing pause guards.
- [x] Keep public low-level methods such as `complete_visit` and `start_visit`
  distinct where they have different semantics; do not collapse them solely
  because their implementations overlap.
- [x] Preserve locked reloads and existing guards when applying a decision.
  Characterize overlapping validation/approval attempts before proposing any
  expected-revision or new lock-lifetime policy. Such hardening changes behavior
  and needs its own review rather than an incidental refactoring parameter.

## Verification

```sh
python -m unittest tests.features.unit.test_run_store tests.features.unit.test_engine
python -m unittest tests.features.contract.test_default_pipeline tests.features.contract.test_example_pipelines tests.features.contract.test_replacement_pipeline
python -m unittest tests.features.contract.test_interruptions tests.features.contract.test_safety
python -m unittest discover
bin/specromancy adapters generate --check
```

Use table-driven decision tests for meaningful combinations, then verify full
persisted traces for a linear graph, bounded loop, branch, approval, and paused
edge. Test the limit boundary, not only a far-over-limit state. Retry a recorded
transition and verify it does not append a visit, event, or revision twice.

## Exit criteria and rollback

Transition logic can be tested without disk access using explicit evidence.
The store still guarantees immutable historical outputs and one committed
successor transition. Generic modules reference configured IDs rather than
shipped phase names. All event traces, pause semantics, and idempotency checks
match the baseline. Revert individual extracted operations if necessary rather
than changing the wire format or rewriting historical visits.


## Preserved transition table

These are low-level store contracts over a validated manifest. Engine commands
apply their existing phase, approval, integrity, and run-status guards first.
Paused is a **run** status; its successor visit is pending. Every mutating row
uses one revision/event; no-op rows preserve both files byte for byte.

| Operation | Run / visit before | Result or error | Repeat |
| --- | --- | --- | --- |
| `prepare_visit` | Any run / any existing visit | Append pending visit; run awaiting-agent; inputs/provenance captured now | Appends another visit, subject to artifact addressing; no implicit limit check |
| `start_visit` | Any run / any existing visit | Append active visit with start timestamp/baseline; run active | Appends another visit; distinct from activation |
| `activate_visit` | Non-paused / pending | Visit and run active; input/provenance records unchanged | Active visit returns unchanged |
| `activate_visit` | Paused / any visit | `run-paused`, before visit lookup/status checks | Same error until resumed |
| `activate_visit` | Non-paused / awaiting-approval, completed, blocked, failed | `illegal-visit-status` | Same error |
| `complete_visit` | Any run / active, awaiting-approval, blocked, failed | Seal output and complete visit; run status/current visit unchanged | `visit-already-completed` |
| `complete_visit` | Any run / pending without start timestamp | No explicit status guard; commit validation rejects the missing start timestamp; neither file changes | Same error |
| `transition_visit` | Any run / active or awaiting-approval, below limits | Seal visit, save evidence/Git head/outcome, append pending successor; run awaiting-agent or paused | Same outcome/target returns unchanged, even after later progress |
| `transition_visit` | Any run / active or awaiting-approval, terminal target | Seal visit; run completed; retain supplied terminal payload or construct default | Same outcome/target returns unchanged |
| `transition_visit` | Any run / active or awaiting-approval, limit reached | Visit/run blocked; save evidence/Git head and block payload; no output sealing or successor | Blocked visit gives `illegal-visit-status` |
| `transition_visit` | Any run / completed, different outcome or target | `visit-already-completed` | Same error |
| `transition_visit` | Any run / pending, blocked, failed | `illegal-visit-status` | Same error |
| `resume_paused` | Paused / pending | Run awaiting-agent; visit remains pending with no start timestamp/baseline | Non-paused run returns unchanged |
| `resume_paused` | Paused / no current visit or non-pending visit | Existing corruption error | Same error |
| `resume_paused` | Any non-paused run | No-op, regardless of visit status | No-op |

Pipeline identity checks and locked reloads remain at their original operation
boundaries. Low-level methods do not gain engine policies. Missing visit lookup
retains `visit-not-found`. Output must exist before completion/transition, even
when a limit will block. Transition limits count recorded matching phase/outcome
pairs; phase limits count every visit to the target regardless of status. A
counter equal to its limit blocks **before** creating the next visit, and a
traversal limit takes precedence over a target-phase limit.

## Execution results

`visit_transitions.py` owns limit decisions, construction from literal evidence,
status/retry guards, activation, sealing, blocked/terminal/successor decisions,
and checkpoint release. `run_records.visit_by_number` shares the existing lookup
and diagnostic. Store methods collect evidence under the existing persistence
lock and apply copied decisions through one revision/commit helper. No-op
results bypass revision stamping entirely.

Completion proposes a sealed record so symbolic successor inputs can resolve
against it under the same lock. Only the final successor/terminal decision is
committed. The intermediate record is never persisted. Artifact resolution,
collision detection, hashing, and clock reads remain in the store's evidence
collection, using the existing artifact helpers. Input and provenance capture,
clock-call counts, output sealing, terminal payloads, Git head updates, and
pause/resume timing match the baseline.

Added disk-free table tests cover operation guards, exact limit boundaries,
counter selection/precedence, detached evidence, terminal payloads, and pause
release. Store tests inspect both persisted files for bounded loops, limit
blocking, exact retries, and pending provenance timing. Existing compatibility
replay covers complete approval/pause traces and existing graph contracts cover
linear and branching pipelines. The new store/interleaving tests also pass with
the original pre-extraction `RunStore` loaded from a temporary source copy.

### Overlapping attempts and deferred behavior change

Deterministic interleavings use two independent stores against one temporary
run. Two validations producing the same transition commit one successor; a
conflicting recorded outcome rejects the later attempt without changing either
persisted file. An approval attempt arriving after the grant but during
validation can finish the transition; the original attempt then returns without
a second transition.

A pre-existing engine defect is now explicitly characterized:
`test_overlap_before_approval_grant_exposes_existing_assertion` arranges for both
approval attempts to read the same pending record, then lets the second attempt
grant and finish before the first calls `mutate`. The first callback reloads the
completed manifest and raises `AssertionError` because its pending approval is
absent (`Engine.approve`'s `decide` callback). The successful attempt's manifest
and events remain intact, but the losing command receives an internal assertion
instead of a controlled retry/conflict result. This reproduces on the original
store. Fixing it requires a separately reviewed engine behavior change; Stage 05
adds neither an expected-revision parameter nor a broader lock lifetime. These
characterizations do not establish safety of stale validation evidence across
arbitrary concurrent file edits.

### Verification

On Python 3.14.4 (this shell provides `python3`, not `python`):

- Focused store, engine, persistence, decision, interleaving, and compatibility
  checks: **49 passed**.
- Default/example/replacement pipeline, interruption, and safety contracts:
  **23 passed**.
- New decision/store coverage plus architecture isolation checks: **18 passed**.
- All **6 new store/interleaving tests** passed against the original store.
- Differential replay against that original store compared **40 complete
  persisted snapshots byte for byte**: linear (8), terminal branch (5), approval
  (9), paused edge (10), bounded loop (8). Both manifests and complete event logs,
  plus all run artifacts, matched at every captured step.
- `python3 -m unittest discover`: **210 passed** in 24.189 seconds.
- `bin/specromancy adapters generate --check`: passed; no generated writes.
- `git diff --check`: passed.

No wire format, configured workflow, adapter, or public signature changed. The
approval assertion described above is the only newly characterized deferred
issue; no concurrency policy change was bundled into this extraction.
