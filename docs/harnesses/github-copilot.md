# GitHub Copilot

Tested documentation target: Specromancy 0.1.0 on 2026-09-23. Deterministic adapter checks were run; prompt-file availability and provider-backed execution vary by Copilot surface and are not claimed as release passes.

## Discovery and trust

The adapter mirrors `AGENTS.md` into `.github/copilot-instructions.md` and creates thin `.github/prompts/*.prompt.md` launchers. It does not copy canonical skills to `.github/skills`; `.agents/skills/` remains authoritative. Review instructions and skills before granting tools.

```bash
specromancy adapters generate --harness copilot
specromancy adapters check --harness copilot
specromancy init --id minimal-greeting --request examples/minimal/request.md
```

## Shared minimal example and invocation

Where prompt files are supported, select `pipeline` and provide `Continue run minimal-greeting.` Select `research`, `plan`, `implement`, or `review` for an individual phase and name the same run. On a surface without prompt files, explicitly ask it to load `.agents/skills/pipeline/SKILL.md` and continue that run.

At `plan_ready`, use `specromancy approve minimal-greeting plan --by YOUR_IDENTITY`, then invoke the pipeline again.

## Surface differences, resume, and cleanup

IDE chat, Copilot CLI, coding agent, and code review discover different customization files. Prompt visibility on one surface does not imply another can use it. Native permissions may tighten access; generated prompts do not grant write access or enforce review isolation.

Resume by selecting the pipeline prompt and naming `minimal-greeting`. `specromancy adapters clean --harness copilot` safely removes unmodified generated instructions/prompts only; it preserves user changes, backups, source, and runs.

## Known limitations and troubleshooting

- Prompt files may be preview-only in a client; no minimum version is asserted.
- Missing prompt: refresh the workspace customization index and confirm `.github/prompts/` support.
- Conflicting guidance: review both instruction files and regenerate after resolving user-owned content.
- If review attempts edits, stop it and reinvoke the canonical review skill under suitable permissions.
- Run `specromancy doctor` and [the general checklist](../troubleshooting.md).
