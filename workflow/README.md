# Workflow customization

This directory is the primary customization surface for Specromancy. Configure
as many pipelines as needed without editing the generic engine in `specromancy/`.
Every new run explicitly chooses a registered pipeline; there is no default.

## Editable workflow sources

| What to customize | Canonical path |
| --- | --- |
| Pipeline registrations | `workflow/pipelines.toml` (mandatory, at least one entry) |
| Graph, gates, policies, and validation | `workflow/pipelines/<id>.toml` |
| Shared artifact templates | `workflow/templates/` |
| Shared phase procedures and orchestration | `.agents/skills/<skill>/SKILL.md` |
| Repository-wide agent constraints | `AGENTS.md` |

The registry uses this structure:

```toml
schema_version = 1

[[pipelines]]
id = "implementation"
path = "pipelines/implementation.toml"

# Add this registration after creating its pipeline file:
# [[pipelines]]
# id = "requirements-gathering"
# path = "pipelines/requirements-gathering.toml"
```

IDs use lowercase words separated by single hyphens and must match the `id` in
the referenced graph. IDs and resolved graph paths are unique. Registry paths
are relative to `workflow/`, stay under `pipelines/`, and end in `.toml`.
Path segments use letters, numbers, underscores or hyphens. Absolute paths,
parent traversal and symlinks escaping that directory are rejected. Unregistered
files never create pipeline launch skills and cannot initialize new runs.

## Add, edit, or remove pipelines

To add a pipeline, copy an existing graph into `workflow/pipelines/<id>.toml`,
set its `id`, customize its phases and transitions, and add its registration.
Reuse canonical skills by naming them in `skill`. Use `../templates/<name>.md`
for a shared output template, or a path relative to the graph for a private one.
References must resolve inside the repository. Different pipelines may use the
same phase names, skills and templates.

Edit a registered graph or its referenced canonical files directly. To remove
a pipeline, remove its registration while keeping at least one entry, then
regenerate adapters. This removes unchanged manifest-owned launch skills.
Modified stale or unowned files are preserved with a conflict diagnostic.
Keep the original graph and consumed skills/templates until its active runs
finish: existing runs resolve their original provenance even after a registration
is removed. Moving or changing that graph does not migrate an existing run.

After customization, run:

```sh
bin/specromancy adapters generate
bin/specromancy adapters generate --check
python3 -m unittest discover
```

Generation validates every registered graph. CLI execution loads the selected
graph, so unrelated graph edits do not change another pipeline's run semantics.
The mandatory registry itself must remain valid for workflow commands.

## Start a run

```sh
bin/specromancy init "describe the requested change" --pipeline implementation
```

Alternatively, invoke the generated `specromancy-implementation` skill. The
generator creates `specromancy-<id>` for every registration, delegating to the
canonical pipeline orchestrator. Existing-run commands need only `RUN_ID`.

Do not edit generated `.agents/skills/specromancy-*/`, `.claude/`,
`.github/copilot-instructions.md`, `.github/prompts/`, or `.opencode/commands/`.
Their ownership and hashes are recorded in `adapters/manifest.json`.
The `specromancy-` skill prefix is reserved for generated launch skills; all
other `.agents/skills/` procedures remain editable canonical sources.

See [Pipeline authoring](../docs/poc-v3/authoring-pipelines.md) for graph rules
and active-run safety.
