# Documentation

Current documentation is organized by purpose:

- [Architecture](reference/architecture.md): runtime responsibilities and dependencies.
- [Public contracts](reference/contracts.md): stable imports, CLI behavior, and persisted data.
- [CLI reference](reference/cli.md): commands, responses, and exit codes.
- [Harness compatibility](reference/harness-compatibility.md): supported discovery surfaces.
- [Pipeline authoring](guides/authoring-pipelines.md): configure graphs and validators.
- [Harness usage](guides/harnesses.md): run workflows from supported agent harnesses.
- [Workflow customization](../workflow/README.md): editable sources and pipeline registration.

[Historical plans and refactoring records](history/README.md) document prior work;
use the references and guides above for current behavior.

## Repository map

| Location | Purpose |
| --- | --- |
| `specromancy/` | Public Python entry points and shared runtime utilities |
| `specromancy/_config/` | Private configuration parsing, models, and serialization |
| `specromancy/_runs/` | Private run records, persistence, and visit preparation/decisions |
| `specromancy/_engine/` | Private approval, validation, provenance, and response orchestration |
| `specromancy/_adapters/` | Private adapter source capture, rendering, and ownership |
| `specromancy/_cli/` | Private command metadata and pipeline selection |
| `specromancy/schemas/` | Published JSON schemas |
| `bin/` | Executable launcher |
| `workflow/` | Canonical pipeline registry, graphs, and artifact templates |
| `.agents/skills/` | Canonical procedures and manifest-owned pipeline launch skills |
| `adapters/` | Generation entry point and generated-file ownership manifest |
| `.claude/`, `.github/`, `.opencode/` | Harness discovery files owned by the adapter manifest |
| `tests/engine/` | Engine unit/contract tests, evaluations, and test-owned fixtures |
| `tests/shipped_configuration/` | Validation of the shipped workflow and generated adapters |
| `docs/reference/`, `docs/guides/` | Current documentation |
| `docs/history/` | Implementation plans and completed refactoring records |
| `.specromancy/runs/` | Ignored local run state and immutable visit artifacts |

The underscore-prefixed Python packages are internal implementation details.
Existing public imports, including `specromancy.config`, `specromancy.engine`,
`specromancy.run_store`, `specromancy.adapters`, and `specromancy.cli`, retain
their paths. Internal package initializers do not import public facades or
eagerly load sibling components.

See the [test guide](../tests/README.md) for discovery commands and compatibility
coverage. Generated adapters remain in harness-required locations; edit their
canonical sources and regenerate them through the CLI.
