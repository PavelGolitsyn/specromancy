# Claude Code

Tested documentation target: Specromancy 0.1.0 on 2026-09-23. Deterministic adapter generation/checks were run; no provider-backed Claude Code session is claimed by the automated suite.

## Discovery and trust

The adapter generates `CLAUDE.md` from `AGENTS.md` and complete skill copies under `.claude/skills/`. Copies preserve relative references and executable modes, normalize text, and carry provenance. `.agents/skills/` remains authoritative. Review repository skills before trusting them.

```bash
specromancy adapters generate --harness claude
specromancy adapters check --harness claude
specromancy init --id minimal-greeting --request examples/minimal/request.md
```

## Shared minimal example and invocation

Invoke `/pipeline Continue run minimal-greeting.` Individual phases are `/research Research run minimal-greeting.`, `/plan Plan run minimal-greeting.`, `/implement Implement run minimal-greeting.`, and `/review Review run minimal-greeting.`

At `plan_ready`, inspect the plan and record `specromancy approve minimal-greeting plan --by YOUR_IDENTITY`, then continue `/pipeline`.

## Permissions, resume, and cleanup

Project or user Claude settings may tighten tool access. Specromancy does not generate `settings.json`, choose a model, or claim that every surface technically enforces read-only review. Resume with `/pipeline Continue run minimal-greeting.` after checking durable status.

`specromancy adapters clean --harness claude` removes only unmodified manifest-owned copies; modified files and backups are retained. It never removes canonical skills, source, or runs.

## Known limitations and troubleshooting

- No minimum Claude Code version is asserted.
- Missing command: confirm `.claude/skills/<name>/SKILL.md` and restart discovery.
- Broken reference or drift: regenerate the whole adapter rather than copying one file.
- Collision: reconcile the file; use `--force` only for intentional backed-up replacement.
- Run `specromancy doctor` and [the general checklist](../troubleshooting.md).
