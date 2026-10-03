# Stage 08 — Verify integration and finish documentation

Prerequisites: all earlier stages. Do not defer their focused verification until
this stage; this is the final cross-boundary check.

## Purpose

Confirm that the refactoring improved responsibility boundaries without changing
how users run pipelines, recover interruptions, approve artifacts, or regenerate
adapters. Update documentation to describe the final code rather than only this
proposed structure.

## Files and outputs

- Update `docs/poc-v3/architecture.md` with the final dependency/responsibility map.
- Update `docs/poc-v3/contracts.md` and `cli.md` if clarification is needed, keeping
  the existing public contract explicit and recording any separately approved
  behavior changes rather than describing them as mechanical moves.
- Update `tests/README.md` for genuinely new fixture/test organization.
- Update this plan's stage checklists and evidence; retain the original baseline.
- Touch generated paths only if canonical inputs intentionally changed in an
  independently justified change and normal ownership-safe generation permits it.

## Work items

- [ ] Replay Stage 01 version-1 fixtures through the final implementation. Verify
  active, pending, approved, paused, terminal, and recoverable states remain usable.
- [ ] Compare canonical pipeline bytes/hashes, action packets, error envelopes,
  event traces, and adapter outputs against baseline expectations. Investigate
  all differences before adjusting expected values.
- [ ] Audit dependency direction: models/validators are leaves; persistence does
  not depend on engine/CLI; state decisions do not perform IO; adapter rendering
  does not implement workflow policy.
- [ ] Remove obsolete private code and duplicated implementations only after all
  callers have moved. Keep documented/public compatibility aliases; do not remove
  them as cleanup without a separate deprecation decision.
- [ ] Review tests for meaningful behavior, fixture independence, and recursive
  architecture coverage. Avoid introducing dependence on shipped phase names in
  generic tests or new tests that only assert an internal helper was called.
- [ ] Run compatibility checks on Python 3.11 and the current development Python.
  Record unavailable interpreters as unverified instead of claiming full coverage.
- [ ] Run source-export/launcher tests and confirm no third-party runtime imports
  were added. Confirm the CLI still works without package installation.
- [ ] Inspect changes for ownership violations or unrelated edits. Do not stage,
  commit, reset, or delete user work as a side effect of verification.
- [ ] Record separately deferred defects and enhancements with concrete evidence,
  affected contracts, and suggested follow-up scope.

## Final verification commands

```sh
python -m unittest discover -s tests/features -t .
python -m unittest discover -s tests/shipped_configuration -t .
python -m unittest discover
bin/specromancy adapters generate --check
git diff --check
git status --short
```

The split runs help diagnose fixture/configuration coupling. If they have already
passed for the unchanged final revision, do not repeat them unnecessarily; the
full suite is the required final gate. Use `python3` when that is the interpreter
available locally, and record the exact version.

## Completion evidence

Fill in this table at implementation closeout, not during planning.

| Gate | Required evidence | Result |
| --- | --- | --- |
| Python 3.11 | Full-suite result and interpreter version | Not run for implementation |
| Development Python | Full-suite result and interpreter version | Not run for implementation |
| Persisted compatibility | Fixture replay and trace comparisons | Not run |
| CLI/launcher | Contract and fresh-export tests | Not run |
| Generated files | Drift check plus deterministic fixture generation | Not run |
| Architecture | Generic policy/dependency/ownership checks | Not run |
| Documentation | Final file map and unchanged public contracts reviewed | Not done |
| Scope | Diff has only planned or explicitly justified changes | Not reviewed |

## Exit criteria and rollback

All required gates pass, public contracts are documented, generated output is
reproducible, and no unrelated content changed. Report completed stages and
remaining limitations using evidence rather than a file-size reduction target.
If an integration regression appears, identify and repair or revert the smallest
responsible code change. Do not migrate or rewrite runs to make compatibility
tests pass, and do not delete old public entry points just to make the new layout
look cleaner.
