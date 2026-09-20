# Stage 7: Harness Adapters

## Objective

Expose the canonical instructions, skills, and phase commands through Codex, Claude Code, GitHub Copilot, Hermes, and OpenCode without duplicating business logic or requiring symlinks.

## Dependencies

- Canonical skills from Stages 2 through 6.
- Stable CLI from Stage 6.

## Deliverables

- `src/specromancy/adapters/base.py`
- `src/specromancy/adapters/claude.py`
- `src/specromancy/adapters/copilot.py`
- `src/specromancy/adapters/opencode.py`
- `src/specromancy/adapters/codex.py`
- `src/specromancy/adapters/hermes.py`
- `specromancy/adapters/manifest.json`
- Generated `CLAUDE.md`
- Generated `.claude/skills/`
- Generated `.github/copilot-instructions.md`
- Generated `.github/prompts/`
- Generated `.opencode/commands/`
- `docs/harnesses/*.md`
- `tests/adapters/`

## Adapter principles

1. Canonical workflow logic remains in `.agents/skills` and the CLI.
2. Generated files contain a visible generated-file header where their format permits it.
3. Generation is deterministic across operating systems.
4. No adapter selects a model, reasoning level, provider, or paid service.
5. Native permissions may tighten capabilities but must not alter phase semantics.
6. Adapters use ordinary files instead of Git symlinks for Windows compatibility.
7. Generated copies are committed for zero-setup use and verified against their canonical sources.

## Harness mapping

### Codex

Native canonical support:

- `AGENTS.md`
- `.agents/skills/<name>/SKILL.md`

Tasks:

- Validate that all canonical skills are discoverable.
- Document `$pipeline`, `$research`, `$plan`, `$implement`, and `$review` invocations.
- Do not create Codex-only workflow files unless a later requirement proves necessary.
- Add a smoke-test checklist using explicit skill invocation.

### Claude Code

Generated adapter:

- `CLAUDE.md` imports or faithfully mirrors the canonical `AGENTS.md` content with generation metadata.
- `.claude/skills/<name>/` is a generated copy of each canonical skill directory.

Tasks:

- Preserve relative references and assets while copying skill directories.
- Strip or translate only fields proven incompatible; otherwise keep standard Agent Skills frontmatter byte-equivalent.
- Verify `/pipeline`, `/research`, `/plan`, `/implement`, and `/review` appear.
- Optionally configure read-only reviewer permissions in a documented, generated project setting only if this can be done without surprising the user.

### GitHub Copilot

Generated adapter:

- `.github/copilot-instructions.md` mirrors the applicable canonical instructions.
- `.github/prompts/<phase>.prompt.md` provides manual prompt entry points that direct Copilot to the canonical skill and CLI contract.

Copilot already supports `.agents/skills`, so do not copy the skills into `.github/skills`.

Tasks:

- Keep prompt files as launchers, not duplicate procedures.
- Document differences among IDE chat, CLI, cloud agent, and code review surfaces.
- Ensure review prompts do not imply that all surfaces enforce read-only access.

### OpenCode

Native canonical support:

- `AGENTS.md`
- `.agents/skills/<name>/SKILL.md`

Generated adapter:

- `.opencode/commands/<phase>.md` for convenient slash-command entry points.

Tasks:

- Each command template instructs the agent to load the named canonical skill and operate on a run ID supplied through arguments.
- Avoid pinning a model or redefining agents in the POC.
- Verify skill permissions are not accidentally denied by generated config.

### Hermes

Native canonical support:

- `AGENTS.md`
- `.agents/skills/<name>/SKILL.md`

Tasks:

- Document the one-time `hermes skills trust` action for a cloned repository.
- Verify each project skill appears as an invocation after trust.
- Do not enable inline shell execution or write user-global Hermes configuration.
- Explain that noninteractive Hermes surfaces inherit the user's trust decision.

## Adapter manifest

Record every generated path with:

- adapter name and version;
- canonical source path or paths;
- transformation type;
- expected content digest;
- whether the generated output is committed;
- minimum known harness version when established.

The manifest allows `specromancy adapters check` to report missing, modified, stale, or unexpected generated files.

## CLI behavior

```text
specromancy adapters generate [--harness NAME]
specromancy adapters check [--harness NAME]
specromancy adapters clean [--harness NAME]
specromancy adapters list
```

`clean` removes only paths declared in the adapter manifest and only when their current digest matches generated content. It must never recursively delete an unresolved or user-controlled directory.

## Implementation tasks

1. Define an adapter protocol and generated-file record.
2. Implement deterministic directory copying and text rendering.
3. Implement each harness adapter independently.
4. Generate invocation wrappers for all five canonical skills where useful.
5. Create the adapter manifest and drift checker.
6. Detect collisions with user-authored files and refuse overwrite unless `--force` is explicitly provided.
7. Back up or preserve provenance for forced replacement according to a documented policy.
8. Add per-harness setup, invocation, limitation, and troubleshooting documentation.
9. Add adapter generation to the development verification command.
10. Test generated adapters from a built package, not only the source tree.

## Tests

- Deterministic output on repeated generation.
- CRLF/LF normalization behavior.
- Preservation of nested skill assets and executable-bit metadata where relevant.
- User-authored destination collision.
- Detection of hand-edited generated file.
- Safe clean with matching and mismatched digests.
- Claude relative-reference integrity.
- Copilot prompt wrappers contain no duplicated procedure.
- OpenCode command argument forwarding text.
- Codex and Hermes correctly report that no generated skill copy is needed.

Where CI access to a harness is unavailable, validate file discovery rules structurally and maintain a documented manual smoke test.

## Exit criteria

- `adapters generate` followed by `adapters check` succeeds on a clean checkout.
- Editing a canonical skill makes relevant generated adapters stale.
- No adapter contains unique pipeline rules.
- All five harness guides describe a successful invocation and known limitations.
- Claude Code can discover generated skill copies without symlink support.
- User-authored harness configuration is never silently overwritten.

## Risks and mitigations

- **Harness formats change:** version adapters independently and isolate transformations.
- **Generated duplication drifts:** commit a manifest and enforce `adapters check` in CI.
- **Copilot surface inconsistency:** document supported surfaces and keep `.github/copilot-instructions.md` as a compatibility layer.
- **User configuration damage:** detect ownership and require explicit force for collisions.

