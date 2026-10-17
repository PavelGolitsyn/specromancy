# Stage 01 — Contracts and baseline

Status: complete (2026-10-11). Dependency: none. Next: [Stage 02](02-source-layout-and-packaging.md).
Index: [migration plan](README.md).

Execution: [baseline results](evidence/01-baseline.md),
[contract decisions](evidence/contracts.md), and
[classified occurrence inventory](evidence/inventory.tsv).

## Objective

Establish the exact surface being migrated and capture independent evidence
before moving files. The result is a contract matrix and a known baseline,
not an implementation change.

## Inputs and intended files

Read `AGENTS.md`, `docs/reference/contracts.md`, `docs/reference/architecture.md`,
`docs/reference/cli.md`, `docs/README.md`, `tests/README.md`, `bin/specromancy`,
`adapters/generate.py`, and `specromancy/__init__.py`.

Inspect all tracked Python imports, module invocation strings, patch targets,
schema paths, test source scans, launcher assumptions, canonical skills,
generated manifest entries, and current configuration. Include hidden harness
directories in searches; do not search ignored run storage as a source tree.

Create implementation evidence under this migration directory, for example
`evidence/01-baseline.md` and `evidence/contracts.md`. Do not add generated build
outputs or private runtime artifacts to the evidence.

## Work

1. Record commit, worktree status, Python executables/versions, Git version,
   supported platforms already claimed, and any existing installation or release
   metadata. Keep unrelated local changes out of the migration.
2. Classify every occurrence into one of: Python namespace, filesystem package
   path, CLI identity, persistent path, workflow-owned source, generated output,
   test expectation, historical record, or unrelated content. This classification
   governs later replacements.
3. Record the migration contracts:

   | Surface | Target decision |
   | --- | --- |
   | `import specromancy` and its public facades | Replace with `specromancy_engine`; explicitly document the break |
   | `python -m specromancy` | Replace with `python -m specromancy_engine` |
   | Installed executable and emitted argv | Keep `specromancy` |
   | Checkout wrappers | Retain as thin developer conveniences, pointing at `src/` |
   | Run/event/pipeline/registry formats | Keep version 1 and exact compatible bytes |
   | Adapter rendering | Change executable text deliberately; preserve ownership format unless its shape changes |
   | Schema resource location | Move into the renamed package; document resource access |
   | Workflow and skill locations | Keep project-owned paths |

4. Determine whether existing consumers require old Python imports. The default
   plan assumes a direct pre-1.0 migration. If evidence requires a shim, specify
   its exact supported facade list, object identity, warning behavior, removal
   version, and distribution contents before proceeding; do not improvise
   duplicate implementations during Stage 3.
5. Keep this packaging and namespace work within the 0.1.0 implementation;
   do not infer package registry availability from a name.
6. Record representative legacy scenarios already captured in
   `tests/engine/fixtures/refactoring-compatibility/`: pending, active, approval,
   paused, completed, and manifest/event recovery. Reuse these independent
   fixtures rather than replacing them with new-engine outputs.
7. Identify active runs in the migration workspace through normal CLI inspection
   if any exist. A source move or canonical skill edit can legitimately change
   repository snapshots or provenance. Do not promise that a run actively
   validating the producer checkout will ignore those changes. Rehearse upgrades
   separately with unchanged consumer files.

## Verification

Run under Python 3.11 and the development interpreter, with each interpreter's
bin directory first on `PATH` for shebang-based subprocesses:

```sh
python -m unittest tests.engine.contract.test_compatibility
python -m unittest tests.engine.contract.test_launcher tests.engine.contract.test_release
python -m unittest discover
bin/specromancy adapters generate --check
```

Save results and diagnose pre-existing failures before attributing anything to
the migration. Adapter check mode must not change files. Do not regenerate old
fixtures or adapters just to make a baseline appear clean.

## Acceptance criteria

- [x] Baseline commands, versions, counts, exit codes, and failures are recorded.
- [x] Every naming surface has a keep/change decision.
- [x] The existing Python import guarantee is explicitly accounted for.
- [x] Legacy records are identified and preserved.
- [x] Source-export support, supported platforms, version, and import transition
  decisions are clear enough for implementation.

Both Python 3.11.15 and 3.14.4 passed 9 compatibility tests, 7 launcher/release
tests, the full 249-test suite, and the adapter drift check. The decision is a
direct namespace change within 0.1.0, with no legacy shim. The temporary
version metadata used by development builds is recorded in the evidence.
Stage 01 also found that action packets currently emit Python module argv,
unlike status commands. The contract evidence and Stage 03 now identify the
deliberate command-value change and require separate versioned expectations.

## Recovery and handoff

No runtime changes occur in this stage. Correct incomplete evidence in place;
do not reset the repository. Hand off the contract matrix and baseline to Stage 2.
