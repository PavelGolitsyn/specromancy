# Specromancy POC public contracts

These contracts are stable across the POC. Breaking representation changes
require a schema-version change and updated fixtures; additive fields with
backward-compatible defaults may extend the current version.

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
init DESCRIPTION --pipeline ID
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

Workflow commands accept `--root PATH`, `--pipeline ID`, `--json`, and `--quiet`. Built-in commands are resolved before dynamic phase aliases; pipeline phase names therefore cannot shadow a reserved command.

`--reason` may be omitted only when the current phase declares exactly one
reason of the relevant kind. `validate --outcome` is required when a phase has
multiple non-blocking outcomes and is rejected when there is only one.

Both `bin/specromancy` and `python -m specromancy` invoke the same package entry point. The repository root is found by walking upward to a `.git` directory or worktree marker. `--root` supplies an explicit root for fixtures and non-Git directories.

`adapters generate` deterministically renders harness-native adapters from
`AGENTS.md`, the mandatory registry, every validated registered graph and its
referenced templates/schemas, canonical `.agents/skills`,
and CLI command/help metadata. Generation is registry-wide and rejects
`--pipeline`. It generates `.agents/skills/specromancy-<id>/SKILL.md` and Claude
launch-skill mirrors. These delegate to the canonical pipeline procedure and
contain no graph policy. Generated launch skills are excluded from canonical
source hashing. Their prefix is reserved; canonical skills outside that namespace
are never owned or removed by the generator. `--check` performs no writes and exits with
`ADAPTER_DRIFT` when the manifest or managed tree differs from the expected
rendering.

The Python `cli.adapter_command_metadata` facade shares explicit descriptions
with parser construction and returns the same sorted command metadata without
inspecting argparse internals. `adapters.render_adapters(root, registry, metadata)`
retains its render-only contract. `adapters.generate_adapters` still accepts
explicit metadata; when omitted, metadata is derived from that invocation's
validated graphs. Generation reuses captured source text and bytes for rendering
and source hashes, without a cross-invocation cache. Adapter constants and
`AdapterError` remain available from `specromancy.adapters`.

## Pipeline registry and selection

`workflow/pipelines.toml` is mandatory for workflow and adapter commands:

```toml
schema_version = 1

[[pipelines]]
id = "implementation"
path = "pipelines/implementation.toml"
```

At least one registration is required. Only `schema_version` and `pipelines`
are accepted at the top level; each registration contains only `id` and `path`.
IDs use lowercase kebab-case, match the graph's ID, and are unique. Resolved
paths are unique TOML files under `workflow/pipelines/`, relative to `workflow/`.
Segments use letters, numbers, underscores or hyphens. Unsafe, escaping,
missing and duplicate paths are rejected with `INVALID_PIPELINE` diagnostics.
The registry format is published in `specromancy/schemas/pipelines.schema.json`;
filesystem containment and cross-file identity are additionally validated by
the loader. `load_registry(root)` returns immutable registrations; `load(id)`
validates the selected graph and `load_all()` validates every registration.
`load_pipeline(path, root)` remains a low-level explicit-path API with no default.

Initialization requires `--pipeline ID`, even for a single registration. Paths
and unknown IDs cannot initialize a run. Existing-run commands select the graph
from validated persisted provenance; an optional ID must match the run. Paths
are not accepted as selectors. Packets omit the selector in their validation command.
Pipeline edits still enforce provenance and approval invalidation. Removing a
registration disables initialization but retains existing-run access while the
original files exist. Registry ordering and unrelated graph edits do not alter
another pipeline's run. Every workflow command requires a valid registry;
help remains available without one.

Skills are shared by repository-root skill name. Templates and validator paths
resolve relative to each graph and may reference shared repository files through
parent segments when containment is preserved.

## Filesystem ownership

The CLI may create or replace files only in:

- `.specromancy/runs/<run-id>/`;
- generated adapter paths recorded in `adapters/manifest.json`;
- explicit temporary files adjacent to a manifest during atomic replacement.

The CLI never deletes, resets, stages, or commits repository work. Cleanup is limited to generated paths owned by the previous adapter manifest.

`adapters/manifest.json` is the schema-versioned ownership boundary. It records
the generator version and regeneration command, canonical source records and
aggregate hash, every generated adapter path and content hash, and generated or
native mode for every supported harness. Native Codex and Hermes targets
record shared launch-skill `discovery_paths`; native `.agents` outputs have a
single ownership record under the Codex target. The manifest omits its own hash to
avoid self-reference and contains no timestamps or absolute paths.

Generation preflights ownership conflicts before writing, rechecks stale owned
file hashes before removal, replaces each output atomically, and writes the
manifest last. This is not a transaction across all generated files. Check mode
compares expected bytes directly and creates no temporary output files.

## Run persistence

Run IDs use a UTC timestamp and eight lowercase hexadecimal characters, for
example `20260922T142501Z-a1b2c3d4`. Only IDs matching that form may be used to
address `.specromancy/runs/`.

The `specromancy.run_store` imports and compatibility aliases remain available,
including the same exception classes re-exported from `run_errors`. Run and
event schema versions remain 1. `RunStore` returns ordinary, defensively copied
dictionaries; record annotations neither construct defaults nor validate
external data. Generation accepts injected clocks and zero-argument or sized
random sources, and timestamp formatting remains UTC with microseconds and `Z`.

`run.json` is the validated current snapshot. Each mutation increments its
`revision`, atomically replaces the file, and appends an `events.jsonl` record
that contains the revision and canonical manifest hash. If interruption occurs
after replacement but before the event append, the next load appends a
`recovery` event. A malformed manifest, a malformed event, a non-contiguous
event sequence, or any other manifest/event disagreement is corrupt state and
is not repaired heuristically.

Run and visit statuses must be recognized strings. Invalid JSON status values,
including arrays and objects, raise `RunCorruptionError` with exit code 12 and
details `{"error_code": "corrupt-run", "run_id": "<run-id>"}`. The messages are
`manifest status is invalid` and `visit identity or status is invalid`,
respectively, subject to earlier validation failures. Manifest validation occurs
before event reconciliation: malformed statuses leave `run.json` and
`events.jsonl` unchanged even when the log is one revision behind. Version-1
acceptance of numeric quirks, open approval dictionaries, and weak nested metadata
is unchanged; the [compatibility decision matrix](../refactoring/14-persisted-data-diagnostics.md#nested-validation-decision-matrix)
records the separately deferred hardening work.

The internal `run_persistence` component owns serialization, reconciliation,
and commits. `RunStore` retains repository/run path ownership checks and artifact
verification, and collects evidence for the pure internal `visit_transitions`
decisions. Those decisions return copied state and event payloads (or an explicit
no-op); they do not read files or clocks, assign revisions, or acquire locks.
One lock spans manifest/event loading, the
change, validation, replacement, and append; internal commit helpers do not
reacquire it. Idempotent activation, transition, and resume returns do not add
a revision or event. The general `mutate` API always commits, even if its callback
leaves the record unchanged.

Visit preparation resolves symbolic inputs and hashes skill/template provenance
immediately, including for a pending successor at a paused edge. Activation
records the start timestamp and mutation baseline without refreshing those
records. A graph transition seals the current output and prepares its successor
in one commit; a reached limit records a blocked visit without sealing its output
or creating a successor. Resume releases a paused checkpoint while leaving the
successor pending. The low-level `start_visit` and `complete_visit` methods retain
their separate semantics: start appends an active visit, and completion seals a
visit without advancing the run. Completion rejects an already completed visit;
transition accepts an exact outcome/target retry without another commit.

`load(recover=False)` checks consistency without appending recovery events.
`load(verify_artifacts=False)` skips artifact verification independently and
still permits recovery by default. Normal loads, including those invoked by
`status`, may append the allowed recovery event; recovery precedes artifact
verification, so an artifact error may be reported after that append.

Creation first makes the run directory and request artifact, then commits
revision 1. Engine initialization prepares its first visit in a separate commit.
Interruption can therefore leave a directory/request without a manifest or a
created run without a visit. These operations are not one transaction, and the
store does not automatically clean up partially initialized runs.

Each run uses an exclusive `.lock` file containing the owner PID and acquisition
time. Locks are never expired based on age alone. After verifying that its owner
is no longer running, a stale lock must be removed manually.

Artifact paths in manifests are normalized relative paths. Symbolic inputs are
resolved once, when a visit is prepared (or created active by `start_visit`), to
literal paths and SHA-256 hashes. Activating a pending visit does not resolve
them again. Request artifacts and completed visit outputs are immutable; hash drift is a corrupt
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
| 13 | `RUN_PAUSED` | Run paused at a configured checkpoint |

Human-readable successful and actionable responses use stdout; errors use stderr. With `--json`, every response is exactly one JSON object. Expected errors contain `code`, `message`, and, when relevant, `details`.

Successful and actionable JSON responses use response schema version 1 and
contain stable `schema_version`, `kind`, `code`, and `message` keys. An
actionable phase response additionally contains `action`; approval boundaries
contain `approval` and `status`; paused, read-only, and terminal responses
contain `status`.

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

Validation checks the output artifact first, runs commands sequentially, and
then checks the repository mutation policy. A required command failure stops
the command sequence; an optional failure does not. Mutation enforcement still
runs after command execution and its failure takes precedence over a required
command failure. An expected validation failure records one attempt with the
available artifact, command, and mutation evidence before returning its error;
the visit remains retriable.

Approval records bind the run, phase, visit, reason, output hash, pipeline hash,
outcome, actor, decision, and timestamps. Artifact or pipeline drift marks the
record stale and leaves the visit awaiting a fresh approval. Phase-visit and
transition-edge limits are checked atomically before a successor visit is
created; exceeding a limit blocks the run without resetting its counters.

Approval grant and advancement are separate durable operations. After an
interruption following grant, `approve` can resume advancement and revalidation;
failed revalidation retains the approval record and its audit history. Pending
or granted approval drift is recorded as stale before `approve` returns the
stale-approval error. Ordinary commands reject pipeline or prepared resource
drift; `status` instead reports warnings and remains readable when artifact
hashes drift.

Approval requests, grants, and invalidations decide against current persisted
state while holding the run lock. The observed request identity is `run_id`,
`visit_number`, `phase_id`, `reason`, `details`, `requested_at`, `outcome`,
`pipeline_sha256`, and `artifact_sha256`; the containing run and referenced visit
must also agree. Decision fields (`status`, `decision`, `actor`, `decided_at`) are
mutable and excluded from identity. No persisted request ID is required.

Overlapping request creators compare that identity except `requested_at`. An
identical pending request returns the winner's record and evidence with
`approval is already pending` (7), without changing its timestamp or adding a
revision/event. A new request adds one `approval-requested` revision/event.
Conflicting bindings or an overtaken visit cannot attach evidence to a successor,
even if it reuses the same phase ID.

An exact pending request on the current awaiting-approval visit is granted once.
An already granted request on that visit resumes revalidation using its saved
outcome, without another grant event. If its visit already completed with that
outcome and the configured target, an in-flight approve returns the existing
`approval was already recorded` response family for current state and never
advances the successor. Each successful continuation adds one `visit-transitioned`
event (or `loop-limit-exceeded`); an exact transition retry adds none. Each
expected validation failure adds one `validation-failed` event and retains the
grant; interruption before evidence recording adds none. Duplicate continuations
may still execute validation commands more than once.

A stale observation invalidates only its exact eligible pending or granted
request, adding one `approval-invalidated` revision/event before returning
`stale-approval` (7). Mismatch labels remain ordered: `artifact`, then `pipeline`.
An in-flight duplicate invalidation of that same request returns `stale-approval`
without another event, provided no replacement or visit change has occurred.

An overtaken decision whose request is absent, replaced, ambiguous, missing
identity fields, associated with the wrong run/visit, or completed with a different
outcome/target fails with `EngineError`, `ILLEGAL_TRANSITION` (5), diagnostic
`approval-state-changed`, and message `approval state changed before the command
could be applied`. Details contain `error_code`, `run_id`, observed `phase`, and
observed `visit_number`. The conflict creates no revision/event and preserves the
winner. Fresh sequential commands finding a different pending request, or finding
no pending request after invalidation, retain `illegal-transition`.

Lock contention still returns `LOCK_HELD` (10) without implicit retries. General
`RunStore.mutate` still commits an unchanged callback; only explicit decision
no-ops skip commits. Approval decisions use the existing persistence protocol:
interruption after manifest replacement but before event append is repaired on
load with one `recovery` event at the same revision, without synthesizing the
missing approval event. Schemas and existing stored records remain compatible.
External artifact edits are not made atomic with validation by this lock.
