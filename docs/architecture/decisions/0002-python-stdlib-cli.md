# ADR 0002: Build a Python standard-library CLI

- Status: Accepted
- Date: 2026-09-20
- Decision owners: Specromancy maintainers

## Context

The coordinator must run consistently from five harnesses on macOS, Linux, and Windows; validate local contracts; manage files and locks; call Git safely; and remain easy to install and audit. It does not need to call a model provider or provide a hosted service.

## Decision

Implement the POC CLI in Python 3.11 or later using only the standard library at runtime. Use `argparse`, `json`, `pathlib`, `hashlib`, `subprocess` with argument arrays and `shell=False`, exclusive file creation for locks, sibling temporary files plus `os.replace` for atomic replacement, and `unittest` for the initial suite.

The CLI exposes both a `specromancy` console entry point and `python -m specromancy`. It emits human-readable output by default and a stable JSON envelope on request. Contract-specific validation is implemented locally; loading a JSON Schema does not imply adding a runtime schema library.

## Consequences

- The runtime has no third-party dependency supply chain.
- Python 3.11 becomes a prerequisite and must be documented and tested.
- Restricted frontmatter and JSON contract validation must be implemented rather than delegated to PyYAML or a JSON Schema package.
- Cross-platform behavior, especially filesystem syncing, process checks, and Git discovery, needs explicit tests and graceful platform-specific handling.
- Richer optional integrations can be added later without becoming POC requirements.

## Rejected alternatives

### Shell scripts

Rejected because quoting, structured JSON, locking, path safety, and Windows portability would be fragile.

### Node.js or TypeScript

Rejected because the POC gains no browser or package-ecosystem advantage, and a dependency tree would conflict with the minimal runtime goal.

### Third-party Python CLI, YAML, or schema libraries

Rejected for the POC to minimize installation and supply-chain surface. The intentionally restricted formats do not require general-purpose parsers.

### A provider SDK or agent runner in the CLI

Rejected because it would couple coordination to credentials, models, and provider semantics. Harnesses invoke skills; the CLI enforces state and contracts.
