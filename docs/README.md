# Documentation

Current documentation is organized by purpose:

- [Installation](guides/installation.md): CLI-only and Python dependency consumer routes.
- [Release-documentation example](../examples/release-documentation/README.md): wheel-only lifecycle walkthrough.
- [Architecture](reference/architecture.md): runtime responsibilities and dependencies.
- [Public contracts](reference/contracts.md): stable imports, CLI behavior, and persisted data.
- [CLI reference](reference/cli.md): commands, responses, and exit codes.
- [Harness compatibility](reference/harness-compatibility.md): supported discovery surfaces.
- [Pipeline authoring](guides/authoring-pipelines.md): configure graphs and validators.
- [Harness usage](guides/harnesses.md): run workflows from supported agent harnesses.
- [Workflow customization](../workflow/README.md): editable sources and pipeline registration.

[Historical plans and refactoring records](implementation-history/README.md) document prior work;
use the references and guides above for current behavior.

## Repository map

| Location | Purpose |
| --- | --- |
| `pyproject.toml` | Build metadata, package discovery, schema data, and installed CLI |
| `src/specromancy_engine/` | Public Python entry points and shared runtime utilities |
| `src/specromancy_engine/_config/` | Private configuration parsing, models, and serialization |
| `src/specromancy_engine/_runs/` | Private run records, persistence, and visit preparation/decisions |
| `src/specromancy_engine/_engine/` | Private approval, validation, provenance, and response orchestration |
| `src/specromancy_engine/_adapters/` | Private adapter source capture, rendering, and ownership |
| `src/specromancy_engine/_cli/` | Private command metadata and pipeline selection |
| `src/specromancy_engine/schemas/` | Published JSON schemas |
| `bin/` | Executable launcher |
| `workflow/` | This repository's configured development registry, graphs, and templates |
| `.agents/skills/` | This repository's canonical procedures and manifest-owned launch skills |
| `adapters/` | Generation entry point and generated-file ownership manifest |
| `.claude/`, `.github/`, `.opencode/` | Harness discovery files owned by the adapter manifest |
| `tests/engine/` | Engine unit/contract tests, evaluations, and test-owned fixtures |
| `tests/shipped_configuration/` | Validation of the shipped workflow and generated adapters |
| `tests/packaging/` | Installed consumer contracts and executable documentation checks |
| `examples/release-documentation/` | Consumer-owned registry, graph, skills, templates, and sample request; outside the wheel |
| `docs/reference/`, `docs/guides/` | Current documentation |
| `docs/implementation-history/` | Implementation records |
| `.specromancy/runs/` | Ignored local run state and immutable visit artifacts |

The underscore-prefixed Python packages are internal implementation details.
Public imports use `specromancy_engine`, including its `config`, `engine`,
`run_store`, `registry`, `adapters`, and `cli` facades. See the
[public contracts](reference/contracts.md). Internal package initializers do not import
public facades or eagerly load sibling components.

See the [test guide](../tests/README.md) for discovery commands and compatibility
coverage. Generated adapters remain in harness-required locations; edit their
canonical sources and regenerate them through the CLI.

The [distribution verification guide](guides/distribution-verification.md) covers
the offline installed-artifact gates, sdist contents, pinned tooling, and CI.
