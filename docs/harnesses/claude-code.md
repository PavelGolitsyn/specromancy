# Claude Code

## Setup and discovery

Generate the Claude Code compatibility files:

```bash
specromancy adapters generate --harness claude
specromancy adapters check --harness claude
```

The command creates `CLAUDE.md` from canonical `AGENTS.md` and copies each complete canonical skill directory to `.claude/skills/`. Copies use ordinary files, preserve relative references and executable metadata, normalize text line endings to LF, and carry generated provenance. Claude Code loads project instructions from `CLAUDE.md` and exposes `.claude/skills/<name>/SKILL.md` as slash-invocable skills; see <https://code.claude.com/docs/en/claude-directory>.

Discovery rules were reviewed on 2026-09-22; no minimum Claude Code version is asserted by the adapter manifest.

## Invocation

```text
/pipeline Continue run RUN_ID.
/research Research run RUN_ID.
/plan Plan run RUN_ID.
/implement Implement run RUN_ID.
/review Review run RUN_ID.
```

Resume a later session with `/pipeline Continue run RUN_ID.` The generated skills remain launch surfaces; `.agents/skills` and the CLI remain authoritative.

## Permissions and limitations

Project or user Claude settings may tighten tool access. Specromancy does not generate `settings.json`, choose a model, or imply that review is technically read-only on every surface. A generated skill can be stale when its canonical source changes; run `adapters check` in development verification.

## Troubleshooting

- Missing command: confirm `.claude/skills/<name>/SKILL.md` exists and start a fresh session.
- Broken relative reference: regenerate the entire Claude adapter rather than copying only `SKILL.md`.
- Modified generated file: restore or move the edit. Use `--force` only when you want Specromancy to preserve the old file under `specromancy/adapters/backups/<sha256>/` and replace it.
- Drift after changing a canonical skill: run `specromancy adapters generate --harness claude`.
