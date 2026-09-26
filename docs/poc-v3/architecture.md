# Architecture

Specromancy is a small, dependency-free state-machine CLI. An agent authors
artifacts and repository changes; the CLI resolves inputs, enforces gates,
validates outputs, and persists every transition. Runtime correctness comes
from files under `.specromancy/`, never from conversation history.

## Responsibility split

| Concern | Authoritative source |
| --- | --- |
| Always-on repository constraints | `AGENTS.md` |
| Phase procedure | `.agents/skills/<skill>/SKILL.md` |
| Graph, policies, gates, and validators | `specromancy/pipeline.toml` |
| State transitions and persistence | `specromancy/` Python package |
| Current run state | `.specromancy/runs/<run-id>/run.json` and artifacts |
| Audit history | `.specromancy/runs/<run-id>/events.jsonl` |
| Harness discovery surfaces | generated adapters recorded in `adapters/manifest.json` |

The engine is generic. Phase identifiers such as the default pipeline's names
belong only in configuration, skills, templates, tests, and examples.

## State and visit model

A run owns an ordered list of visits. Each visit is one attempt at one
configured phase and has a distinct ordinal, resolved inputs, output path,
mutation baseline, validation results, and outcome. A loop creates new visits;
it never reuses or rewrites an earlier completed visit.

```text
awaiting-agent -> active -> awaiting-agent -> ... -> completed
                      |             ^
                      v             |
              awaiting-approval ----+
                      |
                      +-------------------------> blocked
```

`init` prepares the first pending visit. `phase` captures its repository
baseline and activates it. `validate`, `request-approval`, `approve`, or
`block` records the next transition. Visit and edge counters mechanically stop
configured cycles before an unbounded successor can be created.

## Action packet boundary

The action packet is the complete handoff from CLI to harness. It contains the
resolved skill, literal input artifact records, output and template paths,
mutation policy, completion criteria, validation contract, approval and stop
codes, configured outcomes, and the exact final validation command. A harness
may decide how to invoke an agent, but it must not infer or replace those
fields.

The CLI deliberately does not launch Codex, Claude Code, Copilot, OpenCode, or
Hermes. Launch APIs, trust models, permissions, and interactive behavior differ
between harnesses. Keeping that boundary outside the engine makes the persisted
run and command contract portable and testable.

## Persistence and provenance

One run has this shape:

```text
.specromancy/runs/20260925T143001Z-a1b2c3d4/
├── run.json
├── events.jsonl
├── artifacts/
│   ├── 000-request.md
│   ├── 001-research.md
│   └── 002-plan.md
└── commands/
    ├── 003-01-stdout.txt
    └── 003-01-stderr.txt
```

`run.json` is the validated current snapshot. Every mutation increments its
revision, atomically replaces the manifest, and appends an event containing the
manifest hash. If a process stops after replacement and before event append,
the next load adds a recovery event. Other disagreement is reported as corrupt
state rather than guessed back into shape.

Request and completed output artifacts are hash-bound. Visits also record the
hashes of their skill and template. Approval binds the run, visit, selected
outcome, pipeline hash, and artifact hash; changing the artifact or pipeline
makes the approval stale.

When a phase declares `approval_required = true`, successful validation creates
a pending `human-review` record instead of applying the transition. The
validated outcome remains uncommitted until `approve` rechecks the bound hashes
and records the transition. This gate is engine-enforced and cannot be bypassed
by calling `validate` again.

## Transition and mutation safety

Read-only, repository-write, and allowlist policies compare content-level Git
snapshots taken at visit start and validation. This catches edits to files that
were already dirty. `.git/` and CLI-owned `.specromancy/` data are excluded.
The CLI never deletes, resets, stages, or commits repository work.

Validation commands are trusted pipeline configuration expressed as argument
arrays. They run without a shell. Full output stays in ignored run storage;
bounded, secret-redacted summaries are recorded in the manifest.

## Canonical and generated content

`AGENTS.md`, `specromancy/pipeline.toml`, `.agents/skills/`, and
`specromancy/templates/` are canonical. Claude Code, Copilot, and OpenCode
adapters are deterministic projections. Codex and Hermes consume canonical
files directly. Generated files contain provenance and invocation glue only;
they contain no phase graph, approval policy, or unique workflow procedure.

## POC limitations

The POC has no harness launcher, remote store, database, daemon, authenticated
approvals, active-run migration, parallel joins, YAML loader, or arbitrary
JSON-Schema implementation. Validation commands run with the invoking user's
normal permissions. Run locking is local to one filesystem and stale locks
require a human to verify the owner has exited before removal.
