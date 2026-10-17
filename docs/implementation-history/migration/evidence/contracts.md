# Migration contract decisions

This records a stage of the 0.1.0 implementation. Artifacts are identified by
stage and original hash; historical command excerpts use explicit artifact-path
placeholders where obsolete filenames have been omitted.

Decision date: 2026-10-11. Baseline commit:
`767a417850499bbe13d32cf2a6360a2f9bf04904`.
See [executed baseline](01-baseline.md) and [occurrence inventory](inventory.tsv).
These decisions describe subsequent implementation; the current checkout
continues to expose its existing `0.1.0` contracts during Stage 01.

## Compatibility and version decision

Use distribution `specromancy-engine` and import namespace `specromancy_engine`,
without a legacy import shim, as part of the **0.1.0 implementation**. Stage 02
uses `specromancy` for its intermediate source layout; Stage 03 changes the
namespace. Package and distribution metadata are kept consistent throughout
the implementation. No registry publication or remote repository rename is
authorized.

The old imports are a real documented guarantee in
`docs/reference/contracts.md:7`, `docs/README.md:38`, and architecture text.
The migration intentionally breaks that guarantee, along with old module
invocation and source-relative schema paths. Stage 03 must replace the
present-tense guarantee with documentation of the implemented namespace. The current
documentation remains accurate and unchanged in Stage 01.

The tracked consumer search found old imports in the two checkout wrappers
and engine/shipped-configuration tests, including subprocess programs and
patch strings. Runtime imports are relative. No tracked application outside
those consumers imports the package; no installable distribution metadata or
local release tags indicate an additional compatibility requirement. This
does not establish that unknown external consumers do not exist. Available
repository evidence gives no reason to depart from the plan's direct break.
If a concrete external consumer is found later, revisit this decision before
Stage 03; specify a shim's exact facade coverage, shared object identity,
warning behavior, removal version, and distribution contents first.

## Surface matrix

| Surface / classification | Decision | Implementation boundary |
| --- | --- | --- |
| Python namespace: package import | CHANGE `specromancy` to `specromancy_engine`; no old package shipped | Stage 03 |
| Python namespace: six public facades | CHANGE only namespace for `config`, `engine`, `run_store`, `registry`, `adapters`, `cli`; KEEP names, signatures, exports and defining-object identity | Stage 03 |
| Python namespace: shared utilities and aliases | CHANGE namespace; KEEP utilities, `SpecromancyError`, compatibility aliases and exception identity | Stage 03 |
| Python namespace: private subsystems | KEEP `_config`, `_runs`, `_engine`, `_adapters`, `_cli` boundaries and relative imports; move under the new parent | Stages 02–03 |
| Python namespace: module command | CHANGE `python -m specromancy` to `python -m specromancy_engine` | Stage 03 |
| Filesystem package path | CHANGE `specromancy/` → `src/specromancy/` → `src/specromancy_engine/`; move all 52 Python files and four schemas | Stages 02–03 |
| CLI identity: installed executable, argparse name | KEEP `specromancy`, commands, flags, stream routing and exit codes | Stages 02–03 |
| CLI identity: status `next_command` | KEEP existing `specromancy` argv | No behavior change |
| CLI identity: action `final_validation_command` | CHANGE existing Python module prefix to installed `specromancy`; retain remaining arguments and order | Stage 03; exception detailed below |
| CLI identity: checkout wrappers | KEEP `bin/specromancy` and `adapters/generate.py`; CHANGE only source-path insertion and delegated import | Stages 02–03 |
| Persistent path | KEEP `.specromancy/runs/<run-id>/`, artifacts, events, locks and command logs; no conversion or cleanup | Every stage |
| Persisted formats | KEEP version 1 run/event/pipeline/registry formats, canonical bytes, hashes, immutable outputs and recovery behavior | Every stage |
| Response formats | KEEP version 1 keys, types, diagnostics and behavior; intentional action argv value change is separately recorded | Stage 03 |
| Filesystem package path: schemas | CHANGE resource location; KEEP all four schema contents, existing `$id` values and schema versions | Stages 02–04 |
| Workflow-owned source | KEEP consumer `AGENTS.md`, `workflow/`, `.agents/skills/`, pipeline IDs and policies; CHANGE portable CLI instructions where needed | Stages 02, 05 |
| Generated output: invocation text | CHANGE `bin/specromancy …` to `specromancy …` through canonical rendering; preserve original adapter capture | Stage 05 |
| Generated output: ownership/discovery | KEEP `adapters/manifest.json`, managed paths, `specromancy-<id>` prefix, harness names/modes and generator name | Every stage |
| Generated output: versions | KEEP ownership schema version 1 if shape stays unchanged; increment generator version when executable rendering changes | Stage 05 |
| Test expectation | CHANGE namespace, patch/import strings, physical package scans and deliberate invocation expectations only; KEEP original state/hash/diagnostic captures | Stages 02–05 |
| Historical record | KEEP `docs/implementation-history/**` and original independent compatibility evidence unchanged | Every stage |
| Unrelated content | KEEP arbitrary scratch-directory names, test environment-variable names, prose not asserting package layout, schema URLs, and `game-of-life/` | Every stage |
| Product/distribution identity | Use `specromancy-engine` for distribution and suggested repository name; no assertion of registry availability | Stages 02, 06 |

The package-level exports to carry forward are `ExitCode`, `Engine`,
`EngineError`, `PipelineConfig`, `PipelineConfigError`, `PipelineRegistry`,
`PipelineRegistration`, `RunCorruptionError`, `RunNotFoundError`, `RunStore`,
`generate_run_id`, `load_pipeline`, `load_registry`, `validate_run_id`, and
`__version__`. Do not turn aliases into duplicate definitions. Existing
compatibility tests assert identity for configuration records/errors,
`EngineError`, schema helpers, hashing aliases, artifact helpers, RunStore
aliases, and the repository snapshot alias.

## Correction: action commands are module invocations today

The initial migration index incorrectly said both `actions.py` and `status.py`
already emit executable `specromancy` commands. At the baseline:

```text
status.py:  ["specromancy", "validate", RUN_ID, PHASE]
actions.py: [sys.executable, "-m", "specromancy", "--root", ROOT,
             "validate", RUN_ID, PHASE, ...]
```

`tests/engine/unit/test_engine.py:262` explicitly asserts the old three-item
prefix. `responses.json` preserves it in `action-pending`, `action-active`,
and `resumed` using `<PYTHON>` normalization. A blind rename would alter
response bytes, while leaving it untouched would invoke a removed module.

Apply the Stage 01 target that emitted CLI argv uses `specromancy`: Stage 03
must produce `["specromancy", "--root", ROOT, "validate", RUN_ID, PHASE, ...]`
in `action.final_validation_command`. Keep `status.next_command` unchanged.
Configured validation-command argv belongs to the consumer and must not be
rewritten. Check emitted commands in an environment whose PATH contains the
installed console script; installation-free source-export users can put the
checkout's `bin/` on PATH or invoke its wrapper explicitly.

This is an intentional command-value change with the same response shape and
schema version, not a stored-data change. Preserve the original
`responses.json`; add a separately reviewed versioned response expectation
that differs only in those command prefixes. Compare every other response
field exactly, and continue replaying the original `states.json`,
`canonical.json`, and `diagnostics.json` without changes. Do not weaken replay
to ignore arbitrary argv or regenerate all records. Stage 05 separately needs
versioned adapter expectations for its deliberate executable-text change.

## Package resources, installation and source exports

Keep the four files `run.schema.json`, `event.schema.json`,
`pipeline.schema.json`, and `pipelines.schema.json` as engine-owned package
data. Their installed access contract will be:

```python
from importlib.resources import files

schema_text = (
    files("specromancy_engine")
    .joinpath("schemas", "run.schema.json")
    .read_text(encoding="utf-8")
)
```

Use `importlib.resources.as_file` only when an actual filesystem path is
needed, within its context manager. Do not derive engine resources from the
consumer root. Do not route published full schemas through
`schema_validation.load_json_schema`: that function loads consumer-owned
validator schemas and deliberately accepts only a small keyword subset.
Consumer template, skill and validator paths continue to resolve from the
consumer configuration, with existing containment and provenance rules.

Source exports remain supported without installation through the two thin
wrappers. They currently insert their parent repository directory into
`sys.path`; Stage 02 changes that insertion to `src/`. Module execution from
an arbitrary source directory is not a substitute for an installed package.
Tests should use the prescribed editable development install, not a new
test-side `sys.path`/`PYTHONPATH` workaround. Regular wheel/sdist verification
must also run outside the producer checkout with an unchanged independent
consumer. Build dependencies may be separate tooling; runtime dependencies
remain empty and the minimum interpreter remains Python 3.11.

## Inventory scope and reading guide

The inventory covers all 232 tracked files at the baseline, including hidden
harness files and fixture skills. It excludes ignored run storage and all new
Stage 01 evidence. File/line/column references refer to that commit, before
these completion edits. Searches used `git ls-files -z` and `git grep -n -I`
with explicit hidden paths; Python AST inspection covered all 97 tracked
`.py` files and `bin/specromancy`. No tracked `game-of-life/` files were found.

`inventory.tsv` contains 1,760 rows:

- 927 case-insensitive occurrences of `specromancy` (including
  `specromancy_engine` and occurrences inside JSON strings).
- 729 AST import statements: 109 absolute engine imports, 163 relative imports,
  and 457 other imports. Runtime engine imports are relative; other imports
  are retained and the baseline dependency scan passes.
- 56 package-file rows (52 Python files plus four schemas), 22 owned-file rows
  (21 generated files plus the manifest), and 26 additional source-assumption
  lines matching `sys.path`, `PYTHONPATH`, `__file__`, `runtime_sources`,
  `import_module`, or `patch(` without a naming occurrence on that line.

Every row has one of the nine Stage 01 classifications and a keep/change
decision. Line/column zero identifies a whole file. Import rows may overlap
naming rows because an import is both a statement and a naming occurrence.
`keep-plan-text` means an existing migration document already describes the
target or an explicit old/new comparison; it is not a replacement candidate.
`regenerate-from-canonical` forbids direct edits to generated text. It does
not authorize renaming owned paths. `keep-fixture` preserves test-owned input
and independent captures; current fixture skill commands explicitly marked
`change-invocation-stage05` are the exception. Versioned expectations are added
separately without replacing the independent captures.

The following reviewed details resolve the less obvious references:

| Evidence at baseline | Required treatment |
| --- | --- |
| `bin/specromancy:8`, `adapters/generate.py:7` | Insert checkout `src/`, keep executable locations and thin delegation |
| `test_architecture.py:32–35,80–91,152` | Rename synthetic module, module blockers/imports and physical scan root; keep recursive scanning |
| `source_scan.py:6`, `test_release.py:68`, `test_layout.py:21` | Add existence/nonempty guards so a wrong path cannot pass an empty scan |
| `test_release.py:75` | Rename the allowed internal package in the stdlib check |
| `test_config.py:206`, `test_registry.py:115`, `test_run_store.py:318` | Update physical schema paths in Stage 02; use package resources by Stage 04 |
| `test_run_records.py:186` | Current `run_store.__file__` path follows the moved module; change to the supported resource access contract in Stage 04 |
| `compatibility_support.py:113,166,202`, `test_compatibility.py:151,190`, `test_engine_orchestration.py:122`, `test_cli.py` under unit tests at line 52 | Rename string patch targets while preserving the same patch seams |
| Contract `support.py:65`, CLI/adapter/launcher/multi-pipeline/example tests | Change subprocess `-m` package names; retain tests' repository-root discovery |
| Contract `test_recovery.py:66` | Rename the import embedded in the subprocess source string |
| Test `ROOT`/`FIXTURES`/`CASES` expressions | Keep current test-directory ancestry and fixture-relative roots; these files do not move with the runtime |
| Unit `test_multi_pipeline_adapters.py:76` | Keep standard-library `pathlib.Path.read_bytes` patch |
| `test_release.py:23`, shipped `test_pipeline.py:68` | Keep scratch checkout directory names; these are not imports |
| Test environment names beginning `SPECROMANCY` | Keep test-controlled variables; no package-discovery meaning |
| `.agents/skills/{pipeline,research,plan,implement,review}/SKILL.md` | Keep policy and locations; Stage 05 changes checkout-specific invocation text |
| `adapter_sources.py`, `adapter_ownership.py`, `adapter_rendering.py` | Keep reserved generated prefixes, source exclusions, discovery and ownership; change executable rendering only through canonical code |

All abbreviated test filenames in this table are under `tests/engine/contract/`
unless qualified or identified as unit/shipped tests. The TSV supplies full
paths and exact one-based locations.

## Configuration and ownership handoff

The current registry has one `implementation` entry pointing to
`workflow/pipelines/implementation.toml`. Its graph version and schema version
are 1; its phase sequence/policies remain project configuration. Do not move
them into the engine or rewrite their stored hashes during packaging.

The manifest has ownership schema version 1, generator version 1, generator
name `specromancy`, and regeneration command `bin/specromancy adapters generate`.
Its canonical-source hash is
`3a540bc3f8b4d681de44f4a8a2000aa6b3f1f95502639e91c6de9c3573a2c562`.
Its 21 outputs are one native `.agents` launch skill, 11 Claude files, five
Copilot files and four OpenCode commands. Codex and Hermes use native discovery;
the shared launch skill has one ownership record under Codex. Keep these
identities and paths. Regeneration after canonical instruction edits will
legitimately change content/provenance hashes, without changing ownership shape.

The active producer run and four missing-pipeline conditions are recorded in
the baseline. Do not promise source moves or skill edits are invisible to that
active run. No state conversion, fixture refresh, staging, commit, publication,
or repository cleanup is part of this migration stage.
