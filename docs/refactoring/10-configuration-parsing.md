# Stage 10 — Separate field parsing from pipeline assembly

Status: complete on 2026-10-04. Prerequisites: Stage 09 complete.
Category: behavior-preserving refactoring. Risk: diagnostics and configuration hashes.

## Objective and evidence

`config_loader._Loader` still contains scalar/list checks, resource containment,
phase parsing, validator/schema loading, command parsing, transition parsing, and
pipeline assembly. The earlier pass separated models and canonical serialization;
retain those boundaries. The goal is to make each parser readable with explicit
inputs, not to create a generic validation framework or hit a line-count target.

## Files and target responsibilities

| File | Responsibility after this stage |
| --- | --- |
| `specromancy/config_loader.py` | TOML/root loading, pipeline assembly, graph validation, compatibility `_Loader` entry point |
| `specromancy/config_fields.py` (new) | Diagnostic context, scalar/list checks, unknown-key checks, existing-path resolution |
| `specromancy/config_phase_parser.py` (new) | Phase, validator, command, transition, input and output-pattern parsing |
| `specromancy/config.py` | Existing imports and public loading/hash helpers |
| `config_models.py`, `config_serialization.py`, `schema_validation.py` | Existing responsibilities; no replacement implementations |

The names above are proposed internal modules. Prefer two cohesive modules over
one new file per helper. The field context may perform path IO; it is not a pure
model. It must not import phase parsing, the CLI, engine, or run storage.

## Implementation sequence

1. Extract `_Loader.fail`, field requirements, string-list parsing, and
   `check_unknown` into a small context carrying source path and repository root.
   Move existing code first; preserve `_MISSING`, diagnostic fields, remediation,
   exception chaining, and the distinction between absent and explicit values.
2. Move resource resolution without changing lexical versus resolved checks,
   allowed parent traversal, symlink containment, file requirements, or error
   precedence. Do not impose registry-path rules on shared resource paths.
3. Move phase-related parsers to functions or a small parser using that context.
   Preserve the order of field checks and filesystem reads. Keep schema-file
   loading in the validator path and reuse the supported schema-subset validator.
4. Leave `_Loader.parse` responsible for assembling the pipeline, validating
   the graph, and obtaining canonical bytes from `config_serialization`.
   Preserve root discovery, the `root` alias, and errors for conflicting arguments.
5. Retain required `_Loader` methods/delegates and facade exports established
   in Stage 09. Avoid hidden callbacks into `config.py` and circular imports.
6. Document the new ownership map in `docs/poc-v3/architecture.md`; update isolated
   import coverage to include the new boundaries. Do not rewrite canonical TOML.

Suggested review units: field context extraction, phase-parser extraction, then
facade/dependency audit. Each must pass focused verification before proceeding.

## Verification cases

- Compare exact canonical JSON/hash output, including Unicode, ordering, omitted
  pause defaults, and explicit values, with the existing compatibility fixture.
- Exercise invalid tables, booleans in integer fields, duplicate values, unknown
  fields, unsafe outputs/inputs, escaping resources, malformed schemas, and
  multiple simultaneous errors. Preserve the first reported diagnostic.
- Load test-owned single and multi-pipeline registries, relative shared resources,
  non-Git roots, and replacement phase names. Test source export without installation.

```sh
python -m unittest tests.features.unit.test_config tests.features.unit.test_registry tests.features.unit.test_graph tests.features.contract.test_compatibility tests.features.contract.test_architecture tests.features.contract.test_replacement_pipeline
```

Then run the shared full-suite, adapter-check, and diff-check gates in the index.

## Exit criteria and rollback

- [x] Pipeline assembly is separate from field and phase parsing.
- [x] Existing imports, diagnostics, hashes, and accepted configurations match.
- [x] No schema version, canonical resource, or generated adapter changed.
- [x] All focused and shared verification gates pass.

On an unexplained diagnostic/hash difference, stop and compare evaluation order
before changing fixtures. Each extraction can be reversed independently; no run
migration or adapter regeneration is part of rollback.

## Stage 09 decisions to preserve

Use the [inventory and test map](09-follow-on-baseline.md#import-and-injection-inventory).
Retain every existing `_Loader` method and facade helper import; no direct
private-loader monkeypatch callers were found, but removal is not this stage's
scope. The new multiple-invalid-fields test fixes first-diagnostic ordering across
field, phase, resource, validator, command and transition boundaries, including
complete error details. Existing root/schema/hash tests remain the oracle.

## Execution record

Starting revision: `a37559a044ff7ea0b712dd7ab459f28dc593c7b1`; clean checkout.

- Extracted diagnostic construction, scalar/list/unknown-key checks, and resource
  resolution into `config_fields.FieldContext`. `_Loader` inherits those methods
  with unchanged signatures and sentinel defaults.
- Extracted phase, validator, command, transition, input, and output-pattern
  parsing into `config_phase_parser`, using explicit `FieldContext` arguments.
  `_Loader` retains every phase-parser method as a delegate. Existing constants
  and helper imports remain available through the loader and `config` facade.
- Kept TOML/root loading, pipeline assembly, graph validation, and canonical
  serialization orchestration in the loader. Schema reads still happen in
  validator parsing through the existing schema-subset loader.
- Extended isolated-import checks for both new modules, facade identity checks,
  and direct use of the retained loader parser methods. Updated the architecture
  ownership map. No compatibility capture or canonical resource was changed.

An AST comparison against the starting revision confirmed all original loader
method and helper bodies match after normalizing the explicit context arguments
and parser calls. This supplements the behavioral checks without creating another
compatibility fixture.

### Verification

Executed on Python 3.14.4. This shell has no `python` executable, so the documented
`python3` equivalent was used; Python 3.11 was not rerun in this stage.

| Command / checkpoint | Result |
| --- | --- |
| Focused command below, before extraction | 59 passed in 1.446s |
| Same focused command, after field/resource extraction | 59 passed in 1.411s |
| Same focused command, after phase extraction | 59 passed in 1.494s |
| Same focused command, with final boundary/delegate coverage | 60 passed in 1.468s |
| `python3 -m unittest discover` | 230 passed in 26.086s, including source-export coverage |
| `bin/specromancy adapters generate --check` | Passed: generated adapters are up to date |
| `git diff --check` | Passed |

Focused command:

```sh
python3 -m unittest tests.features.unit.test_config tests.features.unit.test_registry tests.features.unit.test_graph tests.features.contract.test_compatibility tests.features.contract.test_architecture tests.features.contract.test_replacement_pipeline
```

No scope deviations or behavior changes. Existing limitations and later-stage
correctness work remain as recorded in Stage 09; stages 11–15 were not executed.
