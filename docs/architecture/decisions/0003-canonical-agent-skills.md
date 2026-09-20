# ADR 0003: Keep canonical agent skills in `.agents/skills`

- Status: Accepted
- Date: 2026-09-20
- Decision owners: Specromancy maintainers

## Context

Codex, Claude Code, GitHub Copilot, Hermes, and OpenCode use overlapping but non-identical instruction, skill, prompt, and command discovery conventions. Maintaining a full workflow independently for every harness would cause semantic drift and make it unclear which copy governs behavior.

## Decision

Make `AGENTS.md` the canonical always-on project instruction file and `.agents/skills/<name>/` the canonical source for research, plan, implementation, review, and pipeline procedures. The CLI contracts remain the machine-enforced authority.

Where a harness cannot consume a canonical file directly, generate deterministic, provenance-marked adapters. Adapters may mirror or wrap canonical content only for discovery and invocation. Generated files are checked for drift and never contain unique workflow logic, model selection, provider configuration, or weaker permissions.

## Consequences

- Phase authors edit one procedure and regenerate any affected adapters.
- Generated copies must preserve referenced assets and be tested for deterministic output.
- User-authored harness configuration must be collision-checked and never silently overwritten.
- Some harnesses require trust or setup steps; these are documented as harness concerns rather than pipeline semantics.
- Native permissions may enforce stricter limits but cannot authorize behavior forbidden by the canonical policy.

## Rejected alternatives

### Harness-specific canonical workflows

Rejected because duplicated procedures would drift and make cross-harness resume unsafe.

### Symlink every harness directory to `.agents/skills`

Rejected because symlink support and discovery behavior vary, especially on Windows and in hosted environments.

### Generate `.agents/skills` from a harness-specific format

Rejected because it would make one harness the source of truth and weaken the portability claim.

### Put every phase procedure in `AGENTS.md`

Rejected because always-on instructions would become large, phase boundaries would blur, and harness skill invocation could not load only the relevant procedure.
