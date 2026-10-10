# Stage 07 — Clarify CLI and adapter boundaries

Status: implemented on 2026-10-04.

Prerequisites: Stages 02 and 06. Deliver the CLI and adapter work as separate
reviewable changes, with a compatibility checkpoint between them.

## Purpose and evidence

`adapter_command_metadata` inspects private argparse structures to recover names
and descriptions. CLI pipeline selection is mixed with process formatting.
Adapter generation combines source discovery, rendering, ownership, and writes;
`registry.load_all()` is used by both rendering and source hashing. The goal is
explicit boundaries and consistent per-invocation inputs, not a plugin system.

## Proposed file map

| File | Responsibility |
| --- | --- |
| `specromancy/cli.py` | Public `main`, parser facade, dispatch and process output |
| `specromancy/cli_commands.py` (new) | Small static command descriptions and argument definitions |
| `specromancy/pipeline_selection.py` (new) | Init selection versus existing-run persisted provenance |
| `specromancy/adapters.py` | Public generate/render facade and existing constants/errors |
| `specromancy/adapter_sources.py` (new) | Validated registry-wide source capture and source records |
| `specromancy/adapter_rendering.py` (new) | Deterministic harness output and expected manifest construction |
| `specromancy/adapter_ownership.py` (new) | Previous manifest, path checks, drift, preflight, owned writes/cleanup |
| `specromancy/adapter_contracts.py` (new) | Shared constants, error, command record, and target classification; public names remain re-exported by `adapters` |

Keep `contracts.RESERVED_COMMANDS` compatible. Keep harness-specific glue inside
adapter modules, and keep phase procedure/policy in canonical sources.

## Part A — CLI work items

- [x] Introduce a minimal command definition shared by parser construction and
  adapter metadata. Preserve descriptions and sorted metadata byte-for-byte.
  Avoid a general dispatch framework when ordinary functions suffice.
- [x] Check reserved built-ins and definitions agree; dynamic phase aliases stay
  run-specific and cannot shadow a built-in command.
- [x] Isolate `_selected_pipeline`. Initialization still requires a registered
  ID; existing-run commands still use validated persisted path/identity. A
  removed registration must not strand an existing run with its graph intact.
- [x] Preserve bootstrap ordering: help works without registry access, workflow
  commands require a valid registry, and adapter generation rejects `--pipeline`.
- [x] Preserve common flags before/after subcommands, description file behavior,
  usage/error precedence, actionable stdout, error stderr, quiet handling, and
  the exactly-one-object JSON contract.

## Part B — Adapter work items

- [x] Capture validated graphs, canonical skill text, dependency bytes, and CLI
  metadata once per generation invocation where feasible. Reuse that explicit
  source bundle for rendering and hashing; do not introduce cross-command caches.
- [x] Preserve `render_adapters` as a public facade with its current signature
  and diagnostics while making the internal renderer operate on captured data.
- [x] Move harness templates/rendering mechanically. Preserve whitespace, newline
  normalization, path order, generator version, native discovery paths, and
  exclusion of generated `specromancy-*` launch skills from canonical hashing.
- [x] Separate expected manifest construction from reading the prior manifest.
  Source hashes must continue to bind the same bytes and metadata.
- [x] Move ownership checks without broadening managed paths. Preflight all known
  conflicts before writes; recheck stale file hashes before deleting any previous
  manifest-owned output. Protect canonical skills and unowned or modified files.
- [x] Keep `--check` write-free. Avoid writing temporary files merely to compare
  output. Preserve symlink/parent checks and adjacent temporary-file behavior.
- [x] Preserve current per-file atomic replacement and manifest-last ordering.
  This plan does not claim adapter generation is a multi-file atomic transaction;
  a new batch-recovery protocol would be a separate design.

## Verification

```sh
python -m unittest tests.features.unit.test_cli tests.features.contract.test_cli tests.features.contract.test_launcher tests.features.contract.test_multi_pipeline
python -m unittest tests.features.unit.test_adapters tests.features.unit.test_multi_pipeline_adapters tests.features.contract.test_adapter_drift
python -m unittest discover
bin/specromancy adapters generate --check
```

In a temporary fixture, generate twice and compare output bytes and manifest,
then run check mode and verify no files changed. Exercise removed registrations,
renamed launch skills, modified owned files, unowned collisions, and symlinked
parents. Compare command metadata before/after Part A before starting Part B.

## Exit criteria and rollback

CLI metadata no longer depends on argparse private inspection. Registry/pipeline
selection contracts remain unchanged. Rendering and ownership code are separate,
and internal-only changes produce identical managed outputs and source hashes.
Unexpected generated drift blocks completion; do not mask it by regenerating
the checkout. Roll back Part A or Part B independently if its contract gate fails.

## Implementation record

Part A introduced static command definitions in `cli_commands.py`, shared by
parser construction and sorted adapter metadata. Reserved command agreement is
checked explicitly; aliases remain invocation-local and cannot replace built-ins.
`pipeline_selection.py` contains the unchanged registered-init versus persisted-run
selection procedure. `cli.adapter_command_metadata`, `cli.RESERVED_COMMANDS`,
`build_parser`, and the private `_selected_pipeline` delegate remain available.

Before beginning Part B, the 19 focused CLI/launcher/multi-pipeline tests passed.
Command metadata, root help, and every rendered adapter matched the pre-change
baseline byte-for-byte, and the checked-in manifest passed check mode.

Part B extracted normalized source capture, deterministic rendering/expected
manifest construction, and ownership/write handling. One generation invocation
loads registered graphs once and shares captured canonical text, dependency
bytes, and serialized metadata between rendering and hashing. No cross-call
cache was introduced. The CLI lets generation derive metadata from its captured
graphs. Existing explicit metadata calls remain supported; omission is now an
optional convenience on `generate_adapters`.

`render_adapters` retains its signature, sorted output, and source diagnostics.
Its capture omits manifest-only dependency reads, preserving its previous scope.
Harness templates and ownership helpers were moved mechanically. Previous
manifest reads, managed path limits, conflict preflight, stale-file hash rechecks,
adjacent temporary files, per-file atomic replacement, and manifest-last ordering
remain unchanged. This remains a sequence of per-file writes, not a multi-file
transaction or an atomic filesystem snapshot.

### Verification

Python 3.14.4 was used via `python3`, as in the preceding stages.

- Part A compatibility checkpoint: **19 tests passed**; metadata, help, rendered
  bytes, and checked-in adapter source hashes unchanged.
- Initial Part B adapter/unit/drift checkpoint: **21 tests passed**.
- CLI and adapter unit/drift checks including new regressions: **35 passed**.
- Final `python3 -m unittest discover`: **223 passed** in 25.583 seconds.
- `bin/specromancy adapters generate --check`: passed without regeneration.
- `git diff --check`: passed.
- Final metadata/help/rendered-byte comparison against the pre-change capture:
  identical. Extracted ownership helper ASTs match their original implementations.
- Temporary fixtures cover two identical generations and manifest bytes, check
  mode preserving file bytes and modification times without temporary writes,
  removed registrations and renamed launch skills, unowned collisions, modified
  stale files, a stale-file edit after preflight, canonical-skill protection, and
  symlinked parents.
- New source-boundary checks cover one graph load and one canonical-text capture
  per invocation, no cross-invocation cache, captured rendering/hash consistency
  after disk edits, and render-only dependency-read behavior. Architecture checks
  enforce independent imports for the extracted adapter and command modules.

### Deviations and deferred issues

The small additional `adapter_contracts.py` leaf avoids import cycles between the
facade, source capture, renderer, and ownership code. Its existing public names
are re-exported unchanged. `generate_adapters` accepts omitted metadata to avoid
loading all graphs separately in the CLI; explicit metadata remains compatible.
No generated files, canonical procedures, workflow configuration, or stored-run
formats changed. No new deferred issue was identified; broader concurrency and
batch recovery remain outside this extraction.
