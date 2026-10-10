# Stage 05 — Portable skills and adapters

Status: planned. Dependency: [Stage 04](../04-consumer-roots-and-resources/stage.md).
Next: [Stage 06](../06-consumer-example-and-docs/stage.md).
Index: [migration plan](../README.md).

## Objective

Make every current generated instruction executable in a consumer project that
has installed the engine but contains no `bin/specromancy` or engine source.
Preserve canonical procedures and manifest-based ownership.

## Intended files

- `src/specromancy_engine/_adapters/adapter_contracts.py` and
  `adapter_rendering.py`; inspect `adapter_sources.py` and `adapter_ownership.py`.
- Canonical `.agents/skills/{pipeline,research,plan,implement,review}/SKILL.md`.
- Current test-owned skills in `tests/engine/fixtures/`, excluding preserved
  historical compatibility source records unless deliberately versioned.
- `tests/engine/unit/test_adapters.py`, `test_multi_pipeline_adapters.py`,
  `test_skills.py`, contract `test_adapter_drift.py`, `test_compatibility.py`, and
  shipped configuration skill/adapter tests.
- Versioned adapter expectations alongside the original compatibility capture.
- `adapters/manifest.json` and every generated path changed by regeneration.
- Current harness guides and public contracts.

## Work

1. Change `REGENERATION_COMMAND` to `specromancy adapters generate`. Render
   launch skills and harness wrappers with `specromancy`, retaining argument
   order, quoting, harness placeholder conventions, and `--json` behavior.
2. Keep the installed executable identity consistent with `actions.py` and
   `status.py`; these already use `specromancy`. Verify execution context for
   `next_command` and validation argv rather than rewriting them unnecessarily.
3. Update canonical procedure instructions to use the installed command.
   Document that harnesses must inherit an environment with that command on
   `PATH`; terminal activation alone does not change an already-running GUI
   harness environment. Keep `python -m specromancy_engine` as a documented
   diagnostic alternative, not a second set of workflow semantics.
4. Keep `.agents/skills/pipeline/SKILL.md` project-owned and required by adapter
   generation. Installation does not create it. Onboarding must provide a
   reusable generic procedure for explicit copying, with no example phase names.
5. Preserve manifest schema version 1 if its shape and semantics are unchanged.
   Increment `GENERATOR_VERSION` for the intentional rendering change and make
   provenance comments derive their version consistently instead of retaining
   the current literal `v1` text. Keep generator name `specromancy` unless the
   Stage 1 matrix explicitly selects another identity.
6. Preserve old `adapters.json` as historical evidence. Add a versioned expected
   rendering for the new generator and update comparisons intentionally. Continue
   exact comparison of unchanged canonical/state/response/diagnostic records.
   Add an upgrade test using the old manifest and its old generated files as
   inputs to the new generator. Do not relabel the old bytes as new expectations.
7. Update command-extraction tests that currently match only
   `bin/specromancy\s+...`. Assert the new command spelling, known CLI commands,
   and placeholder correctness so changing the regex cannot make checks vacuous.
8. Regenerate all repository adapters from canonical sources. Never manually
   edit `.claude`, `.github` instruction/prompt files, `.opencode` command files,
   or generated `.agents/skills/specromancy-*` content.
9. Exercise generation into a temporary consumer with no producer launcher.
   Retain existing refusal to overwrite unowned files. Do not add a `--force`
   path, project scaffolder, or permission bypass to simplify onboarding.

## Verification

```sh
python -m unittest tests.engine.unit.test_adapters tests.engine.unit.test_multi_pipeline_adapters
python -m unittest tests.engine.contract.test_adapter_drift tests.engine.contract.test_compatibility
python -m unittest discover -s tests/shipped_configuration -t .
specromancy adapters generate
specromancy adapters generate --check
python -m unittest discover
```

Run generation only after canonical sources are finalized for the stage; if
shipped tests run before regeneration, their drift failure is expected and must
be resolved before the final full-suite gate. Record final results, not only the
pre-regeneration run.

Generate twice and compare output bytes and manifest hashes. Test `--check`
with clean output, missing output, edited output, and no manifest; it must never
write. Test owned upgrades, edited owned files, unrelated user files, stale-file
removal, and unowned-path collisions through existing ownership rules. The
generator's per-file atomic writes and manifest-last behavior must not be
misrepresented as a multi-file transaction.

In a wheel-only consumer, substitute representative arguments into each harness
wrapper and verify the resulting argv against the CLI. Actual hosted harness
behavior remains separate from deterministic adapter contract coverage.

## Acceptance criteria

- [ ] Generated commands run without a producer launcher or source checkout.
- [ ] Canonical skills and generated mirrors agree and contain no unique policy.
- [ ] New rendering is versioned and original compatibility evidence is retained.
- [ ] Old-owned-adapter upgrade and collision protections pass.
- [ ] Repeat generation is deterministic; check mode is read-only.
- [ ] Focused tests, full suite, and final adapter check pass.

## Recovery and handoff

If a canonical edit changes active-run provenance, preserve the resulting stop
or invalidation; do not rewrite recorded hashes. To back out rendering changes,
restore the stage's canonical/generator changes and regenerate through the
verified older generator against its ownership manifest. Preserve user edits
and investigate conflicts instead of deleting them. Stage 6 documents consumer
setup using the now-portable instructions.
