# Stage 03 — Run store, artifacts, and recovery

## Outcome

Persist all cross-phase state in a run directory that can be inspected, verified, and resumed by a new process or harness.

## Runtime layout

```text
.specromancy/runs/<run-id>/
  run.json
  events.jsonl
  .lock
  artifacts/
    000-request.md
    001-<phase>.md
    002-<phase>.md
  commands/
    <visit>-<command>.stdout.txt
    <visit>-<command>.stderr.txt
```

Artifacts are immutable after a visit is completed. Repeated phases receive new visit numbers and new artifact names; prior review and repair history is never overwritten.

## Files introduced or completed

```text
specromancy/run_store.py
specromancy/artifacts.py
specromancy/hashing.py
specromancy/locking.py
specromancy/schemas/run.schema.json
specromancy/schemas/event.schema.json
tests/unit/test_run_store.py
tests/contract/test_recovery.py
```

## Work items

### 1. Generate safe run IDs

Use UTC timestamp plus cryptographically random lowercase hex, for example `20260922T142501Z-a1b2c3d4`. Validate IDs before using them in a path. Reject separators, dot segments, and identifiers that do not match the run-ID pattern.

Allow a deterministic injected clock and random source in tests.

### 2. Define the run manifest

`run.json` includes:

- schema version and run ID;
- pipeline ID, version, path, and canonical hash;
- overall status;
- current visit number;
- request artifact path and hash;
- Git base/head metadata;
- creation and update timestamps;
- ordered visit records;
- ordered approval records;
- terminal result or block reason.

A visit record includes:

- phase ID, ordinal, and per-phase attempt number;
- `pending`, `active`, `awaiting-approval`, `completed`, `failed`, or `blocked` status;
- resolved input paths and hashes;
- output path and hash;
- mutation baseline and result;
- validation checks and command results;
- chosen outcome and transition target;
- skill and template hashes;
- start and completion timestamps;
- declared deviations.

Prefer explicit fields over an unstructured metadata bag.

### 3. Append audit events

Each manifest mutation appends an event containing:

- monotonically increasing sequence number;
- timestamp;
- run ID and visit number;
- event type;
- minimal structured payload;
- resulting manifest hash.

Expected event types include `run-created`, `visit-started`, `validation-failed`, `visit-completed`, `approval-requested`, `approval-recorded`, `run-blocked`, and `run-completed`.

`run.json` remains the fast canonical snapshot. `events.jsonl` provides diagnosis and recovery evidence, not an event-sourcing requirement for the POC.

### 4. Make writes atomic

For every state change:

1. Acquire the per-run lock.
2. Read and validate the current manifest.
3. Compute the next manifest entirely in memory.
4. Write JSON to a temporary file in the run directory.
5. Flush and replace `run.json` atomically.
6. Append and flush the corresponding event.
7. Release the lock.

Define the recovery behavior for interruption between steps 5 and 6: status detects that the final event hash is behind the manifest, emits a recovery event, and continues. An invalid or partially written manifest is a corruption error and must never be guessed back into shape.

### 5. Implement artifact addressing

Symbolic input references resolve to exact immutable files:

- `request` resolves to `000-request.md`;
- `latest:<phase>` resolves to the latest completed visit output for that phase;
- `visit:<number>` resolves to a specific visit output.

Resolution happens when a visit is created and is then stored literally in `run.json`. Later graph changes or new visits cannot alter a visit's already-resolved inputs.

### 6. Hash provenance

Use SHA-256 for:

- request and phase artifacts;
- skill files;
- templates;
- pipeline configuration;
- repository snapshots;
- manifest versions.

Use normalized relative paths in manifests, but resolve them against the validated repository/run root before access.

### 7. Implement locking

Use an exclusive create or an OS-supported advisory lock through the standard library. Record PID and acquisition time for diagnostics. Do not automatically remove a seemingly stale lock based only on time; provide a clear manual recovery instruction.

## Tests

- Run IDs are unique and path-safe.
- Creation produces valid request, manifest, and first event.
- Atomic replacement never leaves a partial JSON file in fault-injection tests.
- Two writers cannot mutate one run concurrently.
- Artifact hashes detect post-completion edits.
- Repeated phases get distinct visit numbers and paths.
- A new process reconstructs current state from disk only.
- Missing, malformed, and path-escaping artifact references fail safely.
- Manifest/event mismatch is diagnosed and recoverable as specified.

## Exit criteria

- Runs survive process restart without in-memory state.
- Every completed artifact has a recorded hash and provenance.
- Runtime writes are atomic and locked.
- No artifact from an earlier visit is overwritten.

