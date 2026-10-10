# Stage 03 — Python namespace migration

Status: planned. Dependency: [Stage 02](../02-source-layout-and-packaging/stage.md).
Next: [Stage 04](../04-consumer-roots-and-resources/stage.md).
Index: [migration plan](../README.md).

## Objective

Rename the import package to `specromancy_engine`, preserving engine behavior
and making the intentional Python API break explicit.

## Intended files

- Rename `src/specromancy/` to `src/specromancy_engine/`.
- Update `pyproject.toml` discovery, data-file configuration, version, and entry
  point; update the package version consistently.
- Update imports and qualified strings throughout `tests/`, both checkout
  wrappers, current documentation, and repository instructions.
- Inspect `tests/engine/contract/compatibility_support.py`, `test_compatibility.py`,
  `test_architecture.py`, `test_release.py`, and all `unittest.mock.patch` targets.
- Regenerate canonical-instruction mirrors and `adapters/manifest.json` when
  their source inputs change; do not hand-edit generated output.

## Work

1. Apply the Stage 1 compatibility decision. Under the default direct migration,
   remove the old import package from discovery and source. Do not leave two
   copies or an accidental old package in the distribution.
2. Keep the facade names and exported objects: consumers change
   `from specromancy import Engine` to `from specromancy_engine import Engine`.
   Preserve constructor signatures, exception identity across re-exports,
   compatibility aliases within the new namespace, and module responsibilities.
3. Update the final console-script declaration:

   ```toml
   [project.scripts]
   specromancy = "specromancy_engine.cli:main"
   ```

4. Change module invocations to `python -m specromancy_engine`. Update package
   docstrings and usage references as appropriate, but keep argparse's program
   name, action packet argv, and status commands as `specromancy`.
5. Update test imports, string patch targets such as
   `specromancy.engine.utc_now`, synthetic `types.ModuleType` setup,
   `sys.modules` assertions, AST standard-library allowlists, schema paths, and
   subprocess module names. Treat these as distinct categories, not one global
   replacement of the word `specromancy`.
6. Preserve `.specromancy/`, `specromancy-<pipeline-id>` generated skill names,
   harness command directories, pipeline IDs, registry paths, and generator
   identity unless a later stage explicitly changes a separate contract.
7. Record the breaking release version and migration instructions in current
   public contracts and release notes. Remove the present-tense promise that
   old public imports remain available. Explain that import compatibility and
   persisted-state compatibility are independent.
8. Reinstall the editable package after updating discovery and entry points.
   Build in a clean temporary export to avoid obsolete build output masking an
   incomplete rename. Do not use destructive repository cleanup commands.

## Verification

```sh
python -m pip install -e .
python -m specromancy_engine --help
specromancy --help
python -m unittest tests.engine.contract.test_compatibility
python -m unittest tests.engine.contract.test_architecture tests.engine.contract.test_launcher
python -m unittest discover
specromancy adapters generate --check
```

In a new environment containing only the new wheel, verify new imports and
module execution work and, under the direct migration policy, the old import
name is not supplied by this distribution. Do not use an environment that may
contain an unrelated distribution named `specromancy` for that assertion.

Search tracked current sources for old imports, dotted patch targets, module
invocations, and physical source paths. Review remaining hits individually:
history, preserved old fixtures, and upgrade documentation are allowed.

Replay old state/canonical/response/diagnostic fixtures without refreshing them.
Namespace-dependent test machinery may change; persisted records may not.
Adapter bytes should remain unchanged for identical test-owned input at this
stage; the installed-command rendering change is reserved for Stage 5.

## Acceptance criteria

- [ ] Wheel exposes `specromancy_engine` and the `specromancy` command.
- [ ] Every public facade maps to the same behavior and re-export identities.
- [ ] No duplicate legacy implementation or accidental package remains.
- [ ] The import break and version are documented; stored formats remain stable.
- [ ] Original state/hash/response compatibility, focused tests, and full suite pass.
- [ ] Generated files match their canonical sources.

## Recovery and handoff

If a consumer requires old imports, resolve that compatibility policy before
release; do not patch it with an untested blanket alias. Restore only this
stage's namespace changes if reverting, and reinstall the previous verified
build. Keep consumer state untouched. Proceed with the renamed package to Stage 4.
