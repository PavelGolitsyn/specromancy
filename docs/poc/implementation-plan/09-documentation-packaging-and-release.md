# Stage 9: Documentation, Packaging, and POC Release

## Objective

Turn the validated implementation into a reproducible POC release that users of each target harness can install, understand, exercise, and remove safely.

## Dependencies

- Stages 0 through 8 complete.

## Deliverables

- Complete root `README.md`
- `docs/getting-started.md`
- `docs/concepts.md`
- `docs/artifacts.md`
- `docs/cli.md`
- `docs/harnesses/codex.md`
- `docs/harnesses/claude-code.md`
- `docs/harnesses/github-copilot.md`
- `docs/harnesses/hermes.md`
- `docs/harnesses/opencode.md`
- `docs/troubleshooting.md`
- `docs/security.md`
- `examples/minimal/`
- `CHANGELOG.md`
- Release checklist and versioning policy
- Built source distribution and wheel

## Documentation structure

### Getting started

Provide a path that takes less than fifteen minutes:

1. Verify prerequisites.
2. Install the package in an isolated environment.
3. Run `specromancy doctor`.
4. Generate and verify adapters.
5. Initialize a sample run.
6. Invoke the pipeline from the user's selected harness.
7. Approve the plan.
8. Inspect status and artifacts.
9. Complete or cancel the run.

Use one minimal example consistently across all harness guides.

### Concepts

Explain:

- canonical instructions versus skills versus commands;
- why artifacts, not chats, carry state;
- the state machine and approval gate;
- phase permissions;
- review independence and its limits;
- repair-loop bounds;
- generated adapter ownership;
- trust implications of repository skills.

### CLI reference

For every command, document:

- syntax and arguments;
- allowed states;
- files read and written;
- exit codes;
- text and JSON examples;
- idempotency behavior;
- recovery guidance.

Generate repetitive command listings from parser metadata when practical, while keeping conceptual explanations hand-authored.

### Harness guides

Each guide includes:

- tested version and date;
- discovery files used;
- setup or trust step;
- explicit invocation examples for pipeline and individual phases;
- permission/isolation notes;
- resume workflow;
- known limitations;
- troubleshooting checklist.

Avoid claiming uniform capabilities where harnesses differ.

## Packaging

1. Include contracts, templates, and adapter resources in both sdist and wheel.
2. Exclude runtime `.specromancy/runs`, local caches, and test outputs.
3. Verify install and execution from outside the source checkout.
4. Produce reproducible adapter output from the built wheel.
5. Confirm the package license covers code, templates, and canonical skills.
6. Add package metadata describing the POC status and Python support.

The POC release may remain unpublished. A locally built wheel plus checksums is sufficient to prove packaging.

## Versioning and compatibility

Use semantic versioning for the package and independent integer versions for:

- pipeline contract;
- run manifest schema;
- artifact schemas;
- adapter manifest.

For POC `0.x` releases:

- document breaking changes explicitly;
- reject unsupported future schema versions;
- provide read-only inspection for older known run versions where feasible;
- do not silently migrate artifacts.

## Example project

The minimal example contains:

- a tiny application with tests;
- a realistic change request;
- expected research and plan artifacts;
- an intentionally flawed implementation branch or patch fixture;
- expected review findings;
- commands for both the pass path and repair path.

Keep generated run outputs out of the main example unless they serve as named golden fixtures.

## Release checklist

1. Confirm working tree and generated adapters are clean.
2. Run all static, unit, contract, integration, security, and packaging tests.
3. Run `specromancy doctor --format json` from an installed wheel.
4. Complete the minimal example's pass and repair flows.
5. Perform or review one smoke test per harness.
6. Verify all documentation commands against the release candidate.
7. Inspect distributions for unintended files or secrets.
8. Generate SHA-256 checksums.
9. Update changelog, compatibility table, and known limitations.
10. Tag the release only after artifacts and documentation agree on the version.

## Implementation tasks

1. Write the getting-started guide before final CLI polish to expose usability gaps.
2. Complete conceptual, artifact, CLI, and troubleshooting documentation.
3. Produce and validate all five harness guides.
4. Build the minimal example and golden fixtures.
5. Configure package data and build outputs.
6. Add installed-wheel and distribution-content tests.
7. Define version constants and compatibility checks.
8. Create the changelog and release checklist.
9. Run a clean-room installation in a temporary directory.
10. Record POC limitations and post-POC priorities.

## Exit criteria

- A new user can finish the minimal workflow using only published documentation.
- Wheel and source distribution contain every required runtime resource.
- All example commands have been executed against the release candidate.
- The five harness guides use the same canonical concepts and state model.
- Uninstallation or adapter cleanup does not remove user-authored source files or run artifacts unexpectedly.
- The release notes clearly label the project as a POC and list known limitations.

## Post-POC candidates

Do not implement these during this stage; capture them for prioritization:

- optional noninteractive runners for specific harness CLIs;
- signed skill and adapter bundles;
- remote artifact stores and multi-repository runs;
- richer JSON Schema validation through an optional dependency;
- web interface and run visualization;
- pull-request and CI service integrations;
- policy packs for regulated environments;
- benchmark suite spanning multiple models per harness.

## Risks and mitigations

- **Documentation drift:** derive command syntax from parser metadata and test code blocks where possible.
- **Packaging differs from checkout:** make installed-wheel tests release-blocking.
- **Overstated compatibility:** publish tested versions, dates, and explicit limitations.
- **POC scope creep:** place enhancements in post-POC candidates rather than extending the release gate.

