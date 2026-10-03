# Canonical engine artifacts

This folder holds the editable templates for engine instructions and skills.
These artifacts describe the generic runtime and orchestration contract;
workflow phase procedures belong in `workflow/skills/` beside the pipeline's
artifact templates.

| Source template | Generated outputs |
| --- | --- |
| `specromancy/artifacts/AGENTS.md` | `AGENTS.md`, `.claude/CLAUDE.md`, `.github/copilot-instructions.md` |
| `specromancy/artifacts/skills/<skill>/SKILL.md` | `.agents/skills/<skill>/SKILL.md`, `.claude/skills/<skill>/SKILL.md` |

The `pipeline` skill coordinates the CLI's persisted next actions without
assuming any workflow phase names. Engine skill names are reserved: a workflow
skill with the same name is a generation error, preventing either source from
silently overriding the other.

Edit these templates, then run:

```sh
bin/specromancy adapters generate
bin/specromancy adapters generate --check
python -m unittest discover
```

All generated outputs have provenance comments and are owned by
`adapters/manifest.json`. The generator reads the templates directly; generated
instructions and skills are never source inputs. An existing unowned
`AGENTS.md` is preserved and reported as a conflict. When adopting this layout,
move its content into `specromancy/artifacts/AGENTS.md` before generating.
