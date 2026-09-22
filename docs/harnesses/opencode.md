# OpenCode

## Setup and discovery

OpenCode reads canonical `AGENTS.md` and `.agents/skills` directly. Generate only the convenience commands:

```bash
specromancy adapters generate --harness opencode
specromancy adapters check --harness opencode
```

The adapter creates `.opencode/commands/<phase>.md` launchers. Each launcher loads the matching canonical skill and forwards command arguments through `$ARGUMENTS`. It does not create `opencode.json`, pin a model, redefine an agent, or change skill permissions. See OpenCode's [skills](https://opencode.ai/docs/skills) and [commands](https://opencode.ai/docs/commands/) documentation.

Discovery rules were reviewed on 2026-09-22; no minimum OpenCode version is asserted by the adapter manifest.

## Invocation

```text
/pipeline RUN_ID
/research RUN_ID
/plan RUN_ID
/implement RUN_ID
/review RUN_ID
```

Resume with `/pipeline RUN_ID` from the repository workspace.

## Permissions and limitations

If the user's OpenCode configuration denies the `skill` permission, canonical skills can be hidden or rejected. Specromancy intentionally does not rewrite that configuration. Permission changes can tighten the execution environment but cannot authorize a forbidden phase transition.

## Troubleshooting

- Command missing: verify `.opencode/commands/<name>.md` and restart or refresh the OpenCode session.
- Skill missing: check the selected agent's `skill` permission and `.agents/skills/<name>/SKILL.md` frontmatter.
- Arguments ignored: pass the run ID after the slash command and inspect the generated file for the literal `$ARGUMENTS` placeholder.
- Stale launcher: regenerate after changing canonical skills.
