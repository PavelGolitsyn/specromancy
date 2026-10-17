# Stage 03 — Python namespace migration

Status: complete (2026-10-11). Dependency: [Stage 02](02-source-layout-and-packaging.md).
Verification: [Stage 03 evidence](evidence/03-python-namespace.md).
Next: [Stage 04](04-consumer-roots-and-resources.md).
Index: [migration plan](README.md).

## Objective

Rename the import package to `specromancy_engine`, preserving engine behavior
and making the intentional Python API break explicit.

## Intended files

- Rename `src/specromancy/` to `src/specromancy_engine/`.
- Update `pyproject.toml` discovery, data-file configuration, version, and entry
  point; update the package version consistently.
- Update imports and qualified strings throughout `tests/`, both checkout
  wrappers, current documentation, and repository instructions.
- Update `actions.py` and add separately versioned response expectations for
  its emitted command prefix, as identified by Stage 01.
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
   docstrings and usage references as appropriate. Keep argparse's program
   name and status commands as `specromancy`. Stage 01 found that action packet
   `final_validation_command` currently starts with
   `[sys.executable, "-m", "specromancy"]`: deliberately replace that prefix
   with `["specromancy"]`, preserving all remaining arguments and their order.
   Do not rewrite consumer-configured validation commands. Execute emitted
   argv with the installed console script on PATH. Follow the
   [Stage 01 command-value decision](evidence/contracts.md#correction-action-commands-are-module-invocations-today).
5. Update test imports, string patch targets such as
   `specromancy.engine.utc_now`, synthetic `types.ModuleType` setup,
   `sys.modules` assertions, AST standard-library allowlists, schema paths, and
   subprocess module names. Treat these as distinct categories, not one global
   replacement of the word `specromancy`.
6. Preserve `.specromancy/`, `specromancy-<pipeline-id>` generated skill names,
   harness command directories, pipeline IDs, registry paths, and generator
   identity unless a later stage explicitly changes a separate contract.
7. Document the 0.1.0 namespace and invocation in current public contracts.
   Remove the present-tense promise that old development imports remain
   available. Explain that import compatibility and persisted-state
   compatibility are independent; no separate consumer release is involved.
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

Replay old state/canonical/diagnostic fixtures without refreshing them. Preserve
the original response capture and add separately reviewed versioned expectations
whose only differences are the action command prefixes in `action-pending`,
`action-active`, and `resumed`. Compare all other response fields exactly.
Namespace-dependent test machinery may change; persisted records may not.
Adapter bytes should remain unchanged for identical test-owned input at this
stage; the installed-command rendering change is reserved for Stage 5.

## Acceptance criteria

- [x] Wheel exposes `specromancy_engine` and the `specromancy` command.
- [x] Every public facade maps to the same behavior and re-export identities.
- [x] No duplicate legacy implementation or accidental package remains.
- [x] The import break and version are documented; stored formats remain stable.
- [x] Original state/hash/response compatibility, focused tests, and full suite pass.
- [x] Generated files match their canonical sources.

## Recovery and handoff

If a consumer requires old imports, resolve that compatibility policy before
release; do not patch it with an untested blanket alias. Restore only this
stage's namespace changes if reverting, and reinstall the previous verified
build. Keep consumer state untouched. Proceed with the renamed package to Stage 4.
