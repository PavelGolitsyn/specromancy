# Stage 6: Orchestration and CLI

## Objective

Integrate the four phase implementations into a resumable state machine with explicit gates, locking, status inspection, audit events, and a bounded repair loop.

## Dependencies

- Stages 0 through 5.

## Deliverables

- `.agents/skills/pipeline/SKILL.md`
- `.agents/skills/pipeline/references/state-machine.md`
- `src/specromancy/run.py`
- `src/specromancy/state.py`
- `src/specromancy/events.py`
- `src/specromancy/locking.py`
- `src/specromancy/orchestrator.py`
- Completed CLI subcommands in `src/specromancy/cli.py`
- `tests/contract/test_state_machine.py`
- `tests/integration/test_complete_run.py`

## CLI surface

The POC exposes:

```text
specromancy init [--title TEXT] [--request FILE]
specromancy status RUN_ID
specromancy next RUN_ID
specromancy phase start RUN_ID PHASE
specromancy phase complete RUN_ID PHASE
specromancy phase fail RUN_ID PHASE --reason TEXT
specromancy artifact path RUN_ID ARTIFACT
specromancy artifact verify RUN_ID [ARTIFACT]
specromancy approve RUN_ID plan --by IDENTITY [--note TEXT]
specromancy approval revoke RUN_ID plan --by IDENTITY --reason TEXT
specromancy validate RUN_ID [PHASE]
specromancy resume RUN_ID
specromancy cancel RUN_ID --reason TEXT
specromancy lock inspect RUN_ID
specromancy lock recover RUN_ID
```

`next` reports the next permitted action and required gate; it does not call a model. `resume` validates state, artifacts, repository identity, and locks, then prints a harness-neutral continuation brief.

## Run initialization

`init` must:

1. Discover and validate the repository root.
2. Create a collision-resistant, human-readable run ID.
3. Create the run directory atomically.
4. Copy or normalize the request into `request.md`.
5. Assign stable requirement IDs to explicit acceptance criteria when present.
6. Capture repository URL when available, current branch, base commit, and dirty paths.
7. Create `run.json` and the first `events.jsonl` record.
8. Return the run ID, artifact paths, and recommended research invocation.

Re-initialization with the same user-supplied ID must fail unless an explicit resume command is used.

## State transition engine

Implement one transition function that:

- loads the state table from the packaged contract;
- acquires the run lock;
- reloads `run.json` after acquiring the lock;
- verifies the expected current state;
- executes phase-specific guards;
- writes the event and updated manifest atomically;
- releases the lock;
- returns the new state and next permitted actions.

No phase module may update `run.json` directly. Phase modules return validated transition data to the state engine.

## Pipeline skill behavior

The pipeline skill is an interactive orchestrator, not a second implementation of phase logic. It must:

1. Initialize or identify a run.
2. Query `specromancy next` before choosing a phase.
3. Load and follow the canonical skill for that phase.
4. Stop at explicit approval gates.
5. Surface blocked states and validation errors accurately.
6. On `changes_requested`, invoke implementation in repair mode with the current review artifact.
7. Stop when `passed`, `blocked`, `cancelled`, or the review-cycle limit is reached.
8. Provide a final summary with run ID, status, artifacts, changed files, and verification.

It must not claim completion merely because an agent response ended.

## Resume and recovery

`resume` handles:

- valid incomplete runs;
- a phase marked in progress after the previous session ended;
- missing or stale locks;
- artifacts edited outside the CLI;
- repository HEAD changes;
- plan approval invalidated by edits;
- review verdict invalidated by diff changes.

Recovery policy:

- Revalidate all recorded artifact digests.
- Never silently accept changed artifacts.
- Offer a precise next action: restore artifact, revoke approval, restart phase, or cancel run.
- Require an explicit `lock recover` when a lock owner is no longer alive or the lock age exceeds policy.
- Preserve all prior events; recovery adds compensating events.

## Repair loop

On `changes_requested`:

1. Increment `review_cycle` only when repair implementation begins.
2. Verify the cycle does not exceed `max_review_cycles`.
3. Require implementation to reference all blocking finding IDs.
4. Return to `implementation_ready` after repair validation.
5. Require a full new review and fresh diff digest.
6. Transition to `blocked` with a clear reason when the cycle limit is exhausted.

The user may explicitly increase the limit through a future command; changing it is outside the POC unless added through a decision record.

## Implementation tasks

1. Implement run manifest serialization and invariant checks.
2. Implement the state engine from `pipeline.json`.
3. Implement cross-platform run locks and lock diagnostics.
4. Complete all CLI commands and both output formats.
5. Create the pipeline skill and state-machine reference.
6. Implement continuation briefs for every nonterminal state.
7. Integrate phase validators and guards.
8. Implement repair-cycle tracking and exhaustion.
9. Add cancellation without deleting artifacts.
10. Add end-to-end event audit verification.

## Tests

- Complete happy-path run.
- Approval stop and resume.
- Changes-requested repair and eventual pass.
- Repair-cycle exhaustion.
- Concurrent transition attempts.
- Abrupt exit with a stale lock.
- Artifact edited between phases.
- Repository HEAD changed outside the run.
- Cancellation from each nonterminal phase.
- JSON output remains machine-readable for all expected errors.
- Event log replays to the same final state as `run.json`.

Use process-level integration tests for locking and atomic updates rather than relying only on unit mocks.

## Exit criteria

- Every status change goes through one transition engine.
- A run can be resumed in a new process using files alone.
- The complete happy path and repair path pass in fixture repositories.
- Concurrent or stale actors cannot silently overwrite state.
- Terminal summaries match durable state and validated artifacts.

## Risks and mitigations

- **CLI becomes an agent runner:** maintain the boundary that it coordinates artifacts and state only.
- **Manifest/event divergence:** replay events in tests and write both under the same lock.
- **Cross-platform locking differences:** use exclusive file creation and explicit recovery instead of OS-specific advisory locks for the POC.
- **Invalid partial writes:** use atomic replacement and retain a last-known-good backup only if testing demonstrates a need.

