# CLI reference

Run `bin/specromancy` from a checkout or `python -m specromancy` from the
repository root. Python 3.11 or newer is required; the runtime has no
third-party dependencies.

Global options may appear before or after a subcommand:

```text
--root PATH       explicit repository root
--pipeline PATH   alternate pipeline configuration
--json            emit exactly one JSON object
--quiet           suppress successful human-readable output
```

`--root` is required when no `.git` directory or worktree marker can be
discovered. The default pipeline is `specromancy/pipeline.toml`.

## Workflow commands

```bash
bin/specromancy init "describe the requested change"
bin/specromancy status RUN_ID
bin/specromancy resume RUN_ID
bin/specromancy phase RUN_ID PHASE
bin/specromancy validate RUN_ID PHASE
```

- `init DESCRIPTION` creates a run, immutable request artifact, and pending
  first visit. `--description-file PATH` reads the request from UTF-8 input.
- `status RUN_ID` is read-only. It reports current persisted state, warnings,
  and the next command.
- `resume RUN_ID` reconstructs the next boundary from disk. It does not depend
  on the process or conversation that created the run.
- `phase RUN_ID PHASE` starts or resumes only the recorded current phase and
  emits its action packet. Each configured phase also has a dynamic alias, such
  as `bin/specromancy research RUN_ID` in the default pipeline.
- `validate RUN_ID [PHASE] [--outcome OUTCOME]` validates the output, configured
  commands, and repository mutation policy before recording a transition.
  `--outcome` is required when more than one non-blocking outcome is possible.
- `run RUN_ID` performs deterministic CLI work until the next agent, approval,
  block, failure, or terminal boundary. It never launches a harness.

## Approval and stop commands

```bash
bin/specromancy request-approval RUN_ID --reason REASON --details TEXT
bin/specromancy approve RUN_ID PHASE
bin/specromancy block RUN_ID --reason REASON --details TEXT
```

Only reasons declared by the current phase are accepted. `--reason` may be
omitted when exactly one relevant reason is configured. An approval request
validates the current artifact and binds its hash, pipeline hash, visit, and
selected outcome. `approve` rechecks those bindings before transition. `block`
records a declared stop condition; loop-limit blocks are created mechanically.

For a phase configured with `approval_required = true`, the ordinary
`validate` command automatically creates a pending approval with reason
`human-review` after all validation succeeds. It exits with code 7 and does not
apply the transition. A human reviews the artifact and repository diff, then
runs `approve RUN_ID PHASE`. If review changes the artifact, the old request is
marked stale and `request-approval RUN_ID` creates a new mandatory review
request after the updated output passes validation.

## Adapter commands

```bash
bin/specromancy adapters generate
bin/specromancy adapters generate --check
```

Generation updates only manifest-owned adapter paths. `--check` writes nothing
and reports missing, modified, extra, or source-stale generated files.

## JSON and exit codes

With `--json`, responses have stable `schema_version`, `kind`, `code`, and
`message` fields. Actionable responses include `action`; approval responses
include `approval` and `status`; terminal and read-only responses include
`status`. Expected errors include `details.error_code` where a stable diagnostic
is available.

| Code | Meaning |
| ---: | --- |
| 0 | success |
| 2 | CLI usage error |
| 3 | invalid or changed pipeline |
| 4 | run or artifact not found |
| 5 | illegal transition |
| 6 | artifact, command, or mutation validation failed |
| 7 | approval required |
| 8 | agent action required |
| 9 | run blocked |
| 10 | run lock held |
| 11 | generated adapter drift |
| 12 | internal or corrupt-state error |

Exit codes 7–10 are expected workflow boundaries, not generic crashes. Full
public contracts are recorded in [contracts.md](contracts.md).
