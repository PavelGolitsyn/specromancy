# Stage 01 — Foundation and public contracts

## Outcome

Create the repository skeleton and freeze the vocabulary, command surface, filesystem ownership, and compatibility policy that all later work implements.

## Files introduced

```text
AGENTS.md
.gitignore
bin/specromancy
specromancy/__init__.py
specromancy/__main__.py
specromancy/cli.py
specromancy/errors.py
specromancy/exit_codes.py
specromancy/schemas/
specromancy/templates/
.agents/skills/
adapters/generate.py
tests/unit/
tests/contract/
tests/fixtures/
tests/evals/
```

The package directory will also contain the pipeline configuration. Keeping code and configuration under `specromancy/` is acceptable as long as the loader treats the configuration as data and tests can point it at a fixture-specific configuration.

## Work items

### 1. Define canonical terminology

Use these terms consistently in code, schemas, documentation, and output:

- **Pipeline:** a versioned directed graph of phases.
- **Phase:** a configured unit of agent work with declared inputs, output, mutation policy, validation, and transitions.
- **Visit:** one execution attempt of a phase. A phase may have multiple visits because of loops.
- **Artifact:** a file produced or consumed by a visit.
- **Outcome:** a configured result such as `validated`, `changes-requested`, or `blocked`.
- **Gate:** a mechanical condition that prevents transition, including approval.
- **Run:** one execution of a pipeline for a user request.
- **Action packet:** the fully resolved instructions that the CLI emits for the current visit.
- **Adapter:** generated harness-native instructions or command wrapper containing no canonical workflow logic.

### 2. Define filesystem ownership

The CLI may create or replace files only in:

- `.specromancy/runs/<run-id>/`;
- generated adapter paths recorded in `adapters/manifest.json`;
- explicit temporary files adjacent to a manifest during atomic replacement.

It must not delete, reset, stage, or commit repository work. Generated-file cleanup is limited to paths owned by the previous adapter manifest.

Add `.specromancy/` to `.gitignore`. Keep a placeholder only if tests require the directory to exist.

### 3. Establish the executable boundary

`bin/specromancy` is a tiny Python launcher. Business logic belongs in the package so tests can call it without spawning a subprocess. Support both:

```bash
bin/specromancy ...
python -m specromancy ...
```

Resolve the repository root by walking upward to `.git`; fall back to an explicit `--root` for fixtures and non-Git tests. Never derive the root from the current chat or harness.

### 4. Freeze the initial command contract

Reserve these commands:

```text
init DESCRIPTION
phase RUN_ID PHASE
<dynamic-phase> RUN_ID
validate RUN_ID [PHASE]
approve RUN_ID PHASE
request-approval RUN_ID
block RUN_ID
status RUN_ID
resume RUN_ID
run RUN_ID
adapters generate
```

Common options:

```text
--root PATH
--pipeline PATH
--json
--quiet
```

Dynamic phase aliases are resolved only after built-in commands, so a pipeline cannot shadow `init`, `status`, or another reserved command.

### 5. Define exit codes

Create named constants and document them:

| Code | Meaning |
| ---: | --- |
| 0 | Command completed successfully |
| 2 | CLI usage error |
| 3 | Invalid pipeline configuration |
| 4 | Run or artifact not found |
| 5 | Illegal state transition |
| 6 | Validation failed |
| 7 | Approval required |
| 8 | Agent action required |
| 9 | Run blocked or stopped |
| 10 | Concurrent run lock held |
| 11 | Adapter drift detected |
| 12 | Internal or corrupt-state error |

Human output goes to stdout for successful/actionable responses and stderr for errors. `--json` always returns one JSON object, including on expected failures.

### 6. Add repository instructions

`AGENTS.md` should be short and always applicable. It must state:

- supported Python version;
- test command;
- no third-party runtime dependencies in the POC;
- canonical versus generated file locations;
- no phase names in engine code;
- artifact and state invariants;
- definition of done for code changes.

Do not copy phase procedures into `AGENTS.md`.

## Tests

- Launcher imports the local package correctly from any subdirectory.
- `--help` lists stable commands and exit-code documentation.
- Unknown built-in command produces a usage error before a pipeline exists.
- Root discovery handles a worktree and explicit fixture root.
- JSON error output is valid JSON and contains `code`, `message`, and optional `details`.

## Exit criteria

- Directory skeleton exists.
- Public terms, command names, exit codes, and ownership rules are documented.
- The launcher and placeholder command parser run without dependencies.
- Stage tests pass with `python -m unittest discover`.

