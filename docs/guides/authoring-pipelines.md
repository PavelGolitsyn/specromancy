# Authoring pipelines

Start with the [release-documentation consumer](../../examples/release-documentation/README.md)
and [installation guide](installation.md). The example supplies a registry,
two read-only phases, canonical skills, templates, and a complete walkthrough.
The producer's implementation pipeline provides richer approval and repair
examples. Test-owned replacement fixtures independently verify replaceability;
they are not the consumer onboarding template.

Register each graph in mandatory `workflow/pipelines.toml`, with a unique ID
and a path under `workflow/pipelines/`. There is no default; use
`specromancy init DESCRIPTION --pipeline ID`. See
[Workflow customization](../../workflow/README.md) for add/edit/remove steps.

With the package installed in your environment, use `specromancy init DESCRIPTION
--pipeline ID` from the consumer root or a nested directory. Discovery recognizes
both `.git` directories and worktree marker files. From an unrelated directory,
use `specromancy --root /absolute/path/to/consumer init DESCRIPTION --pipeline ID`.
A non-Git consumer needs both `--root` and `allow_non_git = true` in its graph.
Installation supplies the engine and its four published schemas; author the
registry, graph, skills, templates, and validator schemas in the consumer project.
Nothing is implicitly loaded from the engine's source checkout or home directory.

Adapter generation also requires the project-owned generic
`.agents/skills/pipeline/SKILL.md`. Explicitly copy the
[reusable procedure](../../.agents/skills/pipeline/SKILL.md) to that path in the
consumer; review existing content before replacing it. Installation does not
create it. The procedure resolves phases from persisted CLI packets and needs
no example phase names. See [Harness usage](harnesses.md) for command environment
setup, including GUI harnesses.

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

Set `pause = true` on a nonterminal transition to create a durable checkpoint:

```toml
[[phases.transitions]]
outcome = "validated"
target = "implement"
pause = true
```

The source visit completes and the target visit is prepared atomically, but the
run remains `paused` until `specromancy resume RUN_ID` releases it. Pauses are
independent from approvals and are rejected on terminal transitions. Omitting
`pause`, or setting it to `false`, preserves ordinary transition behavior and
the canonical hash of an otherwise unchanged version-1 pipeline.

## Skills and templates

`skill = "inspect"` resolves to `.agents/skills/inspect/SKILL.md` at the
repository root. Canonical skill frontmatter is limited to portable Agent
Skills fields (`name`, `description`, `license`, `compatibility`, and optional
`metadata`). Keep vendor models, tool allowlists, and slash-command syntax in
generated harness surfaces, never canonical skills.

`output_template` is relative to the pipeline file. `../templates/result.md`
can reference shared `workflow/templates/`; multiple graphs may use the same
canonical skill or template. The resolved file must remain inside the repository.
The `.agents/skills/specromancy-*` namespace holds generated launch skills and
is not a phase-procedure customization surface. A Markdown validator can
declare `required_headings` and `heading_occurrence`; a JSON validator may use
the documented project-owned schema subset. Templates should contain every
required heading exactly once and meaningful placeholder content that a valid
artifact must replace.

JSON validator `path` (or `schema`) resolves relative to the pipeline file and
must stay inside the consumer root, including after symlink resolution. The
`load_json_schema(path)` API still reads these project-owned files and rejects
unsupported keywords. The four published engine schemas are a separate package
resource contract, not artifact validators for that subset; see
[installed resources](../reference/contracts.md#installed-resources-and-consumer-roots).

## Embed the installed engine

Use an explicit absolute consumer root so the caller's working directory does
not select the project. Given a registered `shared` pipeline, this initializes a
run and reads its durable status through the public facades:

```python
from pathlib import Path
from specromancy_engine import Engine, RunStore, load_registry

root = Path("/absolute/path/to/consumer").resolve()
pipeline = load_registry(root).load("shared")
store = RunStore(root)
engine = Engine(pipeline, store)
response = engine.initialize("Record the consumer result.")
run_id = response["action"]["run_id"]
status = engine.status(run_id)
manifest = store.load(run_id)
```

`Engine(pipeline)` also constructs a store at `pipeline.repository_root` when
one is not supplied. For an existing run, load its recorded graph rather than
selecting today's registration, which might point somewhere else:

```python
from specromancy_engine import load_pipeline

saved = store.load(run_id, verify_artifacts=False)["pipeline"]
pipeline = load_pipeline(root / saved["path"], repository_root=root)
engine = Engine(pipeline, store)
status = engine.status(run_id)
```

The low-level `load_pipeline(path, repository_root=...)` API does not require a
registry. CLI commands continue to require one. Neither API executes a phase's
agent procedure: call `start_phase(run_id, phase_id)`, use its action packet to
produce the artifact, then call `validate(run_id, phase_id)`. Construct a
separate pipeline and store for each consumer; no new builder API is required.

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
Read-only phases may write their designated visit output there. Completed
outputs are immutable. In the release-documentation example the reviewed notes
stay in run storage; explicitly copying them into release docs is a user action
outside that lifecycle.
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

After changing `AGENTS.md`, a canonical skill, the registry, a pipeline or its
referenced templates/schemas, or CLI help
metadata, run:

```bash
specromancy adapters generate
specromancy adapters generate --check
python -m unittest discover
```

A run stores its pipeline hash. Any pipeline change causes `resume`, `phase`,
and transition commands to reject that run with `pipeline-hash-mismatch`.
Approval records also become stale. The engine deliberately has no active-run
migration: finish the old run before editing its pipeline, restore the exact
old configuration to resume it, or initialize a new run under the new hash.
Never edit `run.json` to force compatibility.

Removing a registration disables new runs and removes unchanged generated
launch skills on regeneration. Keep original graph, skill, and template files
for active runs, which continue to resolve their persisted provenance. Removing
the files or moving the graph prevents continuation. Registry order and edits
to another graph do not change the selected run.
