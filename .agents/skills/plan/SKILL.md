---
name: plan
description: Map requirements to files and verification when the current Specromancy phase is plan.
license: MIT
compatibility: Specromancy pipeline schema version 1.
metadata:
  role: phase
---

# Plan

Use this procedure only when the user invocation supplies a `RUN_ID`.

1. Run `bin/specromancy status RUN_ID --json` and verify that the recorded
   current phase is `plan`. If it is not, stop and report the recorded next
   action.
2. Run `bin/specromancy phase RUN_ID plan --json` to start or resume the visit
   and treat its action packet as authoritative.
3. Read only the packet's resolved inputs and the repository context needed to
   map requirements to intended files, focused tests, full verification, and
   risks.
4. Preserve the packet's `read-only` mutation policy. Write only the plan
   artifact at `action.output.absolute_path`, using the resolved template and
   every required heading.
5. If a declared stop condition applies, run `bin/specromancy block RUN_ID`
   with its reason and details, then stop.
6. If the plan introduces a `material-scope-change`, run
   `bin/specromancy request-approval RUN_ID --reason material-scope-change --json`
   and stop at that boundary. Otherwise, run the packet's final validation
   command exactly.
7. Run `bin/specromancy status RUN_ID --json` and report its recorded status,
   next command, or terminal result.
