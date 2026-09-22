# Stage 04 — Generic state machine and CLI

## Outcome

Implement phase execution mechanics and expose them through a stable, harness-neutral command line. The CLI prepares work and advances deterministic state; it never launches an LLM harness.

## Files introduced or completed

```text
specromancy/engine.py
specromancy/actions.py
specromancy/cli.py
specromancy/status.py
tests/unit/test_engine.py
tests/contract/test_cli.py
```

## State model

Run statuses:

```text
active
awaiting-agent
awaiting-approval
blocked
completed
failed
```

Visit statuses:

```text
pending -> active -> completed
                  -> awaiting-approval -> completed
                  -> blocked
                  -> failed
```

Only configured outcomes choose graph edges. A phase name never implies a transition.

## Work items

### 1. Implement action packets

Starting or resuming a visit emits a fully resolved packet containing:

- run and visit IDs;
- current phase and skill path;
- exact input artifact paths and hashes;
- exact output artifact path;
- mutation policy and allowlist;
- completion criteria;
- validation commands;
- approval and stop conditions;
- exact final validation command.

The human representation is concise Markdown-like terminal output. `--json` emits a versioned object with stable keys.

### 2. Implement `init`

`init DESCRIPTION` must:

1. Load and validate the pipeline.
2. Capture initial Git metadata.
3. Create the run directory and request artifact from its template.
4. Create `run.json` and the first pending visit.
5. Print the run ID and first action packet.

Support `--description-file` as a later-compatible option if multiline shell quoting becomes a problem, but it is not required for the first slice.

### 3. Implement phase commands

Both commands are equivalent:

```bash
specromancy phase RUN_ID research
specromancy research RUN_ID
```

They verify that the requested phase matches the current visit, capture the mutation baseline, mark the visit active, and emit the action packet. Repeating the command for an already active visit is idempotent and returns the same packet.

Trying to start a different phase produces an illegal-transition error and reports the expected phase.

### 4. Implement `validate`

`validate` calls a validator interface. This stage supplies the minimal file-exists/non-empty implementation needed for end-to-end CLI tests; Stage 05 replaces it with the complete artifact, Git, command, approval, and safety validator without changing the engine interface. On success it:

- records output and provenance hashes;
- records the selected configured outcome;
- enters `awaiting-approval`, advances to the next visit, or completes/stops the run;
- appends the transition event;
- prints the next required action.

Support `--outcome` only when the phase declares more than one successful outcome. Reject undeclared outcomes.

### 5. Implement approvals and blocks

`request-approval` transitions only the active visit to `awaiting-approval` using a declared reason code. It stores details and the current artifact hash.

`approve RUN_ID PHASE` verifies the current phase, pending request, and unchanged artifact hash, then records the approval and executes the configured transition.

`block` records a declared stop reason and leaves an inspectable terminal or user-resumable state according to configuration. It must not fabricate a successful artifact.

### 6. Implement status and resume

`status` is read-only and reports:

- pipeline and run identity;
- current phase, visit, and status;
- completed visits;
- pending approval or block details;
- next command;
- configuration drift or artifact-integrity warnings.

`resume` performs integrity checks and returns the current action packet. It does not automatically rerun completed validation commands.

### 7. Implement `run`

`run` repeatedly performs only deterministic work:

- load and integrity-check the run;
- execute an already-satisfied transition;
- create the next visit;
- stop when agent work, approval, a block, failure, or completion is reached.

It exits with `AGENT_ACTION_REQUIRED` when an artifact must be authored. It must not shell out to Codex, Claude Code, Copilot, Hermes, or OpenCode.

### 8. Ensure idempotency

Re-running a command after an uncertain terminal interruption must either:

- return the already-recorded result; or
- reject it as incompatible with the current state.

It must never create duplicate visits, approvals, or completion events.

## Tests

- Happy-path single and multi-phase pipelines.
- Dynamic aliases and the generic `phase` command are equivalent.
- Built-in command names cannot be shadowed.
- Illegal phase start, outcome, approval, and terminal transitions fail.
- Repeated start, validate, approve, status, and resume calls are idempotent.
- `run` stops at agent and approval boundaries.
- JSON responses conform to the documented shape for every status.
- No test depends on an example phase name in engine setup.

## Exit criteria

- A fixture pipeline can be driven entirely through subprocess CLI calls.
- A new process can resume at every non-terminal state.
- The CLI never invokes a harness.
- All transition decisions come from configuration plus recorded outcomes.
