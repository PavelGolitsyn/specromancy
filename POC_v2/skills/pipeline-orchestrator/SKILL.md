---
name: pipeline-orchestrator
description: Run or resume the repository's configured state-machine pipeline for a user task.
---

# Pipeline orchestrator

Work from the target repository root. The controller owns state; do not edit
generated `state.json` files directly.

1. Validate the definition with `python3 POC_v2/pipeline.py validate`.
2. Inspect the requested run with `python3 POC_v2/pipeline.py status --run ID`.
   If it does not exist, create it with `start --run ID --task TASK`.
3. While the run is active, render the current packet with
   `python3 POC_v2/pipeline.py prompt --run ID`.
4. Follow the embedded stage skill. Respect the harness's normal permission and
   approval boundaries.
5. Select one of the packet's allowed outcomes. Record it with
   `python3 POC_v2/pipeline.py advance --run ID --outcome OUTCOME --summary
   SUMMARY`, adding each durable output with `--artifact PATH`.
6. Repeat from step 3 until the run is `completed` or `blocked`.

Do not infer success merely because work was attempted. Use `blocked` when the
stage cannot safely satisfy its contract. Stop if the controller rejects a
transition or reaches its transition limit; report the run ID and error.
