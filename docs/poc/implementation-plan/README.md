# Specromancy POC Implementation Plan

## Purpose

This plan defines a proof of concept for a harness-agnostic, artifact-driven agentic software-development pipeline:

```text
request -> research -> plan -> implement -> review
                                      ^         |
                                      |---------|
                                      bounded repair loop
```

The POC must work from Codex, Claude Code, GitHub Copilot, Hermes, and OpenCode without making any one harness the source of truth.

## POC outcome

At the end of the plan, a user can install Specromancy into a Git repository, initialize a run, invoke the same logical phase from any supported harness, inspect durable artifacts, resume after interruption, and receive an independently validated review result.

The POC proves these claims:

1. `AGENTS.md` can hold the canonical always-on project instructions.
2. `.agents/skills` can hold the canonical workflow skills.
3. A portable CLI can enforce state transitions and artifact contracts.
4. Thin generated adapters can cover harness-specific discovery and invocation.
5. The pipeline can resume from files without depending on conversation history.
6. Deterministic validation can reject incomplete or invalid agent output.

## Scope

Included:

- A Python 3.11+ standard-library CLI.
- Local repository runs under `.specromancy/runs/`.
- Canonical research, plan, implement, review, and orchestration skills.
- JSON run state and machine-readable artifact metadata.
- Markdown artifacts intended for both people and agents.
- Explicit plan approval.
- A bounded implementation/review repair loop.
- Generated Claude Code, Copilot, and OpenCode adapters.
- Native use from Codex and Hermes through `AGENTS.md` and `.agents/skills`.
- Contract tests, fixtures, and a small behavioral evaluation suite.

Deferred:

- Hosted orchestration service.
- Direct API calls to model providers.
- A graphical interface.
- Multi-repository or distributed runs.
- Automatic pull-request creation.
- Package registries beyond a local install and a Python package build.
- Cryptographic signing of skills or artifacts.

## Stage order

| Stage | Document | Primary result |
|---:|---|---|
| 0 | [Architecture and contracts](00-architecture-and-contracts.md) | Frozen POC boundaries and interfaces |
| 1 | [Repository foundation](01-repository-foundation.md) | Installable CLI skeleton and test layout |
| 2 | [Research stage](02-research-stage.md) | Evidence-backed `research.md` workflow |
| 3 | [Plan stage](03-plan-stage.md) | Approval-ready `plan.md` workflow |
| 4 | [Implement stage](04-implement-stage.md) | Controlled code changes and implementation record |
| 5 | [Review stage](05-review-stage.md) | Independent, severity-ranked review workflow |
| 6 | [Orchestration and CLI](06-orchestration-and-cli.md) | State machine, resume, gates, and repair loop |
| 7 | [Harness adapters](07-harness-adapters.md) | Native discovery and commands for all five harnesses |
| 8 | [Validation, evaluations, and security](08-validation-evaluations-and-security.md) | Confidence and safety checks |
| 9 | [Documentation, packaging, and release](09-documentation-packaging-and-release.md) | Reproducible POC release |

Stages 0 and 1 are prerequisites for everything else. Stages 2 through 5 may be developed independently after the shared artifact helpers exist. Stage 6 integrates them. Stages 7 through 9 harden and distribute the result.

## Global definition of done

The POC is complete when:

- A clean fixture repository can be initialized without hand-editing generated files.
- The same run can be started in one harness and resumed in another.
- Each phase consumes only declared inputs and creates its declared outputs.
- Invalid transitions and malformed artifacts produce stable non-zero exit codes.
- Plan approval is recorded before implementation begins.
- Review can produce `passed`, `changes_requested`, or `blocked` deterministically.
- The repair loop stops at its configured limit.
- Generated adapters are reproducible and drift is detected in CI.
- Unit and contract tests pass on macOS, Linux, and Windows.
- At least one smoke scenario is documented for each supported harness.

## Planning conventions

Each stage document contains:

- objective and dependencies;
- deliverables and proposed files;
- ordered implementation tasks;
- tests and validation;
- exit criteria;
- known risks and explicit non-goals.

File paths describe the intended final repository and may be refined in Stage 0 only. Later changes to a frozen contract require an explicit decision record and corresponding test updates.

