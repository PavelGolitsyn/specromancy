# Specromancy

Specromancy is a dependency-free Python 3.11+ proof of concept for portable,
artifact-based agent workflows. A declarative pipeline and canonical skills
define the work; a small CLI validates transitions and persists recoverable run
state independently of any harness conversation.

## Quickstart

From a Git checkout:

```bash
bin/specromancy init "describe the requested change" --pipeline implementation
bin/specromancy status RUN_ID
bin/specromancy resume RUN_ID
python3 -m unittest discover
bin/specromancy adapters generate --check
```

`init` returns the run ID and next action. Follow the emitted action packet and
use its exact output path, skill, mutation policy, and final validation command.
Runtime data is written only under ignored `.specromancy/runs/` storage.

## Customize the workflow

Register pipelines in `workflow/pipelines.toml` and keep their graphs under
`workflow/pipelines/`. Every new run requires `--pipeline ID`; there is no default.
Adapters generate a `specromancy-<id>` launch skill for each registration.
The editable graphs and shared artifact templates live in [`workflow/`](workflow/).
Phase procedures live in [`.agents/skills/`](.agents/skills/) for native harness
discovery, and repository-wide agent constraints live in [`AGENTS.md`](AGENTS.md).
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
