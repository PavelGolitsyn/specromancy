# Stage 04 consumer-root and resource verification

This records a stage of the 0.1.0 implementation. Artifacts are identified by
stage and original hash; historical command excerpts use explicit artifact-path
placeholders where obsolete filenames have been omitted.

Completed on 2026-10-11 for [Stage 04](../04-consumer-roots-and-resources.md).
All checks ran on macOS arm64. No runtime, package metadata, published schema,
canonical workflow, generated adapter, or persisted format changes were needed.

## Path audit

| Surface | Existing authority preserved |
| --- | --- |
| `cli.discover_repository_root` | Working-directory ancestors with a `.git` directory or file; explicit existing `--root` overrides discovery |
| `registry.load_registry` | Mandatory consumer `workflow/pipelines.toml`; contained paths under `workflow/pipelines/`; explicit initialization ID |
| `_cli/pipeline_selection.py` | Existing runs resolve the saved path and ID through the selected consumer's `RunStore` |
| `_config/config_loader.py` | Explicit root or Git discovery from the graph path; graph must remain inside that root |
| `_config/config_fields.py` / `config_phase_parser.py` | Skills resolve from the consumer root; templates and validator files from the graph directory; resolved paths must stay inside the consumer |
| `actions.py` / `run_store.py` | Packets derive absolute paths and validation argv from the consumer root; run writes remain under its owned run directory |
| `schema_validation.py` | Unchanged project-file `load_json_schema(path)` and limited schema subset |
| `schemas/` / package data | Four published JSON documents already ship with the package; runtime loaders do not need to load them |

The runtime search found no `__file__`-derived project root, `Path.home()`
configuration lookup, or package-relative fallback. `expanduser()` applies only
to caller-supplied paths. No production resource helper or filesystem extraction
was added. Unit tests that inspect published pipeline and registry schemas now
read through `importlib.resources.files("specromancy_engine").joinpath(...)`.

## Permanent coverage and documentation

`tests/packaging/test_consumer_roots.py` is self-contained and can be copied out
of the checkout to run against a wheel. It needs only the installed engine,
standard library, and Git; it neither builds nor downloads dependencies.

- Two consumers register ID `shared` at the same relative path, with different
  graphs, skills, templates, requests, and project-owned JSON validator contents.
  One has a normal `.git` directory; the other is a real linked worktree.
- Console initialization from both roots and nested directories, module status
  from an unrelated directory with explicit roots, dynamic phases, emitted
  validation argv, and completion all use the selected consumer. Looking up a
  run in the other consumer returns `NOT_FOUND`.
- Public registry, pipeline, engine, and store facades are retained and
  interleaved in one Python process, along with in-process CLI calls. Each
  consumer's schema rejects an incorrect result, accepts its own result, and
  persists the correct graph hash and project-relative path.
- Existing runs retain their saved graph after the registry retargets the same
  ID. New runs use the new registration. Missing registries still fail for both
  new and existing runs; mismatched selectors remain usage errors.
- Explicit non-Git initialization requires the configured opt-in. Missing
  roots, file roots, missing selectors, and discovery without a Git marker keep
  their diagnostics and do not create state.
- Published resource availability checks parse all four JSON documents without
  applying the project validator's limited subset.
- Before/after snapshots include file bytes, modes, links, empty directories,
  and Git metadata. Successful lifecycle commands add only consumer run storage;
  rejected root/selector commands leave all captured files unchanged.

Two new root-discovery unit tests cover root/nested/file starts, cwd selection,
explicit override, and invalid-root details. Existing config/registry tests
continue to cover traversal, symlink containment, unsupported schema keywords,
and resource reloading.

The public contracts and authoring guide now distinguish engine-owned published
schemas from consumer-owned artifact validators, explain installed root
selection, and show existing Python facades with explicit roots and saved
provenance. Both embedding examples and the package-resource example were
executed against the regular installation (substituting a temporary consumer
for the documented absolute path).

## Commands and results

Dedicated environments are under `/private/tmp/specromancy-migration-04/`:
`dev311`, `dev314`, and `wheel`. Interpreters are Python 3.11.15 and 3.14.4.
Both development environments first installed the checkout with:

```sh
python -m pip install --no-index \
  --find-links /private/tmp/specromancy-migration-02/build-tools -e .
```

Previously downloaded setuptools 84.0.0 supplied the build dependency. Tests
did not download packages. Each full run put its environment's `bin/` first on
`PATH`, including for nested launcher and emitted-command subprocesses.

| Environment | Command/check | Tests | Seconds | Exit |
| --- | --- | ---: | ---: | ---: |
| Python 3.11.15 editable | Focused command below | 56 | 2.187 | 0 |
| Python 3.11.15 editable | `python -m unittest discover` | 259 | 30.682 | 0 |
| Python 3.14.4 editable | `python -m unittest discover` | 259 | 36.897 | 0 |
| Python 3.11.15 wheel | Copied consumer smoke suite, read-only package | 5 | 2.826 | 0 |
| Python 3.11.15 wheel | Three documented Python examples | — | — | 0 |
| Both editable environments | `specromancy adapters generate --check` | — | — | 0 |
| Python 3.11.15 checkout wrapper | `bin/specromancy adapters generate --check` | — | — | 0 |

The focused command was:

```sh
python -m unittest tests.packaging.test_consumer_roots \
  tests.engine.unit.test_cli tests.engine.unit.test_config \
  tests.engine.unit.test_registry
```

Final runs had no errors, failures, or skips. `git diff --check` passed. Logs are
`tests311.log`, `tests314.log`, and `wheel-smoke.log` in the verification directory.

## Regular wheel and write isolation

A clean temporary export copied only tracked and nonignored files, excluding
Git metadata and stale build output. The regular wheel was built offline:

```sh
python -m pip wheel --no-index \
  --find-links /private/tmp/specromancy-migration-02/build-tools --no-deps \
  /private/tmp/specromancy-migration-04/export \
  --wheel-dir /private/tmp/specromancy-migration-04/dist
```

Stage 04 wheel has SHA-256
`776263c37ccc9716408f064a09cf9a7ab6ac6da53ead853204a34784c6e08c49`.
Archive inspection confirmed all four schema bytes match the source and that
the wheel contains only the engine package and distribution metadata.

A fresh environment installed that wheel with `pip install --no-index --no-deps`.
The probe ran outside the checkout with `python -I -B`, inherited `PYTHON*` and
`GIT_*` variables cleared, user sites disabled, bytecode writes disabled, an
empty home, and `PATH` restricted to the wheel environment plus system command
directories. The only copied Python source was the self-contained test module.
It asserted the imported package was under the isolated environment:

```text
/private/tmp/specromancy-migration-04/wheel/lib/python3.11/site-packages/specromancy_engine/__init__.py
```

The installed package tree had all write bits removed; `os.access(..., W_OK)`
confirmed no package file or directory was writable. The separate home was also
read-only. Full before/after snapshots confirmed no changes to the producer
checkout (including Git metadata), installed package, or home. Consumer tests
separately enforced their run-only write boundary.

The local driver, isolated probe, archive inventory, and machine-readable report
remain as `verify_wheel.py`, `probe.py`, `wheel-contents.txt`, and
`wheel-report.json` in the verification directory. The permanent smoke suite
can be rerun with an installed environment's Python using
`python -B -m unittest discover -s /path/to/copied/smoke`.

Stage 05 can now rely on an installed CLI scoped to the consumer project.
Linux/Windows execution and portable generated instruction changes remain
outside this stage; no live runs were moved or rewritten.
