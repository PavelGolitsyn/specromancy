# POC v2: harness-agnostic agent pipeline

This POC separates workflow semantics from the agent harness:

```text
pipeline.toml              declarative graph and transition policy
skills/*/SKILL.md          replaceable stage behavior
pipeline.py                deterministic state, validation, and prompt assembly
commands/*.md              optional human-facing entry points
.specromancy/runs/*        runtime state and artifacts (generated, not committed)
```

The controller does not call a model API. It emits the same stage packet for
Codex, Claude Code, GitHub Copilot, Hermes, OpenCode, or any agent that can read
files and run a command. A harness owns model sessions, tools, permissions, and
approvals; this POC owns only workflow state and transitions.

## Try it

From the repository root:

```bash
python3 POC_v2/pipeline.py validate
python3 POC_v2/pipeline.py start --run demo --task "Add a health endpoint"
python3 POC_v2/pipeline.py prompt --run demo
python3 POC_v2/pipeline.py advance --run demo --outcome complete --summary "Research captured"
python3 POC_v2/pipeline.py status --run demo
```

For an agent-driven run, give the harness
[`commands/run-pipeline.md`](commands/run-pipeline.md), or ask it to use
[`skills/pipeline-orchestrator/SKILL.md`](skills/pipeline-orchestrator/SKILL.md).
The orchestrator repeatedly renders a stage packet, follows it, records an
outcome, and stops at a terminal state.

Generated run data is placed under `.specromancy/runs/<run-id>/` in the chosen
workspace. Use `--workspace PATH` when the target repository is not the current
directory, and `--config PATH` to select another pipeline.

## Change the workflow

Only two kinds of edits are needed:

1. Edit `pipeline.toml` to add, remove, rename, or reconnect states.
2. Edit or add a `skills/<name>/SKILL.md` file and point a state's `skill` field
   at it.

State names have no meaning to the controller. The sample happens to use
`research -> plan -> implement -> review`, with review either completing the
run or returning it to implementation.

Example replacement:

```toml
[states.verify]
skill = "skills/verify/SKILL.md"

[states.verify.transitions]
passed = "done"
failed = "implement"
```

Then redirect any incoming transition to `verify`. Run `validate` after an
edit; it checks skill files, transition targets, reachability, and whether all
active states can reach a terminal state.

## Design rules

- **Portable core, thin adapters.** Do not encode orchestration in Claude hooks,
  Copilot agents, Codex automations, or OpenCode configuration. Such adapters
  should only invoke the canonical command or orchestration skill.
- **Deterministic control plane.** The controller, not the model, validates and
  persists state transitions. The model chooses only an allowed outcome.
- **Skills are stage contracts.** A stage skill describes its goal, inputs,
  outputs, constraints, and outcome-selection rules. It should not hard-code
  its predecessor or successor.
- **Artifacts carry context.** Stages communicate through files in the run's
  artifact directory, avoiding assumptions about session or context retention.
- **Runtime is resumable.** `state.json` is the source of truth. Any harness can
  resume a run by ID without sharing the prior conversation.
- **Permissions stay with the harness.** A skill may request work, but it does
  not grant filesystem, shell, network, or external-service access.
- **Commands are UX, not logic.** Slash-command syntax differs by product, so
  canonical commands are ordinary Markdown prompts. Packaging can later copy
  or wrap them for each harness without changing the pipeline.

## Harness discovery

The root `AGENTS.md` is the small, always-on discovery layer for Codex, GitHub
Copilot, Hermes, and OpenCode. It points explicit pipeline requests at the
canonical orchestration skill. `CLAUDE.md` imports the same instructions for
Claude Code.

Detailed behavior remains on-demand in `SKILL.md` files. The controller embeds
the current stage skill in the rendered packet, so the active run does not rely
on harness-specific skill lookup, session persistence, or a particular slash
command implementation.

## Configuration contract

`pipeline.toml` contains:

- `initial`: first state.
- `work_dir`: workspace-relative runtime directory.
- `max_transitions`: loop guard for one run.
- `states.<name>.skill`: config-relative `SKILL.md` path for an active state.
- `states.<name>.transitions`: allowed outcome-to-next-state map.
- `states.<name>.terminal`: `completed` or `blocked` for a terminal state.

The POC deliberately avoids provider/model selection, subagent topology,
prompt templating, retries, and hooks. Those can be added later as optional
policy fields or harness adapters without changing the state/skill boundary.
