# Stage 1: Repository Foundation

## Objective

Create the package, CLI skeleton, repository conventions, reusable test utilities, and installation surface required by every later stage.

## Dependencies

- Stage 0 contracts are approved.

## Deliverables

- `pyproject.toml`
- `src/specromancy/__init__.py`
- `src/specromancy/__main__.py`
- `src/specromancy/cli.py`
- `src/specromancy/errors.py`
- `src/specromancy/paths.py`
- `src/specromancy/io.py`
- `src/specromancy/clock.py`
- `src/specromancy/contracts.py`
- `tests/unit/`
- `tests/contract/`
- `tests/fixtures/repositories/minimal/`
- `AGENTS.md`
- `.gitignore` entries for run data and temporary files
- Updated root `README.md`

## Design constraints

- Support Python 3.11 and later.
- Use only the Python standard library at runtime.
- Use `argparse` for the CLI and `unittest` for the initial test suite.
- Provide the `specromancy` console entry point and `python -m specromancy` fallback.
- Emit human-readable text by default and JSON with `--format json`.
- Never depend on the caller's current directory after repository discovery completes.
- Ensure all timestamps and serialized paths are stable across platforms.

## Implementation tasks

### Package and command skeleton

1. Add package metadata, Python version, console script, license, and build configuration to `pyproject.toml`.
2. Implement a root command with `--version`, `--help`, `--format`, and `--repo`.
3. Register placeholder subcommands for `init`, `status`, `next`, `phase`, `artifact`, `approve`, `validate`, `resume`, and `adapters`.
4. Centralize exception-to-exit-code mapping in `errors.py`.
5. Define a result envelope with `ok`, `command`, `message`, `data`, and `errors` for JSON output.

### Repository and path discovery

1. Discover the nearest Git root using `git rev-parse --show-toplevel`.
2. Provide a filesystem fallback for tests that intentionally omit Git.
3. Normalize and resolve paths before use.
4. Reject paths escaping the repository root through `..`, symlinks, or absolute artifact paths.
5. Encapsulate `.specromancy/config.json`, `.specromancy/runs/`, and run artifact paths in a path service.

### Safe I/O primitives

1. Add UTF-8 read helpers with useful path-aware errors.
2. Add atomic JSON and text writes using sibling temporary files and `os.replace`.
3. Add canonical JSON serialization with sorted keys and a final newline.
4. Add SHA-256 helpers for files and normalized text.
5. Add append-only JSON Lines event writing.
6. Add an injectable clock and deterministic run-ID generator for tests.

### Contract loading

1. Package the Stage 0 JSON contracts as importable resources.
2. Load and cache them through one module.
3. Fail at startup with exit code 4 if packaged contracts are invalid.
4. Expose the schema and pipeline versions through `specromancy --version --format json`.

### Project instructions

Create a concise root `AGENTS.md` containing:

- repository purpose and map;
- canonical build and test commands;
- rules for generated adapters;
- rule that runtime phase state lives in artifacts, not chat memory;
- safety and approval invariants;
- requirement to run focused tests followed by the contract suite;
- instruction to avoid editing fixtures unless a test explicitly requires it.

Keep phase-specific procedures out of `AGENTS.md`; those belong in skills.

## Testing

- CLI help and version snapshots.
- JSON and text output modes.
- Git-root discovery from nested directories.
- Path traversal and symlink escape rejection.
- Atomic-write replacement behavior.
- Stable hashing and canonical JSON output.
- Exception-to-exit-code mapping.
- Package-resource loading from both a source checkout and built wheel.
- Windows path separator fixtures.

## Validation commands

```bash
python -m unittest discover -s tests -p 'test_*.py'
python -m build
python -m specromancy --help
python -m specromancy --version --format json
```

If `build` is not available in the development environment, document it as a development-only dependency and keep it out of the runtime dependency set.

## Exit criteria

- The package installs into an isolated environment.
- All placeholder commands return documented exit codes and structured output.
- Tests can create isolated temporary repositories without touching the developer's checkout.
- Contract resources are accessible after packaging.
- `AGENTS.md` is concise and contains no harness-specific workflow logic.

## Risks and mitigations

- **Python launcher differences:** document both `specromancy` and `python -m specromancy`; test `py -m specromancy` on Windows CI.
- **Git absence:** fail clearly for real runs but permit explicit non-Git test fixtures.
- **Packaging resources incorrectly:** include a wheel-install smoke test before Stage 2.

