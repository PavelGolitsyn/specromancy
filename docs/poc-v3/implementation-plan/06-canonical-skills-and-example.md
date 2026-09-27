# Stage 06 — Canonical skills and replaceable example pipeline

## Outcome

Provide a small research → plan → implement → review example that demonstrates the engine without making those phases part of the architecture.

## Files introduced

```text
.agents/skills/pipeline/SKILL.md
.agents/skills/research/SKILL.md
.agents/skills/plan/SKILL.md
.agents/skills/implement/SKILL.md
.agents/skills/review/SKILL.md
specromancy/templates/request.md
specromancy/templates/research.md
specromancy/templates/plan.md
specromancy/templates/implementation.md
specromancy/templates/review.md
tests/fixtures/replacement-pipeline/
```

## Work items

### 1. Apply the portable skill format

Canonical `SKILL.md` files use only:

- `name`;
- `description`;
- `license`;
- `compatibility`;
- string-to-string `metadata`.

Names match their directory names and use lowercase hyphenated identifiers. Descriptions state what the skill does and when it should be loaded. Do not add vendor-specific model, permission, tool, or context settings.

### 2. Use one standard phase procedure

Every phase skill follows the same lifecycle:

1. Obtain `RUN_ID` from the user invocation.
2. Run `bin/specromancy status RUN_ID --json`.
3. Verify that the skill matches the current phase.
4. Start or resume the visit and read the action packet.
5. Read only its resolved inputs and necessary repository context.
6. Respect the declared mutation policy.
7. Write only the exact output artifact and permitted repository files.
8. Request approval or block when a declared condition applies.
9. Run the exact validation command from the packet.
10. Report the recorded next state rather than claiming success from memory.

Shared lifecycle text may live in the `pipeline` skill and be referenced concisely, but each phase skill must remain understandable when loaded alone.

### 3. Implement the pipeline skill

The orchestrator skill:

- initializes or resumes a run;
- treats CLI state as authoritative;
- loads or follows the current phase's canonical skill;
- stops for approval, block, failure, or completion;
- never assumes a fixed list or ordering of phases;
- never edits `run.json` directly.

It must not reproduce the state-machine graph in prose.

### 4. Keep example phase skills shallow

The example is a behavioral demonstration, not a permanent software-development methodology.

- **Research:** read-only; summarize relevant repository evidence and uncertainties.
- **Plan:** read-only; map requirements to intended files, tests, and verification.
- **Implement:** writable; make approved changes and record deviations and verification.
- **Review:** read-only; inspect changes and choose `approved` or `changes-requested`.

Avoid elaborate domain research, project-management ceremonies, or vendor-specific delegation rules.

### 5. Define templates as contracts

Templates should contain explicit required headings and short guidance. Example planning headings:

```text
# Plan
## Scope
## Requirement mapping
## Intended files
## Tests
## Verification
## Risks and approvals
```

Implementation records departures from the approved plan. Review records an outcome and actionable findings. Do not store pipeline state in prose that the CLI cannot verify.

### 6. Configure the example graph

Default flow:

```text
research -> plan -> [approval] -> implement -> review
                                      ^             |
                                      | changes     |
                                      +-------------+
```

The actual repair edge should return review changes to implementation, with a maximum of three repair traversals. Research, plan, and review are read-only. Implementation has repository-write access.

### 7. Prove replaceability

Create a fixture pipeline with unrelated semantics, for example:

```text
inspect -> transform -> verify
```

Use different skills, templates, headings, transitions, and one branch. Do not modify or subclass the engine. Its end-to-end contract test must use the same CLI entry points.

### 8. Validate skill security

Review each canonical skill and referenced file for:

- implicit network access;
- secret requests;
- destructive commands;
- direct manifest edits;
- instructions that bypass validation or approval;
- assumptions about a particular harness.

## Tests

- All skills have valid portable frontmatter and matching directory names.
- Skills reference only existing CLI commands and templates.
- Default pipeline follows expected mutation and approval gates.
- Review repair loop blocks at its configured limit.
- Replacement pipeline completes with no engine changes.
- Static scan rejects vendor-only canonical frontmatter fields.

## Exit criteria

- The example pipeline is usable but clearly replaceable.
- The orchestrator derives every current action from the CLI.
- Canonical skills are portable and vendor-neutral.
- A wholly different fixture pipeline proves configurability.

