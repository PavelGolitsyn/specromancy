# Specromancy POC public contracts

These contracts are stable across the POC. Changes to them require a schema-version change and updated fixtures.

## Vocabulary

- **Pipeline:** a versioned directed graph of phases.
- **Phase:** a configured unit of agent work with declared inputs, output, mutation policy, validation, and transitions.
- **Visit:** one execution attempt of a phase. Loops may cause a phase to have multiple visits.
- **Artifact:** a file produced or consumed by a visit.
- **Outcome:** a configured result such as `validated`, `changes-requested`, or `blocked`.
- **Gate:** a mechanical condition that prevents transition, including approval.
- **Run:** one execution of a pipeline for a user request.
- **Action packet:** the fully resolved instructions emitted by the CLI for the current visit.
- **Adapter:** generated harness-native instructions or a command wrapper containing no canonical workflow logic.

## Command surface

The reserved commands are:

```text
init DESCRIPTION
phase RUN_ID PHASE
<dynamic-phase> RUN_ID
validate RUN_ID [PHASE] [--outcome OUTCOME]
approve RUN_ID PHASE
request-approval RUN_ID [--reason CODE] [--details TEXT] [--outcome OUTCOME]
block RUN_ID [--reason CODE] [--details TEXT]
status RUN_ID
resume RUN_ID
run RUN_ID
adapters generate [--check]
```

All commands accept `--root PATH`, `--pipeline PATH`, `--json`, and `--quiet`. Built-in commands are resolved before dynamic phase aliases; pipeline phase names therefore cannot shadow a reserved command.

`--reason` may be omitted only when the current phase declares exactly one
reason of the relevant kind. `validate --outcome` is required when a phase has
multiple non-blocking outcomes and is rejected when there is only one.

Both `bin/specromancy` and `python -m specromancy` invoke the same package entry point. The repository root is found by walking upward to a `.git` directory or worktree marker. `--root` supplies an explicit root for fixtures and non-Git directories.

`adapters generate` deterministically renders harness-native adapters from
`AGENTS.md`, the validated pipeline configuration, canonical `.agents/skills`,
and CLI command/help metadata. `--check` performs no writes and exits with
`ADAPTER_DRIFT` when the manifest or managed tree differs from the expected
rendering.

## Filesystem ownership

The CLI may create or replace files only in:

- `.specromancy/runs/<run-id>/`;
- generated adapter paths recorded in `adapters/manifest.json`;
- explicit temporary files adjacent to a manifest during atomic replacement.

The CLI never deletes, resets, stages, or commits repository work. Cleanup is limited to generated paths owned by the previous adapter manifest.

`adapters/manifest.json` is the schema-versioned ownership boundary. It records
the generator version and regeneration command, canonical source records and
aggregate hash, every generated adapter path and content hash, and generated or
native mode for every supported harness. The manifest omits its own hash to
avoid self-reference and contains no timestamps or absolute paths.

## Run persistence

Run IDs use a UTC timestamp and eight lowercase hexadecimal characters, for
example `20260922T142501Z-a1b2c3d4`. Only IDs matching that form may be used to
address `.specromancy/runs/`.

`run.json` is the validated current snapshot. Each mutation increments its
`revision`, atomically replaces the file, and appends an `events.jsonl` record
that contains the revision and canonical manifest hash. If interruption occurs
after replacement but before the event append, the next load appends a
`recovery` event. A malformed manifest, a malformed event, a non-contiguous
event sequence, or any other manifest/event disagreement is corrupt state and
is not repaired heuristically.

Each run uses an exclusive `.lock` file containing the owner PID and acquisition
time. Locks are never expired based on age alone. After verifying that its owner
is no longer running, a stale lock must be removed manually.

Artifact paths in manifests are normalized relative paths. Symbolic inputs are
resolved once, when a visit starts, to literal paths and SHA-256 hashes. Request
artifacts and completed visit outputs are immutable; hash drift is a corrupt
state diagnostic rather than an instruction to rewrite either the file or its
record.

## Exit codes and output

| Code | Name | Meaning |
| ---: | --- | --- |
| 0 | `SUCCESS` | Command completed successfully |
| 2 | `USAGE_ERROR` | CLI usage error |
| 3 | `INVALID_PIPELINE` | Invalid pipeline configuration |
| 4 | `NOT_FOUND` | Run or artifact not found |
| 5 | `ILLEGAL_TRANSITION` | Illegal state transition |
| 6 | `VALIDATION_FAILED` | Validation failed |
| 7 | `APPROVAL_REQUIRED` | Approval required |
| 8 | `AGENT_ACTION_REQUIRED` | Agent action required |
| 9 | `RUN_BLOCKED` | Run blocked or stopped |
| 10 | `LOCK_HELD` | Concurrent run lock held |
| 11 | `ADAPTER_DRIFT` | Adapter drift detected |
| 12 | `INTERNAL_ERROR` | Internal or corrupt-state error |

Human-readable successful and actionable responses use stdout; errors use stderr. With `--json`, every response is exactly one JSON object. Expected errors contain `code`, `message`, and, when relevant, `details`.

Successful and actionable JSON responses use response schema version 1 and
contain stable `schema_version`, `kind`, `code`, and `message` keys. An
actionable phase response additionally contains `action`; approval boundaries
contain `approval` and `status`; read-only and terminal responses contain
`status`.

An action packet uses schema version 1 and contains stable keys for `run_id`,
`visit_id`, `visit_attempt`, `visit_status`, `phase`, `skill`, `inputs`,
`output`, `template`, `mutation`, `completion_criteria`, `validation`,
`approval_conditions`, `stop_conditions`, `outcomes`, and
`final_validation_command`. Literal artifact records retain repository- or
run-relative paths and add `absolute_path` for direct harness use.

## Validation and safety

Pipelines require a real Git worktree by default. A pipeline intended for a
non-Git fixture or repository must explicitly set `allow_non_git = true`.
Repository snapshots include every tracked and non-ignored untracked path and
record file content, mode, and symlink target without following symlinks.
`.git/` and CLI-owned `.specromancy/` storage are excluded.

Markdown validators require configured headings exactly once by default;
`heading_occurrence = "at-least-once"` relaxes duplicate handling. JSON
validators may reference a schema file and support only `type`, `required`,
`properties`, `items`, `enum`, `pattern`, and `additionalProperties`.
Unsupported schema keywords make the pipeline invalid at load time.

Validation commands are trusted repository configuration and execute from the
repository root with the user's permissions. They are argument arrays, never
shell strings. Full stdout and stderr remain in ignored run storage; manifests
contain byte-limited summaries with values from secret-like environment
variables redacted. The environment itself is never persisted.

Approval records bind the run, phase, visit, reason, output hash, pipeline hash,
outcome, actor, decision, and timestamps. Artifact or pipeline drift marks the
record stale and leaves the visit awaiting a fresh approval. Phase-visit and
transition-edge limits are checked atomically before a successor visit is
created; exceeding a limit blocks the run without resetting its counters.
