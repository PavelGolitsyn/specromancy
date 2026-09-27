# Workflow customization

This directory is the primary customization surface for Specromancy. Changes
here alter the agentic workflow; files under `specromancy/` implement the
generic engine and should not need editing when the workflow changes.

## Editable workflow sources

| What to customize | Canonical path |
| --- | --- |
| Phase graph, gates, policies, and validation | `workflow/pipeline.toml` |
| Artifact structure and required sections | `workflow/templates/` |
| Phase procedures | `.agents/skills/<skill>/SKILL.md` |
| Repository-wide agent constraints | `AGENTS.md` |

`AGENTS.md` and `.agents/skills/` remain at their conventional repository paths
so supported agent harnesses can discover them directly. Together with this
directory, they are the complete editable workflow surface.

Do not edit `.claude/`, `.github/copilot-instructions.md`,
`.github/prompts/`, or `.opencode/commands/` directly. They are generated
adapters recorded in `adapters/manifest.json`.

## Safe customization sequence

1. Edit the graph in `workflow/pipeline.toml`.
2. Add or update its referenced templates in `workflow/templates/`.
3. Add or update the matching phase procedure in `.agents/skills/`.
4. Run `bin/specromancy adapters generate`.
5. Run `bin/specromancy adapters generate --check`.
6. Run `python -m unittest discover`.

Pipeline-relative paths such as `templates/research.md` resolve from this
directory. See `docs/poc-v3/authoring-pipelines.md` for the configuration
contract and replacement workflow example.
