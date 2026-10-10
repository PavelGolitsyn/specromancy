---
name: review
description: Inspect changes and choose a verdict when the current Specromancy phase is review.
license: MIT
compatibility: Specromancy pipeline schema version 1.
metadata:
  role: phase
---

# Review

Use this procedure only when the user invocation supplies a `RUN_ID`.

1. Run `bin/specromancy status RUN_ID --json` and verify that the recorded
   current phase is `review`. If it is not, stop and report the recorded next
   action.
2. Run `bin/specromancy phase RUN_ID review --json` to start or resume the visit
   and treat its action packet as authoritative.
3. Read only the packet's resolved inputs and the repository evidence needed to
   inspect the implementation against the approved plan.
4. Preserve the packet's `read-only` mutation policy. Write only the review
   artifact at `action.output.absolute_path`, using the resolved template and
   every required heading. Record actionable findings and choose exactly one
   configured verdict: `approved` or `changes-requested`.
5. If a declared stop condition applies, run `bin/specromancy block RUN_ID`
   with its reason and details, then stop.
6. Run the packet's final validation command with the chosen configured
   `--outcome`. Do not infer completion or a repair visit from conversation.
7. Run `bin/specromancy status RUN_ID --json` and report its recorded status,
   next command, block, or terminal result.
