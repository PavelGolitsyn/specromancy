---
name: pipeline
description: Initialize or resume a Specromancy run when coordinating its configured phases.
license: MIT
compatibility: Specromancy pipeline schema version 1.
metadata:
  role: orchestrator
---

# Pipeline

Treat the CLI's persisted state and action packets as authoritative. Do not
reconstruct state from conversation and never edit `run.json` or `events.jsonl`.

For a new request, run `bin/specromancy init DESCRIPTION --json` and retain the
emitted `RUN_ID`. For an existing invocation, obtain `RUN_ID` from the user; do
not guess it.

1. Run `bin/specromancy status RUN_ID --json`.
2. If the run is awaiting agent work, use its recorded phase and next command to
   start or resume that visit, then load and follow the canonical skill named by
   the emitted action packet.
3. Let that phase skill read only resolved inputs, honor its mutation policy,
   write its exact output, handle declared approval or stop conditions, and run
   the packet's validation command.
4. Query status again and repeat only while the recorded state requests another
   agent action.
5. Stop immediately for approval, a block, a validation failure, or completion,
   and report the CLI's recorded state and required user action.

Never assume phase names, their order, or their outcomes. Never bypass approval
or validation, invent an output path, or continue from memory after a process
restart.
