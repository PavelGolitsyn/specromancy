# ADR 0001: Use an artifact-driven pipeline

- Status: Accepted
- Date: 2026-09-20
- Decision owners: Specromancy maintainers

## Context

The POC must start in one agent harness and resume in another without treating either harness's conversation, memory, or proprietary task state as authoritative. Research, planning, implementation, review, approvals, and repair cycles also need deterministic validation and an auditable history.

## Decision

Use repository-local, versioned artifacts as the handoff boundary between phases. Canonical phase inputs and outputs live under `.specromancy/runs/<run-id>/`; `run.json` is the current-state projection, `events.jsonl` is the append-only audit log, and Markdown artifacts carry portable restricted frontmatter plus phase-defined content.

The CLI is the only component that changes run state. Skills author artifacts and scoped repository changes, then request validation and transition. Digests bind completed artifacts, approvals, implementation inputs, and review subjects. Later phases discover all authoritative inputs from files and repository state, not conversation history.

## Consequences

- Runs can be inspected, resumed, and validated without a provider session.
- Human-readable work products and machine-enforced state stay connected by digests.
- Concurrent writers require locking, atomic writes, and recovery semantics.
- Artifact and event retention increases repository-local storage, though runtime runs remain uncommitted by default.
- Editing a completed artifact invalidates downstream bindings instead of being silently accepted.

## Rejected alternatives

### Conversation history as state

Rejected because history is harness-specific, may be truncated, is difficult to validate, and cannot reliably resume across tools.

### One mutable orchestration document

Rejected because phase ownership, approval binding, independent review, and structured recovery would be ambiguous in a single prose file.

### Provider-hosted or remote state

Rejected for the POC because it adds credentials, availability, privacy, and provider-coupling concerns without proving the local portability claim.

### Git commits as the only state

Rejected because research and planning artifacts, in-progress state, dirty-worktree preservation, explicit approval, and failed validations do not map cleanly to commits.
