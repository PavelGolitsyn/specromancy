# Stage 07 — Clarify CLI and adapter boundaries

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

Keep `contracts.RESERVED_COMMANDS` compatible. Keep harness-specific glue inside
adapter modules, and keep phase procedure/policy in canonical sources.

## Part A — CLI work items

- [ ] Introduce a minimal command definition shared by parser construction and
  adapter metadata. Preserve descriptions and sorted metadata byte-for-byte.
  Avoid a general dispatch framework when ordinary functions suffice.
- [ ] Check reserved built-ins and definitions agree; dynamic phase aliases stay
  run-specific and cannot shadow a built-in command.
- [ ] Isolate `_selected_pipeline`. Initialization still requires a registered
  ID; existing-run commands still use validated persisted path/identity. A
  removed registration must not strand an existing run with its graph intact.
- [ ] Preserve bootstrap ordering: help works without registry access, workflow
  commands require a valid registry, and adapter generation rejects `--pipeline`.
- [ ] Preserve common flags before/after subcommands, description file behavior,
  usage/error precedence, actionable stdout, error stderr, quiet handling, and
  the exactly-one-object JSON contract.

## Part B — Adapter work items

- [ ] Capture validated graphs, canonical skill text, dependency bytes, and CLI
  metadata once per generation invocation where feasible. Reuse that explicit
  source bundle for rendering and hashing; do not introduce cross-command caches.
- [ ] Preserve `render_adapters` as a public facade with its current signature
  and diagnostics while making the internal renderer operate on captured data.
- [ ] Move harness templates/rendering mechanically. Preserve whitespace, newline
  normalization, path order, generator version, native discovery paths, and
  exclusion of generated `specromancy-*` launch skills from canonical hashing.
- [ ] Separate expected manifest construction from reading the prior manifest.
  Source hashes must continue to bind the same bytes and metadata.
- [ ] Move ownership checks without broadening managed paths. Preflight all known
  conflicts before writes; recheck stale file hashes before deleting any previous
  manifest-owned output. Protect canonical skills and unowned or modified files.
- [ ] Keep `--check` write-free. Avoid writing temporary files merely to compare
  output. Preserve symlink/parent checks and adjacent temporary-file behavior.
- [ ] Preserve current per-file atomic replacement and manifest-last ordering.
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
