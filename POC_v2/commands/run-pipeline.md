---
name: run-pipeline
description: Start or resume the repository's configured agent pipeline for a task.
---

Use `POC_v2/skills/pipeline-orchestrator/SKILL.md` to run the requested task.

If no run ID is supplied, derive a short lowercase ID from the task. If that ID
already exists, resume it instead of overwriting it. Keep harness-specific
permissions and approval behavior unchanged.
