# GitHub Copilot

## Setup and discovery

```bash
specromancy adapters generate --harness copilot
specromancy adapters check --harness copilot
```

The adapter mirrors canonical repository guidance into `.github/copilot-instructions.md` and creates thin manual launchers under `.github/prompts/*.prompt.md`. It deliberately does not copy skills to `.github/skills`; `.agents/skills` remains canonical. GitHub documents repository-wide instructions and prompt-file support at <https://docs.github.com/en/copilot/reference/customization-cheat-sheet>.

Discovery rules were reviewed on 2026-09-22; Copilot prompt files remain a preview feature and no minimum version is asserted.

## Invocation

In an IDE surface that supports prompt files, select `pipeline`, `research`, `plan`, `implement`, or `review`, then provide `RUN_ID` in chat. On another Copilot surface, ask it directly to load the matching `.agents/skills/<name>/SKILL.md` and operate on `RUN_ID`.

Resume by invoking the `pipeline` prompt and naming the existing run ID.

## Surface and permission differences

- IDE chat: prompt files are manual entry points where supported.
- Copilot CLI: reads repository instructions including `AGENTS.md` and `.github/copilot-instructions.md`, but IDE prompt-file affordances do not imply CLI availability.
- Coding agent/cloud agent: repository instructions and skills depend on the enabled product surface and repository configuration.
- Code review: instruction support differs from agent execution; the review launcher does not claim filesystem enforcement.

Native permissions may tighten access, but the adapter does not grant write access, choose a model, or weaken phase semantics.

## Troubleshooting

- Prompt missing: confirm the client supports `.github/prompts/*.prompt.md` and refresh its workspace customization index.
- Conflicting guidance: compare `AGENTS.md` and `.github/copilot-instructions.md`; regenerate the mirror and remove user-authored conflicting instructions.
- Review tries to edit: stop the run and use a surface or permission profile that enforces the desired isolation; the prompt alone is not a sandbox.
