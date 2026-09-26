# Authoring pipelines

The primary replaceability proof is
`tests/fixtures/replacement-pipeline/pipeline.toml`. It uses `inspect`,
`transform`, and `verify` with its own skills and templates; the generic engine
does not change. Copy that fixture when learning the format, then use the
default pipeline for richer approval and repair examples.

Pipeline files use TOML so Python 3.11 can load them without a dependency. A
pipeline declares schema version, identity, start phase, terminal outcomes,
artifact naming, Git policy, and an ordered `[[phases]]` array. Every phase
names a canonical skill, inputs, output, mutation policy, validator, gates, and
transitions.

## Add, delete, reorder, or replace phases

To add a phase:

1. add `.agents/skills/<name>/SKILL.md` with portable frontmatter;
2. add any output template under the pipeline's directory;
3. add `[[phases]]` with a unique lowercase identifier;
4. route an existing transition to it and give it at least one transition;
5. make every symbolic input available on every incoming route;
6. regenerate adapters and run tests.

Delete a phase by removing all inbound transitions first, then its phase table,
skill, and unused template. Reordering table text alone does not change graph
behavior: change transition targets and, when necessary, `start`. The loader
rejects unreachable phases and unknown targets.

Replacing the whole workflow follows the same rules. The replacement fixture's
unrelated names and order are the contract test for this operation.

## Branches and bounded loops

Add one transition table per allowed outcome:

```toml
[[phases.transitions]]
outcome = "accepted"

[[phases.transitions]]
outcome = "rejected"
target = "transform"
max_traversals = 2
```

A transition without `target` must be listed in `terminal_outcomes`. A cycle
must be bounded by a positive `max_traversals` on the cyclic edge or a positive
`max_visits` on a phase that bounds the cycle. Limits count persisted visits or
edge traversals and block before creating an excess visit.

## Skills and templates

`skill = "inspect"` resolves to `.agents/skills/inspect/SKILL.md` at the
repository root. Canonical skill frontmatter is limited to portable Agent
Skills fields (`name`, `description`, `license`, `compatibility`, and optional
`metadata`). Keep vendor models, tool allowlists, and slash-command syntax in
generated harness surfaces, never canonical skills.

`output_template` is relative to the pipeline file. A Markdown validator can
declare `required_headings` and `heading_occurrence`; a JSON validator may use
the documented project-owned schema subset. Templates should contain every
required heading exactly once and meaningful placeholder content that a valid
artifact must replace.

## Approvals and stops

Declare stable kebab-case reason codes:

```toml
approval_conditions = ["external-side-effect", "material-scope-change"]
stop_conditions = ["insufficient-information"]
```

The phase skill explains when each code applies. It must call
`request-approval` or `block` rather than merely mentioning a concern in prose.
Changing or adding a reason changes the pipeline hash.

## Mutation policies

- `read-only` rejects every repository path change during the visit, including
  a second edit to a file that was dirty at visit start.
- `repository-write` records all changes but permits them.
- `allowlist` permits only paths matched by the phase's `allowlist` globs and
  rejects the rest.

CLI-owned `.specromancy/` files are outside repository mutation comparison.
None of these policies grants permission to delete, reset, stage, or commit
work; repository instructions still apply.

## Validation commands

Commands are arrays, never shell strings:

```toml
[[phases.commands]]
argv = ["python", "-m", "unittest", "discover"]
timeout_seconds = 300
required = true
```

They run in order from the repository root. A required failure prevents phase
completion. Use explicit executables and arguments; shell operators, pipes, and
redirections are not interpreted.

## Regeneration and active runs

After changing `AGENTS.md`, a canonical skill, the pipeline, or CLI help
metadata, run:

```bash
bin/specromancy adapters generate
bin/specromancy adapters generate --check
python -m unittest discover
```

A run stores its pipeline hash. Any pipeline change causes `resume`, `phase`,
and transition commands to reject that run with `pipeline-hash-mismatch`.
Approval records also become stale. The POC deliberately has no active-run
migration: finish the old run before editing its pipeline, restore the exact
old configuration to resume it, or initialize a new run under the new hash.
Never edit `run.json` to force compatibility.
