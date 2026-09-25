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
validate RUN_ID [PHASE]
approve RUN_ID PHASE
request-approval RUN_ID
block RUN_ID
status RUN_ID
resume RUN_ID
run RUN_ID
adapters generate
```

All commands accept `--root PATH`, `--pipeline PATH`, `--json`, and `--quiet`. Built-in commands are resolved before dynamic phase aliases; pipeline phase names therefore cannot shadow a reserved command.

Both `bin/specromancy` and `python -m specromancy` invoke the same package entry point. The repository root is found by walking upward to a `.git` directory or worktree marker. `--root` supplies an explicit root for fixtures and non-Git directories.

## Filesystem ownership

The CLI may create or replace files only in:

- `.specromancy/runs/<run-id>/`;
- generated adapter paths recorded in `adapters/manifest.json`;
- explicit temporary files adjacent to a manifest during atomic replacement.

The CLI never deletes, resets, stages, or commits repository work. Cleanup is limited to generated paths owned by the previous adapter manifest.

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
