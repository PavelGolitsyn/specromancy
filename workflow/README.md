# Workflow customization

This directory is the primary customization surface for Specromancy. Change
the workflow here without editing the generic Python engine in `specromancy/`.

| What to customize | Authoritative location |
| --- | --- |
| Phase graph, order, transitions, policies, gates, and validators | `workflow/pipeline.toml` |
| Artifact structure and required sections | `workflow/templates/*.md` |
| Instructions executed for each phase | `.agents/skills/<skill>/SKILL.md` |
| Repository-wide constraints for every agent | `AGENTS.md` |

The skills and `AGENTS.md` remain at their standard harness discovery paths,
but they are workflow inputs, not engine implementation. Files under
`.claude/`, `.github/prompts/`, and `.opencode/` are generated adapters; do not
edit them directly.

When adding or changing a phase:

1. Edit `workflow/pipeline.toml`.
2. Add or update its template under `workflow/templates/`.
3. Add or update its canonical procedure under `.agents/skills/`.
4. Regenerate adapters and verify the repository:

   ```bash
   bin/specromancy adapters generate
   bin/specromancy adapters generate --check
   python -m unittest discover
   ```

Pipeline changes alter the pipeline hash, so an active run cannot continue
against the edited definition. Finish it first, restore its exact definition,
or start a new run.
