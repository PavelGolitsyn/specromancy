# Stage 02 — Separate configuration responsibilities

Prerequisite: Stage 01. Keep the `specromancy.config` import surface stable.

Status: implemented on 2026-10-03; no migration or adapter regeneration required.

## Purpose and evidence

`config.py` combines immutable dataclasses, TOML loading, field validation,
filesystem checks, graph validation, and canonical hashing. Artifact validation
imports configuration types while the loader imports JSON schema helpers from
artifact validation. Separate these responsibilities without changing accepted
configuration, diagnostic precedence, or hashes used by active runs.

## Proposed file map

| File | Responsibility |
| --- | --- |
| `specromancy/config.py` | Public facade, existing exports and compatibility aliases |
| `specromancy/config_models.py` (new) | Existing frozen configuration dataclasses |
| `specromancy/config_errors.py` (new) | `PipelineConfigError`, its sentinel and diagnostic conversion |
| `specromancy/config_loader.py` (new) | TOML and field parsing, path resolution, graph orchestration |
| `specromancy/config_serialization.py` (new) | Canonical document construction and exact pipeline encoding |
| `specromancy/schema_validation.py` (new) | Existing supported JSON schema definition/value algorithms |
| `specromancy/validation.py` | Artifact reads, Markdown/file validation, schema delegation |

Retain `registry.py` as the registry boundary and `graph.py` as graph analysis.
Prefer these few coherent modules to a class per field or validator. Internal
imports use leaf models; public re-exports reference the same class objects.

## Work items

- [x] Move dataclasses without changing fields, defaults, properties, equality,
  frozen behavior, or constructor signatures. Re-export their names from config.
- [x] Move configuration diagnostics with the existing `_MISSING` semantics so
  omitted values do not become explicit null diagnostic fields.
- [x] Extract `_canonical_document` and its serializer byte-for-byte. Preserve
  ordering, default omission, transition sorting, and Unicode escaping.
- [x] Keep pipeline encoding separate from `canonical_json_bytes`: the current
  pipeline `json.dumps` call uses default ASCII escaping while run hashing does
  not. Sharing hash digest operations is safe only after byte equivalence is
  established; sharing serialization defaults is not automatically safe.
- [x] Move schema definition and value validation into a leaf module that does
  not import config loading. Preserve `ValidationFailure` and
  `SchemaDefinitionError` identities and public helper imports through re-exports
  as needed; choose one defining module for each exception to avoid cycles.
- [x] Move the loader after these dependencies are acyclic. Preserve rejection
  order, filesystem containment, relative template/schema paths, reserved names,
  graph callbacks, root discovery, and `root`/`repository_root` argument behavior.
- [x] Keep registry serialization independent unless exact equivalence is proven.
  Do not add caching that hides graph or dependency changes between commands.
- [x] Update architecture documentation with the new internal dependency direction.

## Verification

```sh
python -m unittest tests.features.unit.test_config tests.features.unit.test_graph tests.features.unit.test_registry tests.features.unit.test_validation
python -m unittest tests.features.contract.test_multi_pipeline tests.features.contract.test_replacement_pipeline
python -m unittest discover
bin/specromancy adapters generate --check
```

Use Stage 01 hashes to compare old and new results for equivalent graphs with
different TOML ordering, Unicode text, optional defaults, and shared paths.
Check invalid schemas, path escapes, unknown fields, loops, and root failures
retain their diagnostic codes and fields. Import leaf modules independently to
detect reliance on package import order.

## Exit criteria and rollback

Public imports and canonical strings/hashes are unchanged. Existing runs accept
their original pipeline provenance. Adapter check passes without rewriting
generated files. Configuration and schema helpers have no import cycle.
Deliver models/serialization, schema extraction, and loader moves as separate
reviewable changes if necessary. Roll back code only; no migration is involved.


## Execution results

The proposed module map is implemented. Runtime consumers import configuration
records from `config_models`; `config` re-exports the same classes, loader,
constants, and compatibility helpers. `config_errors` defines the single
omitted-value sentinel used by both loader and diagnostic construction.
`schema_validation` defines `SchemaDefinitionError` and the existing schema
algorithms, re-exported through `validation`. `ValidationFailure` remains defined
in `validation`, since schema algorithms return value errors without raising it.
Registry serialization, generic hashing, graph algorithms, workflow sources,
and generated adapters are unchanged.

Validation on Python 3.14.4:

- The four planned unit modules plus compatibility and architecture contracts:
  **63 tests passed**.
- Multi-pipeline and replacement-pipeline contracts: **9 tests passed**.
- `python3 -m unittest discover`: **180 tests passed** in 23.242 seconds.
- `bin/specromancy adapters generate --check`: passed, with no generated writes.
- `git diff --check`: passed.

Stage 01 canonical strings/hashes, diagnostic fixtures, adapter bytes, and
version-1 run replay all pass unchanged. Temporary fixture comparisons also
confirmed reordered TOML fields match all three Stage 01 Unicode/pause baselines;
shared template/schema paths match the original loader's canonical strings and
hashes. AST comparison against the pre-extraction source confirmed all moved
records, diagnostic/schema algorithms, path helpers, and loader entry point are
unchanged. The loader class differs only in schema imports and delegation to
the extracted serializer.

New regression checks cover identity of facade re-exports, omitted versus null
diagnostic values, root discovery/alias precedence, schema path containment,
and re-reading schema dependencies on every load. Each extracted module and
artifact validation is imported in an isolated interpreter without package
facade initialization, checking that leaf dependencies do not load the parser
and neither parser nor artifact validation imports the other.

Environment limitation: the prescribed `python -m unittest discover` could not
start because `python` is unavailable; the documented `python3` equivalent was
used. Python 3.11 is not installed here, so minimum-version execution remains
unverified. No design deviations or implementation issues were deferred.
