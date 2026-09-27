# Harness compatibility

Specromancy keeps workflow ownership in `AGENTS.md`, `specromancy/pipeline.toml`, and `.agents/skills/*/SKILL.md`. Harness adapters are generated discovery and invocation aids; they do not define phases, transitions, validation, or approval rules.

Generate adapters after changing any canonical source:

```text
bin/specromancy adapters generate
```

CI and local verification can detect missing, modified, extra, or source-stale adapter output without writing files:

```text
bin/specromancy adapters generate --check
```

The ownership record is `adapters/manifest.json`. Generation uses normalized UTF-8 input, stable ordering and newlines, no timestamps or absolute paths, and atomic per-file replacement. A file may be removed as stale only when the previous manifest owns it and its current hash still matches. Unowned and modified stale files are preserved and reported as conflicts.

## Harness matrix

| Harness | Discovery | Invocation | Adapter mode |
| --- | --- | --- | --- |
| Codex | Reads `AGENTS.md` and `.agents/skills` directly | Use `$pipeline` for a new or resumed run, or invoke the canonical phase skill named by an action packet | Native; no generated files |
| Claude Code | Reads `.claude/CLAUDE.md`, `.claude/skills`, and `.claude/commands/specromancy` | Use the generated init, resume, status, or phase command | Generated mirrors and thin commands |
| GitHub Copilot | Reads `.github/copilot-instructions.md`, repository `.agents/skills`, and `.github/prompts` | Run a generated `specromancy-*` prompt | Generated instructions and thin prompts |
| OpenCode | Reads `AGENTS.md`, `.agents/skills`, and `.opencode/commands` | Run a generated `specromancy-*` command | Generated thin commands |
| Hermes | Reads `AGENTS.md` and project `.agents/skills` after trust is granted | Invoke the canonical pipeline or current phase skill | Native; no generated files |

## Persisted-state workflow

Initialize a run with `bin/specromancy init DESCRIPTION --json` and retain its returned run ID. For an existing run, use `bin/specromancy status RUN_ID --json` or `bin/specromancy resume RUN_ID --json`. When the CLI emits an action packet, load the exact `skill.absolute_path` it records, honor its mutation policy, and execute its recorded final validation command. Conversation history is never run state.

## Hermes repository trust

Hermes requires project skills to be trusted before it will load them. From the repository, run:

```text
hermes skills trust
```

Review and accept the repository skills when prompted. Specromancy does not modify user-level Hermes configuration.

## Generated-file policy

Do not edit generated files. Change `AGENTS.md`, the validated pipeline configuration, canonical `.agents/skills` content, or CLI command/help metadata, then regenerate. Codex and Hermes remain listed in generator metadata even though they need no generated adapter files; this makes their compatibility expectation testable and visible in the manifest.
