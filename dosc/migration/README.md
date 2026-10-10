# Specromancy Engine package migration

Status: planned; implementation has not started. Prepared on 2026-10-10 against
commit `040d84debfdc0ebb44c64f4abd3c271c606d211d`.

This plan turns the checkout-based POC into an installable engine that another
project can depend on while owning its own pipeline specifications, skills, and
templates. The plan lives in `dosc/migration/` as requested; the existing product
documentation remains in `docs/`.

## Target names and boundaries

| Surface | Target | Compatibility decision |
| --- | --- | --- |
| Product and suggested repository name | `specromancy-engine` | Renaming a remote repository is outside this migration |
| Python distribution | `specromancy-engine` | Declared in `pyproject.toml` |
| Python import package | `specromancy_engine` | Explicit breaking change from `specromancy` |
| Installed source | `src/specromancy_engine/` | Only reusable engine code and engine-owned resources |
| Installed CLI | `specromancy` | Preserve command names, arguments, response envelopes, and exit codes |
| Module invocation | `python -m specromancy_engine` | Replaces `python -m specromancy` |
| Consumer configuration | `workflow/` and `.agents/skills/` | Preserve current configuration and discovery contracts |
| Consumer runtime state | `.specromancy/runs/` | Preserve paths, schemas, hashes, and recovery behavior |
| Generated adapters | Existing harness paths and `adapters/manifest.json` | Preserve ownership rules; deliberately update invocation text |

The proposed import migration is a direct pre-1.0 break, with no legacy import
shim. The current documented import guarantees make this a real contract
change, not a cosmetic rename. Stage 1 must check whether known consumers need
a transition period; if so, revise the compatibility decision before Stage 3.
This is an implementation decision checkpoint, not a request to stop writing
this plan. The proposed next version is `0.2.0`, subject to checking release
history; neither package-name availability nor publication rights are assumed.

```text
specromancy-engine/
├── pyproject.toml
├── src/specromancy_engine/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── engine.py
│   ├── config.py
│   ├── run_store.py
│   ├── registry.py
│   ├── adapters.py
│   ├── schemas/
│   ├── _config/
│   ├── _runs/
│   ├── _engine/
│   ├── _adapters/
│   └── _cli/
├── tests/
│   ├── engine/
│   ├── shipped_configuration/
│   └── packaging/
├── examples/release-documentation/
│   ├── AGENTS.md
│   ├── workflow/
│   └── .agents/skills/
├── tools/verify_distribution.py
├── docs/
├── dosc/migration/
├── workflow/                       # This repository's development workflow
├── .agents/skills/                 # This repository's canonical procedures
├── adapters/                       # Manifest and optional developer wrapper
└── bin/specromancy                 # Optional checkout-only launcher
```

Existing public modules and shared utilities omitted from the abbreviated tree
move with the package. Keep the current private subsystem boundaries; this work
does not redesign the engine or introduce a new pipeline DSL or SDK abstraction.

## Stages

Each stage has its own `stage.md`, file map, verification, acceptance criteria,
and recovery guidance. Execute sequentially. Each stage should leave a working,
reviewable tree; Stage 2 intentionally uses the old import name temporarily.

| Stage | Deliverable | Depends on |
| --- | --- | --- |
| [01 — Contracts and baseline](01-contracts-and-baseline/stage.md) | Inventory, compatibility decisions, reproducible baseline | None |
| [02 — Source layout and packaging](02-source-layout-and-packaging/stage.md) | `src/specromancy/`, installable distribution, console entry point | 01 |
| [03 — Python namespace migration](03-python-namespace/stage.md) | `src/specromancy_engine/`, updated imports and public contracts | 02 |
| [04 — Consumer roots and package resources](04-consumer-roots-and-resources/stage.md) | Installed runtime independent of producer checkout | 03 |
| [05 — Portable skills and adapters](05-portable-skills-and-adapters/stage.md) | Consumer-executable generated instructions | 04 |
| [06 — Consumer example and documentation](06-consumer-example-and-docs/stage.md) | Release-documentation example and dependency onboarding | 05 |
| [07 — Distribution verification and CI](07-distribution-verification/stage.md) | Isolated wheel/sdist checks and repeatable CI | 06 |
| [08 — Migration rehearsal and release readiness](08-release-readiness/stage.md) | Completed evidence, upgrade rehearsal, distributable artifacts | 07 |

## Evidence informing the plan

- `specromancy/__init__.py` exports the engine, configuration, registry, run
  store, errors, and `__version__ = "0.1.0"`.
- No `pyproject.toml` or `.github/workflows/` directory exists in the inspected
  checkout. `bin/specromancy` and `adapters/generate.py` inject the repository
  root into `sys.path`.
- `specromancy/cli.py` already discovers the consumer root from the working
  directory or `--root`; installation should preserve this behavior.
- `specromancy/actions.py` and `status.py` already emit `specromancy` commands,
  while adapter rendering and canonical skills still use `bin/specromancy`.
- Adapter generation requires a consumer `AGENTS.md`, registry, skills, and
  `.agents/skills/pipeline/SKILL.md`; installation alone does not supply them.
- The published JSON schemas are inside the package. The general
  `schema_validation.py` loader reads project-owned validator schemas; those
  must remain separate from engine-owned package resources.
- Existing contracts explicitly preserve old imports and schema paths. The
  compatibility fixtures preserve exact state, hash, response, and adapter
  bytes, so neither bulk replacement nor blanket fixture regeneration is safe.
- Release tests exercise source exports without installation. Additional
  regular-install tests are needed to prove this product's intended use.

See the current [public contracts](../../docs/reference/contracts.md),
[architecture](../../docs/reference/architecture.md), and
[test map](../../tests/README.md).

## Invariants and scope limits

- Support Python 3.11 and newer; keep third-party **runtime** dependencies empty.
  Build and development tooling may be third-party dependencies, declared
  separately and never imported by the runtime.
- Keep phase names and policies in consumer configuration. The engine does not
  acquire release-documentation or implementation-specific behavior.
- Preserve immutable visit outputs, read-only enforcement, approval invalidation,
  atomic validated persistence, event reconciliation, and existing CLI ownership.
- Do not rename `.specromancy`, workflow directories, harness discovery paths,
  pipeline IDs, or run schemas merely to match the distribution name.
- Do not introduce a setup/scaffolding command that writes consumer-owned
  configuration. Users explicitly copy or author example files themselves.
- Never edit live run artifacts for migration. No automatic conversion of run
  records, repository reset, staging, committing, or project cleanup is added.
- Do not edit `game-of-life/` or historical documents. Preserve the original
  compatibility records and add versioned expectations for intentional changes.
- This plan authorizes no registry publication, remote repository rename, tag,
  or external service change. Release preparation ends with local artifacts.

## Verification and completion policy

For each implementation stage, run its focused checks and then
`python -m unittest discover`. From Stage 2 onward, first install the current
tree into the active development environment with `python -m pip install -e .`.
Repeat installation after changing entry points or package discovery metadata.
The test suite itself must not download dependencies.

Verify generated files with `bin/specromancy adapters generate --check` while
the checkout launcher remains, and also with installed
`specromancy adapters generate --check` after packaging exists. Regenerate only
through canonical sources when their inputs change. Record command, interpreter,
exit code, test count, and any skips; do not label a stage complete from an
intended command list. Baseline tests have not been executed as part of writing
this plan.

The final distribution gate uses a fresh environment, a non-editable install,
and a separate consumer directory without producer source on `PYTHONPATH`.
It must execute an entire custom workflow and replay representative old states.
Wheel and source-distribution contents must be inspected explicitly.

## Packaging references

- [PyPA: src versus flat layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
  explains why editable development and regular-install verification differ.
- [PyPA: writing pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
  defines project metadata, runtime dependencies, and console scripts.
- [Setuptools: package data](https://setuptools.pypa.io/en/latest/userguide/datafiles.html)
  covers inclusion of schemas and other package resources.
- [Python: importlib.resources](https://docs.python.org/3.11/library/importlib.resources.html)
  provides resource access without depending on a source-checkout path.

These references support the packaging mechanics. Stage boundaries, compatibility
choices, and release gates are recommendations specific to this repository.
