# POC v3 implementation plan

## Objective

Build a minimal but robust, harness-agnostic agentic pipeline framework with:

- one canonical workflow definition;
- one canonical set of `SKILL.md` files;
- one stable command-line contract;
- artifact-based runtime state;
- thin, generated harness adapters.

The POC proves that a workflow can be reordered, extended, or replaced by editing the state-machine configuration and the Markdown skills/templates referenced by its phases. The Python engine must not contain knowledge of `research`, `plan`, `implement`, or `review`.

## Architectural boundary

The agent authors and reasons. The CLI enforces and records.

| Concern | Owner |
| --- | --- |
| Always-on repository rules | `AGENTS.md` |
| On-demand phase procedures | `.agents/skills/*/SKILL.md` |
| Phase graph and gates | `specromancy/pipeline.toml` |
| State transitions, hashes, validation, exit codes | `bin/specromancy` and Python package |
| Cross-phase state | `.specromancy/runs/<run-id>/` artifacts and manifest |
| Harness conventions | Generated adapters |

`pipeline.toml` is used for the POC instead of YAML so Python 3.11 can load it with `tomllib` and the CLI can remain dependency-free. If YAML becomes a hard product requirement, replace the configuration loader behind its existing interface and add a real YAML dependency; do not implement a partial YAML parser.

## Invariants shared by every stage

1. Runtime correctness must not depend on chat history.
2. Canonical skills use only portable Agent Skills frontmatter.
3. No state-machine phase name is hard-coded in the engine.
4. Every state change is atomic, validated, and represented in `run.json` and `events.jsonl`.
5. Read-only phases are checked mechanically.
6. A changed approved artifact invalidates its approval.
7. Cycles must be bounded in configuration.
8. Generated files are reproducible and may contain no unique workflow logic.
9. Commands have stable exit codes and a machine-readable `--json` form.
10. Work outside `.specromancy/` is never deleted or reverted by the CLI.

## Stage order

| Stage | Purpose | Depends on |
| --- | --- | --- |
| [01](01-foundation-and-contracts.md) | Establish repository layout and public contracts | None |
| [02](02-pipeline-configuration.md) | Load and validate arbitrary state machines | 01 |
| [03](03-run-store-and-artifacts.md) | Persist recoverable run state and immutable artifacts | 01, 02 |
| [04](04-state-machine-and-cli.md) | Implement generic transitions and the CLI contract | 02, 03 |
| [05](05-validation-approvals-and-safety.md) | Enforce artifacts, mutations, approvals, and bounded loops | 03, 04 |
| [06](06-canonical-skills-and-example.md) | Add portable skills and the replaceable example pipeline | 02–05 |
| [07](07-generated-harness-adapters.md) | Expose canonical content to supported harnesses | 01, 04, 06 |
| [08](08-contract-tests-evals-and-release.md) | Prove portability, replaceability, recovery, and readiness | All prior stages |

Each stage must land with its tests passing. Later stages may refine interfaces, but must not silently change an earlier public contract; contract changes require updating the schema version and affected fixtures.

## POC completion criteria

The POC is complete when all of the following are true:

- A fresh clone works with Python 3.11+ without package installation.
- `bin/specromancy init "task"` creates a valid run.
- A run can be resumed from a new process with no conversation context.
- The example pipeline reaches a terminal state using only CLI transitions and artifacts.
- A fixture with entirely different phase names and ordering runs through the same engine.
- Read-only mutations, invalid artifacts, stale approvals, illegal transitions, and excessive loop iterations are rejected.
- Adapter generation is deterministic and `adapters generate --check` detects drift.
- Canonical skills contain no vendor-only model or tool-permission fields.
- `python -m unittest discover` passes all unit and contract tests.

## Explicit POC non-goals

- Starting or controlling a vendor harness from the CLI.
- Distributed or multi-host run coordination.
- Remote artifact storage or a database.
- A plugin marketplace or skill installation system.
- Rich JSON Schema support beyond the project-owned schemas.
- Sandboxing arbitrary validation commands beyond normal user permissions.
- A polished TUI, daemon, web service, or standalone binary build.

