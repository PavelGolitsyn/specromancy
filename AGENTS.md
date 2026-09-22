# Repository agent guidance

- The harness-neutral pipeline POC is documented in `POC_v2/README.md`.
- When a user explicitly asks to run or resume that pipeline, read and follow
  `POC_v2/skills/pipeline-orchestrator/SKILL.md` completely.
- Do not start a pipeline for ordinary repository work unless the user asks for
  it.
- Treat `POC_v2/pipeline.toml` and the referenced stage `SKILL.md` files as the
  workflow source of truth. Never hand-edit generated run state.
