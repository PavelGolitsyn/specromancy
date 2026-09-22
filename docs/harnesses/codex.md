# Codex

## Setup and discovery

Codex consumes the repository's canonical `AGENTS.md` and `.agents/skills/<name>/SKILL.md` files directly, so `specromancy adapters generate --harness codex` creates no harness-specific workflow copy. The adapter check still verifies that all five canonical skills exist.

Official Codex documentation describes repository skill discovery from `.agents/skills` and explicit `$skill-name` invocation: <https://learn.chatgpt.com/docs/build-skills>. Discovery rules were reviewed on 2026-09-22; no minimum Codex version is asserted by the adapter manifest.

## Invocation

From the repository root, invoke the complete workflow or an individual phase:

```text
$pipeline Continue run RUN_ID.
$research Research run RUN_ID.
$plan Plan run RUN_ID.
$implement Implement run RUN_ID.
$review Review run RUN_ID.
```

The skill reads durable state from `.specromancy/runs/RUN_ID/` and uses the CLI for transitions. Resume a later session with `$pipeline Continue run RUN_ID.`

## Permissions and limitations

Codex permissions come from the user's Codex configuration and execution environment. They can require extra approvals but do not replace Specromancy's phase gates. This adapter selects no model, reasoning level, provider, or paid service.

No live Codex process is started by the automated adapter suite. Use the smoke test below after meaningful discovery changes.

## Smoke test and troubleshooting

1. Run `specromancy adapters check --harness codex`.
2. Start a fresh Codex session at the repository root.
3. Confirm `$pipeline`, `$research`, `$plan`, `$implement`, and `$review` appear in skill selection.
4. Invoke each skill with a disposable run and confirm it reads its matching `.agents/skills` source.

If a skill is missing, verify its directory and `SKILL.md` name, its `name` and `description` frontmatter, and the current working directory. Restart Codex if a newly changed skill is not shown.
