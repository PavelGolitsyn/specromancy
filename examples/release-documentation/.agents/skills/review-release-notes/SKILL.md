---
name: review-release-notes
description: Review release notes when the current release-documentation phase requests a verdict.
license: MIT
compatibility: Specromancy pipeline schema version 1.
metadata:
  role: phase
---

# Review release notes

Run the installed `specromancy` from the consumer project root. With the supplied
RUN_ID, inspect `specromancy status RUN_ID --json` and start or resume the
recorded phase with `specromancy phase RUN_ID review-release-notes --json`.
Read only the packet's resolved request and draft inputs, plus its template.

Compare each draft claim with the request. Check that every confirmed change and
required upgrade instruction is present. Write Verdict, Findings, and Verification
to the exact `output.absolute_path`; do not repair the sealed draft or edit any
project file. Never edit `run.json` or `events.jsonl`.

If the draft faithfully covers the request, run `final_validation_command` with
`--json`. Its sole successful outcome is `approved`, selected automatically;
do not pass `--outcome`. Otherwise record discrepancies in the review output,
then call `specromancy block RUN_ID --reason unsupported-release-claims
--details TEXT --json` and stop. Use that same stop when inputs cannot support
a review at all. Report the recorded result and return to the orchestrator.

The outcome `approved` is this example's review verdict, not a human approval
gate or permission to publish. The engine validates structure and mutation policy;
the reviewing agent is responsible for checking factual accuracy.
