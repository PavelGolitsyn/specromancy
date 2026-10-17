---
name: draft-release-notes
description: Draft release notes when the current release-documentation phase requests them.
license: MIT
compatibility: Specromancy pipeline schema version 1.
metadata:
  role: phase
---

# Draft release notes

Run the installed `specromancy` from the consumer project root. With the supplied
RUN_ID, inspect `specromancy status RUN_ID --json` and start or resume the
recorded phase with `specromancy phase RUN_ID draft-release-notes --json`.
Use the returned action packet as the authority for paths and policy.

Read its resolved request input and template. Draft the Summary, Changes, and
Upgrade Notes using only that request. Include every confirmed change and
required upgrade action; do not infer dates, compatibility, or performance.
If the request lacks enough change data, call `specromancy block RUN_ID
--reason insufficient-change-data --details TEXT --json` and stop.

Write only the exact `output.absolute_path`. A read-only phase may write its
designated output under engine-owned run storage; project files remain unchanged.
Never edit the request, completed outputs, `run.json`, or `events.jsonl`.
Run the packet's `final_validation_command` with `--json`. Its sole successful
outcome is `drafted`, selected automatically; do not pass `--outcome`.
Report the response and return control to the orchestrator. Do not publish notes.
