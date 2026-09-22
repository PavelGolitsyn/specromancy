# Stage 07 — Generated harness adapters

## Outcome

Expose canonical instructions, skills, and CLI actions through each supported harness's native discovery and invocation conventions without duplicating workflow ownership.

## Files introduced or generated

```text
specromancy/adapters.py
adapters/generate.py
adapters/manifest.json
.claude/CLAUDE.md
.claude/skills/*/SKILL.md
.claude/commands/specromancy/*.md
.github/copilot-instructions.md
.github/prompts/specromancy-*.prompt.md
.opencode/commands/specromancy-*.md
tests/unit/test_adapters.py
tests/contract/test_adapter_drift.py
```

Codex and Hermes may require no generated command files in the POC because both can consume canonical repository instructions and skills. Their adapter definitions still exist in generator metadata so compatibility expectations are tested and documented.

## Work items

### 1. Define adapter inputs

The generator reads only canonical sources:

- `AGENTS.md`;
- validated pipeline configuration;
- `.agents/skills/*/SKILL.md`;
- CLI command names and help metadata.

It must not read previously generated files as source content.

### 2. Define adapter ownership manifest

`adapters/manifest.json` records:

- generator schema version;
- canonical source hash;
- generator version;
- every generated path and content hash;
- target harness;
- generation timestamp only if reproducibility is not affected; preferably omit it.

Every generated text file starts with a comment stating that it is generated, its canonical source, and the regeneration command.

### 3. Generate Claude compatibility files

Generate:

- a small `CLAUDE.md` that imports or faithfully reflects canonical `AGENTS.md` without adding workflow rules;
- `.claude/skills/<name>/SKILL.md` wrappers or deterministic mirrors for canonical skills;
- command wrappers that accept a run ID, invoke the stable CLI, and direct Claude to the current canonical skill/action packet.

Choose wrappers when Claude's import behavior is reliable for the referenced location; otherwise generate full mirrors and enforce their hashes. Canonical `.agents/skills` files remain the only editable sources.

### 4. Generate Copilot files

Generate `.github/copilot-instructions.md` from the subset of `AGENTS.md` relevant to repository work and small prompt wrappers for initialize/resume/status or phase invocation.

Copilot uses `.agents/skills` directly, so do not generate a second skill tree.

### 5. Generate OpenCode commands

Generate small `.opencode/commands/` wrappers that invoke the same CLI action packets. OpenCode consumes `AGENTS.md` and `.agents/skills` directly, so no instruction or skill copy is required.

### 6. Document Hermes trust

Hermes consumes `AGENTS.md` and project `.agents/skills`, but project skills require repository trust. Add the required `hermes skills trust` step to the compatibility documentation rather than trying to change user-level Hermes configuration.

### 7. Keep Codex canonical

Codex uses `AGENTS.md` and `.agents/skills` directly. Document `$pipeline` and phase-skill invocation. Do not add a Codex-only canonical instruction file.

### 8. Implement deterministic generation

- Stable file ordering.
- Stable newline and UTF-8 encoding.
- No absolute local paths.
- No current timestamps in generated content.
- Canonical hashes derived from normalized bytes.
- Temporary-file-plus-rename updates.

`adapters generate --check` renders everything in memory, compares expected paths and bytes with the worktree, reports missing/stale/modified paths, performs no writes, and exits with adapter-drift status.

### 9. Safely remove stale output

Normal generation may remove a file only when:

- it appears in the previous ownership manifest;
- it is absent from the new generated set;
- its current hash still matches the previous generated hash.

If a user changed a stale generated file, report the conflict and leave it untouched.

## Tests

- Two generations produce byte-identical trees and manifests.
- `--check` passes after generation and fails after edits, additions, or removals.
- Generator never overwrites an unowned file.
- Stale unchanged files are removed; stale modified files are preserved with an error.
- Generated wrappers mention only existing CLI commands and canonical skills.
- Canonical source changes cause adapter drift.
- Static checks confirm generated adapters add no transition or validation logic.

## Exit criteria

- All supported harnesses have either a generated adapter or an explicit native/no-file adapter definition.
- Generated output is deterministic and safely owned.
- Editing generated files is never required to change the workflow.
- CI can detect all adapter drift with one command.

