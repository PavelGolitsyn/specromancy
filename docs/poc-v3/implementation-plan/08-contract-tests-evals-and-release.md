# Stage 08 — Contract tests, evals, documentation, and POC release

## Outcome

Demonstrate that the POC is generic, recoverable, safe, and usable from multiple harnesses, then document the supported contract and known limitations.

## Files introduced or completed

```text
tests/contract/test_default_pipeline.py
tests/contract/test_replacement_pipeline.py
tests/contract/test_interruptions.py
tests/contract/test_adapter_drift.py
tests/evals/README.md
tests/evals/cases/*.json
docs/poc-v3/architecture.md
docs/poc-v3/cli.md
docs/poc-v3/authoring-pipelines.md
docs/poc-v3/harnesses.md
README.md
```

## Work items

### 1. Build end-to-end contract fixtures

Drive the real CLI in temporary Git repositories. Avoid mocking filesystem, Git, hashing, locking, or subprocess boundaries in contract tests.

Required scenarios:

1. Default pipeline completes normally.
2. Plan approval pauses and resumes the run.
3. Review requests changes and the repair loop returns to implementation.
4. Repair loop exceeds its limit and blocks.
5. Read-only phase changes a clean tracked file.
6. Read-only phase changes a file that was dirty before phase start.
7. Implementation records allowed repository changes.
8. Artifact is edited after approval and approval becomes stale.
9. Process stops between visits and a new process resumes.
10. Pipeline configuration changes during a run and drift is rejected.
11. Replacement pipeline with unrelated phase names completes.
12. Generated adapter drift fails the check.

### 2. Add fault-injection tests

Inject failures at controlled run-store boundaries:

- before temporary manifest write;
- after temporary write but before replace;
- after replace but before event append;
- while command output is being captured;
- while a run lock is held.

Assert that the next `status` or `resume` is deterministic and never silently loses a completed transition.

### 3. Add behavior eval cases

Evals describe expected artifacts and transitions, not exact model wording. Include:

- underspecified request → approval or block for missing information;
- security-sensitive/destructive request → approval required;
- deterministic tests fail → implementation does not complete;
- impossible request → stopped or blocked artifact, not fabricated success;
- conflicting skill and repository instruction → always-on repository invariant wins;
- material deviation from approved plan → approval/planning gate;
- excessive review repairs → mechanical block.

Each eval case declares initial repository state, request, expected phase sequence, expected terminal/gate status, and required artifact properties. Actual harness-driven eval automation may remain manual in the POC, but fixture validation must be executable.

### 4. Add static architecture checks

Tests should scan source code and canonical content for:

- example phase names in generic engine modules;
- vendor-only fields in canonical skill frontmatter;
- adapter-owned workflow rules missing from canonical sources;
- absolute paths in generated files;
- direct instructions to edit `run.json`;
- shell-string execution in validation commands;
- unbounded cycles in shipped fixtures.

Avoid brittle exact-prose assertions.

### 5. Document the architecture

`docs/poc-v3/architecture.md` should explain:

- responsibility split;
- state and visit model;
- action packet boundary;
- artifact/provenance layout;
- transition and approval flow;
- why the CLI does not launch harnesses;
- canonical versus generated content.

Use one small state diagram and one filesystem example.

### 6. Document pipeline authoring

Provide recipes for:

- adding a phase;
- deleting or reordering phases;
- adding a branch;
- adding a bounded loop;
- changing a skill or template;
- declaring approval and stop codes;
- using read-only, writable, and allowlist mutation policies;
- regenerating adapters;
- handling a pipeline hash change for an active run.

Include the replacement pipeline as the primary proof, not only the default example.

### 7. Document harness usage

For Codex, Claude Code, Copilot, OpenCode, and Hermes, document:

- discovered instruction and skill paths;
- invocation examples;
- generated files, if any;
- trust or permission prerequisites;
- known surface-specific limitations;
- the fact that the CLI and artifacts remain authoritative.

Do not promise identical slash-command behavior when a harness does not provide it; document the nearest thin adapter honestly.

### 8. Update the root README

Keep the root quickstart short:

```bash
bin/specromancy init "describe the requested change"
bin/specromancy status RUN_ID
bin/specromancy resume RUN_ID
python -m unittest discover
bin/specromancy adapters generate --check
```

Link to architecture, CLI, authoring, harness, and implementation-plan documentation.

### 9. Run the release checklist

- Fresh-clone test on a supported Python version.
- No third-party runtime imports.
- Full unit and contract suite passes.
- Adapter check passes with a clean worktree.
- Default and replacement pipeline demonstrations pass.
- Generated files contain no local paths or timestamps.
- `.specromancy/` runtime data is ignored.
- License headers and skill license metadata are consistent.
- Known limitations are documented.

## Exit criteria

- All POC completion criteria in the implementation-plan index pass.
- Tests prove behavior rather than model prose.
- Documentation lets a contributor replace the example pipeline without reading engine code.
- The worktree is clean after tests and adapter drift checks.
- Remaining work is explicitly categorized as post-POC rather than hidden in incomplete stages.

## Post-POC candidates

Do not pull these into POC completion unless a contract defect requires them:

- packaged wheel or standalone binaries;
- YAML configuration loader;
- signed approvals or authenticated actors;
- remote artifact stores;
- richer schema validators;
- harness launch plugins;
- parallel branches and join nodes;
- migration of active runs between pipeline versions;
- structured telemetry and long-running daemon support.

