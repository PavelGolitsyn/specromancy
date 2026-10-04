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
| Pipeline registrations | `workflow/pipelines.toml` |
| Graph, policies, gates, and validators | `workflow/pipelines/<id>.toml` |
| State transitions and persistence | `specromancy/` Python package |
| Current run state | `.specromancy/runs/<run-id>/run.json` and artifacts |
| Audit history | `.specromancy/runs/<run-id>/events.jsonl` |
| Harness discovery surfaces | generated adapters recorded in `adapters/manifest.json` |

The editable workflow surface is intentionally outside the Python package:
start in `workflow/` for the graph and templates, then use `.agents/skills/`
for phase procedures or `AGENTS.md` for always-on constraints. Files under
`specromancy/` implement the generic runtime and are not changed to add,
remove, reorder, or tune phases.

The engine is generic. Phase identifiers such as the configured pipeline's names
belong only in configuration, skills, templates, tests, and examples.

The CLI loads the mandatory registry and requires a registered ID for init.
Existing runs resolve their graph from persisted provenance, so unrelated graphs
and registry ordering do not change their execution. Graph loading, transitions
and run storage remain generic. Adapter generation validates every registered
graph and projects each registration into a launch skill delegating to the
canonical orchestrator.

## Configuration dependencies

`specromancy.config` remains the public configuration entry point. Its records
are the same frozen class objects defined in `config_models`; configuration
diagnostics and the omitted-value sentinel live in `config_errors`.

```text
config facade -> config_loader -> config_models / config_errors
                              -> graph
                              -> config_serialization -> config_models
                              -> schema_validation

validation -> config_models / schema_validation
runtime consumers -> config_models
registry -> config_loader / config_models / config_errors
```

The loader owns TOML parsing, field rejection order, repository discovery, and
resource containment. Graph analysis remains in `graph`, with diagnostic
callbacks supplied by the loader. Models, diagnostics, canonical serialization,
and schema validation do not import the loader or public facade. Artifact
validation owns artifact reads, Markdown/file checks, and `ValidationFailure`;
it delegates JSON schema algorithms to `schema_validation` and re-exports the
existing schema helpers and `SchemaDefinitionError`.

`config_serialization` preserves the canonical pipeline document and its exact
JSON encoding, including ASCII escaping, transition sorting, and omission of
false pause defaults. This encoding is deliberately separate from the generic
`hashing.canonical_json_bytes` UTF-8 encoding used for run data. Registry
serialization remains independent. Loading does not cache graph or dependency
contents between commands. These internal boundaries add no public APIs or
stored-data migrations; existing configuration imports and hashes are retained.

## State and visit model

A run owns an ordered list of visits. Each visit is one attempt at one
configured phase and has a distinct ordinal, resolved inputs, output path,
mutation baseline, validation results, and outcome. A loop creates new visits;
it never reuses or rewrites an earlier completed visit.

```text
awaiting-agent -> active -> awaiting-agent -> ... -> completed
                      |             ^
                      |             |
                      +-> paused ---+
                      |             |
                      v             |
              awaiting-approval ----+
                      |
                      +-------------------------> blocked
```

`init` prepares the first pending visit. `phase` captures its repository
baseline and activates it. `validate`, `request-approval`, `approve`, or
`block` records the next transition. Visit and edge counters mechanically stop
configured cycles before an unbounded successor can be created.

A transition configured with `pause = true` completes its source and prepares
its pending successor in the same atomic mutation, but records the run as
`paused`. `resume` releases that checkpoint to `awaiting-agent`; it does not
activate the successor. Direct phase and run commands cannot bypass the pause.

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

`run_store` remains the compatibility entry point for `RunStore`, identity
helpers, constants, exceptions, and aliases. Internally, `run_records` defines
dictionary annotations and pure selectors, `run_identity` owns injected
clock/random helpers, `run_errors` defines shared exceptions, and
`run_validation` checks persisted fields without filesystem mutation or
engine/CLI dependencies. The store delegates its existing validation methods
and retains locking, serialization, audit consistency, recovery, and defensive
copies. Engine, action, status, and approval code share the record vocabulary.

Selectors borrow records from their arguments. Current-visit presentation
lookups tolerate an absent ordinal and can return a completed visit; the
store's explicit visit lookup still raises when missing. Status selects the
latest pending approval across the run, while engine approval decisions and
next-command selection filter by visit. Approval invalidation and idempotency
retain their separate matching rules.

Annotations do not validate or fill missing fields. The existing runtime checks
and published run/event schemas differ in several places; the
[Stage 03 comparison](../refactoring/03-persisted-records.md#schema-comparison-and-deferred-validation-issues)
records these differences and follow-up candidates. Artifact schema validation
is a limited subset and cannot replace cross-record run checks. These internal
modules add no public API or stored-data migration.

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

## Transition and mutation safety

Read-only, repository-write, and allowlist policies compare content-level Git
snapshots taken at visit start and validation. This catches edits to files that
were already dirty. `.git/` and CLI-owned `.specromancy/` data are excluded.
The CLI never deletes, resets, stages, or commits repository work.

Validation commands are trusted pipeline configuration expressed as argument
arrays. They run without a shell. Full output stays in ignored run storage;
bounded, secret-redacted summaries are recorded in the manifest.

## Canonical and generated content

`AGENTS.md`, `workflow/pipelines.toml`, `workflow/pipelines/`, canonical
`.agents/skills/` procedures and `workflow/templates/` are editable sources.
Generated `.agents/skills/specromancy-*/` are manifest-owned launch skills,
excluded from canonical source hashing. Claude Code, Copilot, and OpenCode
adapters are deterministic projections. Codex and Hermes consume canonical
files directly and discover generated per-pipeline launch skills natively. Generated files contain provenance and invocation glue only;
they contain no phase graph, approval policy, or unique workflow procedure.

## POC limitations

The POC has no harness launcher, remote store, database, daemon, authenticated
approvals, active-run migration, parallel joins, YAML loader, or arbitrary
JSON-Schema implementation. Validation commands run with the invoking user's
normal permissions. Run locking is local to one filesystem and stale locks
require a human to verify the owner has exited before removal.
