# Stage 02 — Source layout and packaging

Status: planned. Dependency: [Stage 01](01-contracts-and-baseline.md).
Next: [Stage 03](03-python-namespace.md). Index: [migration plan](README.md).

## Objective

Make the engine installable and move it under `src/` while temporarily retaining
the `specromancy` import name. Separating the physical move from the namespace
change keeps failures attributable to one change at a time. This intermediate
build is for local verification, not publication.

## Intended files

- Move the complete tracked `specromancy/` tree to `src/specromancy/`, including
  all public modules, private packages, package initializers, and four schemas.
- Add `pyproject.toml`; update `.gitignore` for `.venv/`, `build/`, `dist/`, and
  package metadata such as `*.egg-info/` without ignoring real source files.
- Update `bin/specromancy` and `adapters/generate.py`.
- Update `tests/engine/contract/test_architecture.py`, `test_release.py`,
  `test_launcher.py`, and `tests/shipped_configuration/test_layout.py`.
- Update `AGENTS.md`, `README.md`, `docs/README.md`, relevant references,
  `workflow/README.md`, and `tests/README.md` to match this intermediate layout.
- Regenerate manifest-recorded adapters if canonical instructions change.

## Work

1. Add standard build metadata using setuptools as the proposed backend. Declare
   the distribution name `specromancy-engine`, Python `>=3.11`, MIT license,
   README, current version, and `dependencies = []`. Select and record a backend
   version that supports the chosen metadata and Python 3.11. Build requirements
   are separate from runtime dependencies; do not use a custom installer hook.
2. Configure discovery only under `src/` and only for `specromancy` and its
   subpackages. Do not add `src/__init__.py` or make `src` an import namespace.
   Disable unnecessary namespace discovery for these regular packages.
3. Explicitly include `schemas/*.json` as package data. Configure distribution
   inclusion so wheel contents cannot accidentally contain root workflows,
   developer skills, tests, `.specromancy`, or `game-of-life/`.
4. Add the temporary console-script entry point:

   ```toml
   [project.scripts]
   specromancy = "specromancy.cli:main"
   ```

5. Adjust the two checkout wrappers to insert the checkout's `src/` directory,
   then delegate to the existing CLI. Keep them free of engine policy. Preserve
   their existing installation-free source-export behavior as a developer
   convenience; installed consumers must not need either file.
6. Update static source scans to inspect `src/specromancy/`. Assert that the
   source root exists and that recursive scans return files, so a wrong path
   cannot silently make architecture checks pass.
7. Keep all Python imports, public exports, internal boundaries, CLI semantics,
   and fixture payloads unchanged in this stage. Update only physical paths in
   tests and documentation; historic descriptions remain historic.
8. Document editable development installation before the unchanged test command.
   Avoid adding `sys.path` mutations or `PYTHONPATH=src` to the test harness.
9. Keep package and metadata versions consistent; test that consistency. The
   breaking version bump belongs in Stage 3, not this intermediate layout move.

## Verification

In a dedicated development environment:

```sh
python -m pip install -e .
python -m specromancy --help
specromancy --help
python -m unittest tests.engine.contract.test_launcher tests.engine.contract.test_release
python -m unittest tests.engine.contract.test_architecture tests.engine.contract.test_compatibility
python -m unittest discover
bin/specromancy adapters generate --check
```

Install the build frontend in a separate build environment and run
`python -m build`. Inspect wheel contents with standard-library `zipfile`; verify
all nested modules and four JSON schemas are included. Install that exact wheel
with `pip install --no-deps` into a fresh environment and run both entry points
from a temporary directory outside the checkout. Assert the imported module
comes from that environment's installation, not `src/`.

Keep dependency acquisition out of unit tests. Record the build commands and
artifact paths, and do not commit `.venv`, archives, or package metadata outputs.

## Acceptance criteria

- [ ] The source tree resides under `src/specromancy/` with no duplicate runtime.
- [ ] Editable installation and a regular wheel installation both work.
- [ ] All schemas are packaged; no third-party runtime requirements appear.
- [ ] Source-export launcher behavior and existing compatibility tests pass.
- [ ] Full suite and adapter drift checks pass.
- [ ] Documentation and repository instructions reflect the current layout.

## Recovery and handoff

If installation fails, repair discovery or metadata before renaming imports.
For a rollback, restore only this stage's reviewed file moves/configuration and
reinstall the preceding package in the test environment. Do not delete runtime
state or unrelated files. Hand off a working package build to Stage 3.
