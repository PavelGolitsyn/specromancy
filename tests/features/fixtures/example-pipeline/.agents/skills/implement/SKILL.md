---
name: implement
description: Apply an approved plan when the current Specromancy phase is implement.
license: MIT
compatibility: Specromancy pipeline schema version 1.
metadata:
  role: phase
---

# Implement

Use this procedure only when the user invocation supplies a `RUN_ID`.

1. Run `bin/specromancy status RUN_ID --json` and verify that the recorded
   current phase is `implement`. If it is not, stop and report the recorded next
   action.
2. Run `bin/specromancy phase RUN_ID implement --json` to start or resume the
   visit and treat its action packet as authoritative.
3. Read only the packet's resolved inputs and the repository context needed to
   apply the approved plan.
4. Respect the packet's mutation policy. Change only repository files required
   by the approved plan, and write the implementation record only at
   `action.output.absolute_path` with every required heading.
5. Record changes, deviations from the plan, and verification in that artifact.
   For `destructive-action`, `external-side-effect`, `material-scope-change`, or
   `new-production-dependency`, run `bin/specromancy request-approval RUN_ID`
   with the matching declared reason and details, then stop. If a declared stop
   condition applies, run `bin/specromancy block RUN_ID` with its reason and
   details, then stop.
6. Run the packet's configured validation commands through its final validation
   command exactly. Do not substitute remembered or easier checks.
7. Run `bin/specromancy status RUN_ID --json` and report its recorded status,
   next command, or terminal result rather than claiming success from memory.
