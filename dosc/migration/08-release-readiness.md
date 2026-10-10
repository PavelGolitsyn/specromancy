# Stage 08 — Migration rehearsal and release readiness

Status: planned. Dependency: [Stage 07](07-distribution-verification.md).
Index: [migration plan](README.md).

## Objective

Demonstrate the complete transition from checkout-oriented usage to an installed
dependency, finalize the migration instructions, and prepare verified local
release artifacts. Publishing is a separate action.

## Intended files

Finalize the existing installation/migration guides, current public contracts,
README, test instructions, and version metadata. Add a release-readiness report
under `dosc/migration/evidence/` with artifact hashes and verification results.
Change implementation files only to resolve concrete gate failures; repeat the
affected checks and full suite after such changes.

## Work

1. Reconcile the Stage 1 matrix against the final tree. Confirm distribution,
   import package, CLI, source path, schemas, configuration roots, and generated
   output names match the selected design. Verify no unrelated source was moved.
2. Run a controlled upgrade rehearsal in temporary consumer projects. Initialize
   representative states using the original baseline checkout/runtime or replay
   the independent original fixtures. Switch only the engine installation while
   leaving consumer configuration, artifacts, and run paths unchanged.
3. Cover pending, active, awaiting approval, approved-before-advancement, paused,
   terminal, and recoverable interrupted states. Confirm normal transitions and
   any legitimate recovery append; do not require byte identity after an operation
   whose existing contract deliberately changes state.
4. Distinguish an engine-only upgrade from editing skills, templates, or graphs.
   The former must preserve compatible state; the latter may intentionally
   trigger provenance or approval invalidation. Test that editing an approved
   artifact still invalidates approval and never bypass that behavior for migration.
5. Rehearse adapter upgrade separately from run compatibility. Review canonical
   input changes, regenerate through ownership checks, and confirm unrelated
   customer files remain unchanged. A user-edited managed file must retain its
   existing conflict treatment.
6. Document the user migration sequence: use an isolated or controlled environment,
   install the verified package version, update Python imports/module commands,
   ensure the harness can find `specromancy`, review canonical skill changes,
   regenerate owned adapters, and inspect persisted status before continuing.
   Keep `.specromancy/` in place and never edit `run.json` or `events.jsonl`.
7. Document `bin/specromancy` as producer-checkout convenience only. Consumer
   onboarding must not copy engine source or launcher code into each project.
   Keep the direct dependency and installed CLI routes equally clear.
8. Re-run the complete Stage 7 matrix with the final version and toolchain. Record
   exact artifact SHA-256, build origin commit, Python versions, commands, exit
   codes, counts, generated drift status, and any limitations. A skip is not a pass.
9. Review archives for stale namespace files, unintended workflows/skills, private
   data, caches, environments, and `game-of-life/`. Review diffs to ensure only
   the planned source/package/test/docs changes and reproducible adapters changed.
10. Confirm prospective distribution/repository naming is documented without
    claiming remote ownership. Registry account setup, remote repository rename,
    tags, release publication, and credential handling remain outside the local
    migration. Do not add automatic uploads to the test workflow.

## Final acceptance checklist

- [ ] Product distribution is `specromancy-engine`.
- [ ] Installable source is under `src/specromancy_engine/`.
- [ ] `import specromancy_engine`, its public facades, module invocation, and
  installed `specromancy` CLI work from outside the source checkout.
- [ ] The intentional old-import break is explicit and has a chosen version.
- [ ] Runtime dependencies remain empty and Python 3.11 verification passes.
- [ ] A separate release-documentation consumer completes its custom pipeline.
- [ ] Consumer workflows and canonical skills remain outside engine source.
- [ ] All schemas are available in direct and sdist-rebuilt wheel installations.
- [ ] State compatibility, recovery, immutable artifacts, read-only phases, and
  approval invalidation pass through installed-package execution.
- [ ] Generated adapters are deterministic, current, and ownership-safe.
- [ ] Full tests pass; public contracts and developer setup are current.
- [ ] No live run data, unrelated project files, or historical captures were rewritten.
- [ ] Local release artifacts and their verification evidence are ready for review.

## Rollback and support guidance

Retain the prior verified engine version and original configuration history.
Before changing an actual deployment, stop overlapping commands and preserve a
normal filesystem backup of the consumer's run directory and configuration.
Do not include private run contents in public migration reports.

For an engine-only upgrade failure, select the prior verified installation in
the consumer environment and inspect status through its CLI. Compatibility with
newly written state must be established by rehearsal before claiming downgrade
safety. If a new renderer or configuration has been adopted, account for those
separate changes rather than assuming a package downgrade restores everything.

Do not roll back by deleting `.specromancy/`, rewriting audit events, weakening
ownership checks, or resetting repository work. Any future format migration
requires a separate design and versioned contract, outside this packaging plan.

## Completion report

Summarize the final names, installed consumer result, compatibility limits,
test/build evidence, and local artifact locations. Mark stages complete only
when their gates are satisfied. If a gate remains unresolved, name the concrete
failure and keep release readiness incomplete; do not publish to discover whether
the migration works.
