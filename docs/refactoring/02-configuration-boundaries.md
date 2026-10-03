# Stage 02 — Separate configuration responsibilities

Prerequisite: Stage 01. Keep the `specromancy.config` import surface stable.

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

- [ ] Move dataclasses without changing fields, defaults, properties, equality,
  frozen behavior, or constructor signatures. Re-export their names from config.
- [ ] Move configuration diagnostics with the existing `_MISSING` semantics so
  omitted values do not become explicit null diagnostic fields.
- [ ] Extract `_canonical_document` and its serializer byte-for-byte. Preserve
  ordering, default omission, transition sorting, and Unicode escaping.
- [ ] Keep pipeline encoding separate from `canonical_json_bytes`: the current
  pipeline `json.dumps` call uses default ASCII escaping while run hashing does
  not. Sharing hash digest operations is safe only after byte equivalence is
  established; sharing serialization defaults is not automatically safe.
- [ ] Move schema definition and value validation into a leaf module that does
  not import config loading. Preserve `ValidationFailure` and
  `SchemaDefinitionError` identities and public helper imports through re-exports
  as needed; choose one defining module for each exception to avoid cycles.
- [ ] Move the loader after these dependencies are acyclic. Preserve rejection
  order, filesystem containment, relative template/schema paths, reserved names,
  graph callbacks, root discovery, and `root`/`repository_root` argument behavior.
- [ ] Keep registry serialization independent unless exact equivalence is proven.
  Do not add caching that hides graph or dependency changes between commands.
- [ ] Update architecture documentation with the new internal dependency direction.

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
