# Specromancy contributor instructions

Specromancy is a standard-library Python CLI for durable, artifact-driven development. Runtime code lives in `src/specromancy/`, packaged contracts in `src/specromancy/resources/contracts/`, tests in `tests/`, architecture notes in `docs/architecture/`, and staged implementation plans in `docs/poc/implementation-plan/`.

Use Python 3.11 or later. Run focused tests first, then the complete contract suite with `python -m unittest discover -s tests -p 'test_*.py'`. Build distributions with `python -m build`; `build` is a development-only dependency.

Harness adapters are generated discovery or invocation surfaces. Never put unique workflow rules in an adapter or edit a generated adapter as its source of truth. Canonical phase procedures belong in `.agents/skills/`.

Runtime phase state lives in `.specromancy/runs/<run-id>/` artifacts and metadata, never in chat memory. Do not bypass validation, explicit approvals, repository confinement, locks, or bounded review cycles. Destructive operations, production changes, secrets access, and dependency additions require explicit user approval.

Avoid editing fixtures unless a test explicitly requires it. Preserve unrelated working-tree changes and keep runtime dependencies limited to the Python standard library.

