# Stage 04 — Consumer roots and package resources

Status: planned. Dependency: [Stage 03](../03-python-namespace/stage.md).
Next: [Stage 05](../05-portable-skills-and-adapters/stage.md).
Index: [migration plan](../README.md).

## Objective

Prove that an installed engine reads configuration and writes run state in the
consumer project, independently of the engine's source checkout. Keep engine
resources distinct from project-owned templates, validators, and skills.

## Intended files

Inspect the renamed `cli.py`, `registry.py`, `_cli/pipeline_selection.py`,
`_config/config_loader.py`, `_config/config_phase_parser.py`, `actions.py`,
`run_store.py`, `schema_validation.py`, and `schemas/`.

Extend `tests/engine/unit/test_cli.py`, `test_config.py`, `test_registry.py`,
contract coverage, and new `tests/packaging/` coverage as needed. Add a package
resource helper only if production code actually needs one. Update
`docs/reference/contracts.md` and `docs/guides/authoring-pipelines.md`.

## Work

1. Audit all path derivation after the move. The existing CLI root discovery is
   already based on working directory or explicit `--root`; preserve it rather
   than replacing it with a package-relative root.
2. Verify normal discovery from the consumer root and nested directories, `.git`
   directory and worktree-file markers, explicit roots from unrelated working
   directories, invalid roots, and non-Git behavior allowed by configuration.
   Do not add a new fallback to the producer checkout or an implicit pipeline.
3. Keep `workflow/pipelines.toml` mandatory and initialization selectors explicit.
   Existing runs must continue to resolve the saved pipeline path and ID.
   Preserve containment checks, traversal rejection, and error diagnostics.
4. Exercise two consumer projects through one installed package. Give them the
   same pipeline ID but different graph/template/skill contents. Verify each
   command uses its own root, inputs, outputs, registry, and run store without
   cached configuration leaking between projects.
5. Inventory the four published engine schemas and verify their installed
   availability. Read package resources through Python 3.11-compatible
   `importlib.resources.files("specromancy_engine").joinpath("schemas", name)`
   where resource access is needed. Use `as_file` only while an actual filesystem
   path is required, without persisting its temporary location in run records.
6. Keep the project-schema API `load_json_schema(path)` and configured validator
   resolution unchanged. Do not route arbitrary consumer schemas through the
   package-resource loader or expand the supported JSON Schema subset.
7. Document that published engine schemas and the subset schema validator serve
   different contracts. Resource availability tests should parse published JSON;
   they must not assume all published schemas use the validator's limited subset.
8. Verify no command needs write access to the installed package, producer
   checkout, or a home-directory configuration. Reads of installed code and
   resources are allowed; run mutations remain in the consumer's owned paths.
9. Document the existing Python embedding route using public facades and explicit
   consumer roots. Do not invent a new `Workflow` class or add a builder API as
   part of packaging. Confirm actual signatures before writing executable examples.

## Verification

Run focused CLI/configuration/registry tests and `python -m unittest discover`.
Build and install a regular wheel in a new environment; from a separate temporary
consumer root, test root selection, registry loading, initialization, status,
and package-resource reads through both the CLI and public Python API.

Use at least two consumers and an unrelated working directory. Clear inherited
`PYTHONPATH`, disable user-site interference, and assert the imported package
origin is inside the isolated environment. Run installed commands without the
producer checkout on `PATH`; add only the installed environment's bin directory.

Capture relevant project files and Git metadata before/after commands. Expected
run artifacts are the only workflow-command writes. For a read-only package
check, disable bytecode writes with `PYTHONDONTWRITEBYTECODE=1` so interpreter
cache behavior does not obscure engine ownership. Where supported, make the
installed package tree read-only during the smoke test.

## Acceptance criteria

- [ ] Installed engine works from consumer roots and nested directories.
- [ ] Explicit-root behavior and failure diagnostics remain compatible.
- [ ] Two projects using the same package cannot contaminate each other's state.
- [ ] All four schemas are present and readable in the installed package.
- [ ] Project-owned schemas, skills, and templates remain project-owned.
- [ ] No producer-checkout lookup or runtime package write is required.
- [ ] Public API smoke checks, focused tests, full suite, and adapter check pass.

## Recovery and handoff

Keep path changes minimal. A packaging omission should be fixed in package data
configuration, not by copying consumer configuration into the wheel. If a root
regression occurs, restore existing resolution behavior and add its reproducer.
Do not move consumer state. Stage 5 can now rely on an installed consumer CLI.
