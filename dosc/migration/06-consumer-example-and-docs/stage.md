# Stage 06 — Consumer example and documentation

Status: planned. Dependency: [Stage 05](../05-portable-skills-and-adapters/stage.md).
Next: [Stage 07](../07-distribution-verification/stage.md).
Index: [migration plan](../README.md).

## Objective

Provide an executable example of the intended product: another project installs
`specromancy-engine`, supplies release-documentation configuration and skills,
and uses the engine without modifying its source.

## Intended files

Create the following example-owned files:

```text
examples/release-documentation/
├── README.md
├── AGENTS.md
├── .gitignore
├── sample-changes.md
├── workflow/
│   ├── pipelines.toml
│   ├── pipelines/release-documentation.toml
│   └── templates/
│       ├── release-notes.md
│       └── review.md
└── .agents/skills/
    ├── pipeline/SKILL.md
    ├── draft-release-notes/SKILL.md
    └── review-release-notes/SKILL.md
```

Update `README.md`, `docs/README.md`, `docs/reference/{architecture,contracts,cli}.md`,
`docs/guides/{authoring-pipelines,harnesses}.md`, `workflow/README.md`, and
`tests/README.md`. Add `docs/guides/installation.md`, a migration guide, and
example lifecycle coverage under `tests/engine/contract/` or `tests/packaging/`.

## Work

1. Build a minimal two-phase pipeline using the existing schema. Register
   `release-documentation` explicitly; configure `draft-release-notes` followed
   by `review-release-notes`, ending in an outcome such as `approved` or `blocked`.
   If the example includes a repair loop, bound it through existing edge limits.
2. Make release-specific inputs, headings, outcomes, policies, and procedures
   entirely example-owned. Use sample change data supplied as request content
   through existing `--description-file` or other supported request behavior;
   do not invent an unsupported arbitrary-file input selector.
3. Keep drafted notes as engine-owned run artifacts so the example can complete
   with read-only repository phases. Explicitly copying an approved result into
   a project's release docs is a user action outside this minimal lifecycle.
   Explain that read-only phases can produce their designated run output.
4. Provide canonical skills with portable frontmatter. The generic pipeline
   procedure must agree with the canonical orchestrator semantics from Stage 5.
   Keep any repeated example copy covered by a consistency check or documented
   maintenance rule; do not introduce engine-owned workflow policy.
5. Include `AGENTS.md` because adapter generation reads it. Include `.gitignore`
   rules for `.specromancy/`, local environments, and generated development
   outputs relevant to the example. Do not commit run artifacts.
6. Document two consumer installation routes: installing the engine in a project
   environment for CLI use, and adding `specromancy-engine` to an existing Python
   project's dependency metadata for imports and CLI use. Use a concrete tested
   local wheel before publication; label registry installation as available
   only after a release exists. Do not claim an unpublished package is on PyPI.
7. Document explicit creation/copying of workflow and skill files, preserving
   existing user instructions. Installation must never silently overwrite a
   consumer's `AGENTS.md`, skills, registry, or harness files. Explain how to
   resolve adapter ownership conflicts using the documented ownership model.
8. Walk through help, registry selection, adapter generation/check, init, status,
   phase work, validation, and completion. Capture RUN_ID and output paths from
   responses rather than hardcoding timestamps or guessing artifact names.
   Explain actionable nonzero exits, including code 8 for agent work, so a shell
   walkthrough does not treat normal continuation as a crash.
9. State the host model clearly: the engine emits actions for an agent/harness
   and verifies their results; it does not launch an LLM, supply credentials,
   generate prose itself, or publish release notes.
10. Provide a Python usage example using the actual public API. Describe the
    dependency name/import name distinction and the `specromancy` executable.
    Separate consumer instructions from contributor editable-install setup.
11. Update the repository map and import migration guide. Keep the producer's
    `workflow/` and `.agents/skills/` in place; classify them as this repository's
    own configured workflow, not automatically installed customer defaults.

## Verification

Copy the example, including hidden skill files, into a separate temporary Git
repository; use explicit `--root` where needed so the parent producer Git root
cannot be selected accidentally. Install only the built wheel in its environment.

Execute the documented walkthrough. In automated checks, act as a deterministic
agent by writing suitable content only to the emitted artifact paths and then
calling validation. Confirm terminal outcome, immutable completed outputs, and
unchanged sample/project files. Validate actual runtime results, not just TOML
syntax. Test missing registry, missing orchestrator, and invalid pipeline IDs.

Run applicable example, architecture, and shipped configuration tests, followed
by `python -m unittest discover` and `specromancy adapters generate --check`.
Review documentation links and executable command spelling. Keep existing
test-owned workflow fixtures independent of the new user-facing example.

## Acceptance criteria

- [ ] A consumer without engine source completes the release-documentation flow.
- [ ] No example phase names or policies enter runtime code.
- [ ] Both CLI-only and Python dependency installation routes are documented.
- [ ] All needed canonical consumer files are supplied or explicitly described.
- [ ] Installation versus configuration, agent work, and output handling are clear.
- [ ] Existing workflows, fixtures, full tests, and adapter checks remain valid.

## Recovery and handoff

Fix example configuration or documentation rather than hardcoding its behavior
into the engine. Keep examples outside the wheel; make them available in the
repository and proposed source distribution. Stage 7 verifies that distribution
artifacts and CI preserve this consumer experience.
