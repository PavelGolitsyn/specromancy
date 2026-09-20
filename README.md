# Specromancy

Specromancy is a harness-agnostic toolkit for artifact-driven, spec-driven development. Its proof of concept coordinates a durable `request -> research -> plan -> implement -> review` workflow without making a model provider or chat session the source of truth.

## POC terminology

- **Run:** One durable execution of the pipeline for a request, stored under `.specromancy/runs/<run-id>/`.
- **Phase:** One canonical unit of work: research, plan, implementation, or review. Orchestration coordinates phases but does not perform them.
- **Status:** The persisted state of a run, such as `research_ready`, `plan_approved`, or `passed`.
- **Artifact:** A Markdown phase handoff with restricted, versioned frontmatter and phase-specific validated content.
- **Manifest:** `run.json`, the current-state projection containing artifact digests, approvals, repository identity, and repair-cycle state.
- **Event log:** `events.jsonl`, the append-only audit history used to explain and replay manifest state.
- **Approval:** An explicit CLI record binding an approver-supplied identity to the exact validated plan digest. Approval in prose or chat does not count.
- **Canonical skill:** A workflow procedure in `.agents/skills/<name>/`; it is the source from which any harness-specific copy or launcher is generated.
- **Harness:** Codex, Claude Code, GitHub Copilot, Hermes, or OpenCode—the environment that invokes a skill and provides agent tools.
- **Adapter:** A generated harness discovery or invocation file. It contains no unique pipeline policy.
- **Repair cycle:** A bounded return from `changes_requested` to implementation, followed by a fresh review.
- **Validator:** Deterministic code that checks a manifest, artifact, repository subject, or transition guard before state can advance.

The version 1 architecture and public contracts are documented in [the POC architecture](docs/architecture/poc.md).
