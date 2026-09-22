---
name: pipeline-status
description: Report the current state and recent handoff for a pipeline run.
---

Run `python3 POC_v2/pipeline.py status --run <run-id> --json`. Summarize the
current state, status, transition count, and most recent history item. Do not
advance the pipeline or modify files.
