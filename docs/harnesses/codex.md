# Codex

Tested documentation target: Specromancy 0.1.0 on 2026-09-23. Deterministic adapter checks were run; no provider-backed Codex session is claimed by the automated suite.

## Discovery and trust

Codex reads the repository's `AGENTS.md` and canonical `.agents/skills/<name>/SKILL.md` files directly. `specromancy adapters generate --harness codex` creates no workflow copy, while `adapters check` validates all five canonical skills. Review repository instructions and skills before trusting the project; discovery does not grant them extra authority.

## Shared minimal example

```bash
specromancy adapters check --harness codex
specromancy init --id minimal-greeting --request examples/minimal/request.md
```

Invoke the complete pipeline with `$pipeline Continue run minimal-greeting.` Individual phases are `$research Research run minimal-greeting.`, `$plan Plan run minimal-greeting.`, `$implement Implement run minimal-greeting.`, and `$review Review run minimal-greeting.`

When the plan is ready, inspect it and run `specromancy approve minimal-greeting plan --by YOUR_IDENTITY`; then invoke `$pipeline Continue run minimal-greeting.` again.

## Permissions, resume, and cleanup

Codex permissions come from the user's execution environment. They may add tool approvals but cannot replace Specromancy's digest-bound gate. The adapter chooses no model, reasoning level, or paid service. Procedural review independence is required, but the adapter does not claim a separate operating-system identity.

Resume any later session with `$pipeline Continue run minimal-greeting.` and confirm `specromancy status minimal-greeting` first. `specromancy adapters clean --harness codex` removes no canonical file. Cancellation and adapter cleanup preserve `.specromancy/runs/` and user source.

## Known limitations and troubleshooting

- No minimum Codex version is asserted and no live provider run is release-blocking.
- If a skill is missing, verify `.agents/skills/<name>/SKILL.md`, its `name`/`description` frontmatter, and repository root discovery; then restart the session.
- If state and chat disagree, trust `status`, `next`, and validated artifacts.
- Run `specromancy doctor` and [the general checklist](../troubleshooting.md) before recovering locks or artifacts.
