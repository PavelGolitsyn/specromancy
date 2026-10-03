# Stage 01 — Establish a compatibility baseline

Prerequisites: none. Deliver this before moving runtime code.

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

- [ ] Inventory documented imports in `specromancy/__init__.py`, module-level
  aliases, constructor injection points, and externally exercised methods.
  Include `load_config`, hash helper aliases, run-store aliases, and artifact
  aliases even when they are absent from `__all__`.
- [ ] Make source scans recursive, with explicit justified exclusions for
  harness-specific boundaries. Test newly extracted generic modules too; retain
  the separation between workflow policy and runtime behavior.
- [ ] Map each contract below to an existing test and add only missing cases.
- [ ] Capture representative canonical pipeline strings and expected hashes,
  including non-ASCII text, absent defaults, `pause = false`, and `pause = true`.
- [ ] Capture representative action, approval, paused, blocked, terminal, and
  error envelopes, retaining meaningful ordering and exact diagnostic fields.
- [ ] Prepare version-1 persisted examples for active, pending, approved-but-not-
  advanced, paused, completed, and recoverable states. Obtain them through the
  baseline API in isolated fixtures; do not manufacture valid history by editing
  an actual user's state.
- [ ] Use fixed clocks/random sources where supported. Normalize only documented
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
```

Run version-sensitive checks on Python 3.11 and the current development
interpreter when available. A pass on 3.14 alone does not establish the minimum
supported version.

## Exit criteria and rollback

Every matrix row has named test evidence; new source modules cannot evade
architecture checks; baseline generated bytes and pipeline hashes are captured.
The full suite passes without runtime behavior changes. If baseline failures
exist, document and resolve them before using this stage as an equivalence gate.
This stage is reversible as a test/documentation change and writes no live runs.
