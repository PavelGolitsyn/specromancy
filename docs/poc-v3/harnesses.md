# Harness usage

The CLI and persisted artifacts are authoritative for every harness. Adapters
help a harness discover instructions and invoke the CLI; they do not own phase
order, validation, approval, or run state. Always use the returned run ID and
load the exact skill path in the current action packet.

Generate or verify adapters with:

```bash
bin/specromancy adapters generate
bin/specromancy adapters generate --check
```

## Codex

- Discovery: `AGENTS.md` and `.agents/skills/*/SKILL.md` are native project
  instructions and skills.
- Invocation: ask Codex to use the `pipeline` skill with a request, or provide
  `RUN_ID` to the phase skill named by `status`.
- Generated files: none.
- Prerequisites: open the repository as a trusted writable workspace and allow
  only the commands needed by the configured validation.
- Limitation: availability and presentation of skill invocation depend on the
  Codex client; Specromancy does not start or control a Codex task.

## Claude Code

- Discovery: generated `.claude/CLAUDE.md`, `.claude/skills/`, and
  `.claude/commands/specromancy/`.
- Invocation: `/specromancy:init DESCRIPTION`,
  `/specromancy:status RUN_ID`, `/specromancy:resume RUN_ID`, or
  `/specromancy:phase RUN_ID PHASE`.
- Generated files: the Claude instruction mirror, portable skill mirrors, and
  four thin commands listed in `adapters/manifest.json`.
- Prerequisites: trust the repository and approve shell/filesystem access
  required by the phase and validation commands.
- Limitation: command wrappers only invoke the CLI and hand off to canonical
  skills; they do not provide a persistent orchestration service.

## GitHub Copilot

- Discovery: generated `.github/copilot-instructions.md`, repository
  `.agents/skills/`, and `.github/prompts/specromancy-*.prompt.md`.
- Invocation: select a `specromancy-init`, `-status`, `-resume`, or `-phase`
  prompt and supply its argument hint.
- Generated files: one instruction mirror and four prompt files.
- Prerequisites: use an agent-capable surface with repository and terminal
  permissions.
- Limitation: Copilot prompt availability varies by editor. The prompts are the
  nearest thin adapter and are not guaranteed to behave like slash commands in
  every host.

## OpenCode

- Discovery: `AGENTS.md`, `.agents/skills/`, and generated
  `.opencode/commands/specromancy-*.md`.
- Invocation: use the matching `specromancy-init`, `-status`, `-resume`, or
  `-phase` custom command with its positional arguments.
- Generated files: four thin command files.
- Prerequisites: trust the project and grant terminal/filesystem access needed
  by the current action packet.
- Limitation: the generated command convention is OpenCode-specific and does
  not promise parity with Claude Code slash-command parsing.

## Hermes

- Discovery: `AGENTS.md` and `.agents/skills/*/SKILL.md` directly.
- Invocation: invoke the canonical `pipeline` skill for a new run, or the
  current phase skill with `RUN_ID` after `status`.
- Generated files: none.
- Prerequisites: run `hermes skills trust` in the repository and review the
  project skills before accepting them.
- Limitation: project-skill trust is user-managed. Specromancy does not modify
  user-level Hermes configuration or expose generated slash commands.

## Recovery across harnesses

Any harness may stop after any visit. A later process—or a different supported
harness—can run `bin/specromancy status RUN_ID --json` and continue from the
recorded next command. Conversation transcripts, harness task identifiers, and
adapter-local state are never required for recovery.

See [harness-compatibility.md](harness-compatibility.md) for the compact matrix
and generated-file ownership policy.
