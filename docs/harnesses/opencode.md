# OpenCode

Tested documentation target: Specromancy 0.1.0 on 2026-09-23. Deterministic command-adapter generation/checks were run; no provider-backed OpenCode session is claimed by the automated suite.

## Discovery and trust

The adapter creates thin launchers under `.opencode/commands/`. Each launcher points back to one canonical `.agents/skills/<name>/SKILL.md`; it does not duplicate workflow policy. Review repository instructions and skills before tool use.

```bash
specromancy adapters generate --harness opencode
specromancy adapters check --harness opencode
specromancy init --id minimal-greeting --request examples/minimal/request.md
```

## Shared minimal example and invocation

Invoke `/pipeline Continue run minimal-greeting.` Individual commands are `/research Research run minimal-greeting.`, `/plan Plan run minimal-greeting.`, `/implement Implement run minimal-greeting.`, and `/review Review run minimal-greeting.`

At `plan_ready`, inspect and record `specromancy approve minimal-greeting plan --by YOUR_IDENTITY`, then continue `/pipeline`.

## Permissions, resume, and cleanup

OpenCode configuration controls tools and models. The launchers grant no extra permission and do not prove technical reviewer isolation. Resume with `/pipeline Continue run minimal-greeting.` after checking durable status.

`specromancy adapters clean --harness opencode` removes only unmodified manifest-owned launchers. Modified launchers, backups, source, canonical skills, and runs remain.

## Known limitations and troubleshooting

- No minimum OpenCode version is asserted.
- Missing command: verify `.opencode/commands/<name>.md`, refresh discovery, and check adapter drift.
- Stale command text: regenerate from the canonical skill; do not hand-maintain a launcher.
- Permission failure: adjust the OpenCode environment or resume elsewhere without changing run state by hand.
- Run `specromancy doctor` and [the general checklist](../troubleshooting.md).
