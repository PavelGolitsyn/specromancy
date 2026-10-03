# Specromancy

Specromancy is a dependency-free Python 3.11+ proof of concept for portable,
artifact-based agent workflows. A declarative pipeline and canonical skills
define the work; a small CLI validates transitions and persists recoverable run
state independently of any harness conversation.

## Quickstart

From a Git checkout:

```bash
bin/specromancy init "describe the requested change"
bin/specromancy status RUN_ID
bin/specromancy resume RUN_ID
python3 -m unittest discover
bin/specromancy adapters generate --check
```

`init` returns the run ID and next action. Follow the emitted action packet and
use its exact output path, skill, mutation policy, and final validation command.
Runtime data is written only under ignored `.specromancy/runs/` storage.

## Customize the workflow

The editable graph, artifact templates, and canonical phase procedures live in
[`workflow/`](workflow/), with skills in [`workflow/skills/`](workflow/skills/)
beside the templates. Templates for repository-wide instructions and the
generic pipeline skill live in [`specromancy/artifacts/`](specromancy/artifacts/).
Run `bin/specromancy adapters generate` after editing canonical sources;
`AGENTS.md`, `.agents/skills/`, and the other harness surfaces
are generated mirrors recorded in `adapters/manifest.json`.
The Python package under `specromancy/` is the generic engine, not a workflow
customization surface. Start with the
[`workflow/README.md`](workflow/README.md) customization map.

## Documentation

- [Architecture](docs/poc-v3/architecture.md)
- [CLI reference](docs/poc-v3/cli.md)
- [Pipeline authoring](docs/poc-v3/authoring-pipelines.md)
- [Harness usage](docs/poc-v3/harnesses.md)
- [Public contracts](docs/poc-v3/contracts.md)
- [POC v3 implementation plan](docs/poc-v3/implementation-plan/README.md)

The POC intentionally does not launch harnesses, migrate active runs between
pipeline versions, provide remote storage or distributed locking, authenticate
approvers, or implement parallel graph joins. See the architecture document for
the complete limitations and safety boundary.
