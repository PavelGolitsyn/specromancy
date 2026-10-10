# Test groups

The suite is split by the source of its test data:

- `engine/` tests engine behavior with test-owned pipelines, skills, templates,
  and repositories. These tests must not depend on the checkout's customizable
  shipped configuration. CLI fixtures provide their own mandatory registry;
  low-level engine tests may load explicit test-owned graph paths. They assert
  exact values from their test configuration to verify the expected behavior.
- `shipped_configuration/` validates the real pipeline registry, all registered
  graphs, skills, templates, and generated harness adapters shipped by this checkout. These tests check
  validity and consistency without requiring specific configuration values.
  They must tolerate changes to the shipped configuration as long as it remains
  valid and consistent.

Run the groups independently:

```sh
python3 -m unittest discover -s tests/engine -t .
python3 -m unittest discover -s tests/shipped_configuration -t .
```

Run everything with:

```sh
python3 -m unittest discover
```

`engine/fixtures/refactoring-compatibility/` retains pre-extraction version-1
records with exact canonical pipeline bytes/hashes, response and diagnostic
envelopes, persisted manifests/events/artifacts, and generated adapter bytes.
`engine/contract/compatibility_support.py` runs deterministic scenarios in
temporary repositories; `test_compatibility.py` compares against those independent
records and continues restored pending, active, approval, paused, terminal, and
recovery states. Tests never refresh expected records. See the
[fixture capture and normalization policy](engine/fixtures/refactoring-compatibility/README.md).

`engine/contract/source_scan.py` recursively discovers runtime Python sources,
including nested package initializers, for architecture, subprocess, and
standard-library dependency checks. Architecture tests also import extracted
components independently of the public facades to expose reversed dependencies.
Pure visit decisions have table-driven tests in `unit/test_visit_transitions.py`;
store interleavings and durable fault boundaries live in
`unit/test_visit_transition_store.py` and `unit/test_run_persistence.py`.
`contract/test_engine_orchestration.py` checks validation/approval ordering and
recovery through observable responses and stored evidence.

For minimum-version verification, run the full suite with Python 3.11 and put
that interpreter's `bin` directory first on `PATH`, so subprocess launcher tests
using `#!/usr/bin/env python3` also exercise it. Repeat on the development Python.
The source-export tests require no package installation or runtime dependencies.

Follow-on integration evidence is recorded in
[Stage 15](../docs/history/refactoring/15-follow-on-integration.md), including the exact
interpreter paths, commands, counts, and deferred investigation boundaries.
The regression coverage for the final module boundaries and corrections is:

| Contract | Evidence under `engine/` |
| --- | --- |
| Original sequential bytes, hashes, packets, errors, restored runs, and facade aliases | `contract/test_compatibility.py`; the overlap test is separate from unchanged captures |
| Parsing and service import direction, generic runtime, pure decision dependencies | `contract/test_architecture.py` |
| Preparation lock scope, resource order, collision/failure non-mutation, sealed successor inputs | `unit/test_visit_transition_store.py`, class `VisitStoreBoundaryTests` |
| Request/grant/invalidation overlaps, no-op event counts, binding conflicts, recovery | `unit/test_visit_transition_store.py`, class `OverlappingAttemptTests`; `contract/test_engine_orchestration.py` |
| Controlled malformed-status errors before recovery, without persisted changes | `unit/test_run_records.py`; `contract/test_cli.py` |
| Deliberately retained weak version-1 acceptance | `unit/test_run_records.py`, status and nested compatibility tables |
| Fault points, clocks, recovery, ownership, immutable outputs, read-only policy | `unit/test_run_persistence.py`, `unit/test_run_store.py`, `contract/test_interruptions.py`, `contract/test_recovery.py`, `contract/test_safety.py` |
| Deterministic generation and adapter ownership in temporary repositories | `unit/test_adapters.py`, `contract/test_adapter_drift.py`, `contract/test_compatibility.py` |
| Installation-free source exports, launchers, standard-library imports | `contract/test_release.py`, `contract/test_launcher.py` |

Overlap tests deterministically inject a second engine at selected operation
boundaries. They establish the specified approval outcomes, not safety for every
possible command interleaving or external file edit. The deferred investigations
in Stage 15 require separate reproductions and design decisions.
