# Specromancy Engine

Specromancy Engine is a dependency-free Python 3.11+ framework for portable,
artifact-based agent workflows. A declarative pipeline and canonical skills
define the work; a small CLI validates transitions and persists recoverable run
state independently of any harness conversation.

## Use the engine in another project

Install the locally built `specromancy-engine` wheel into your project's Python
environment, or add it to an existing Python project's dependencies. Follow the
[installation guide](docs/guides/installation.md) for both routes and the
[release-documentation consumer](examples/release-documentation/README.md) for
an executable two-phase example. Registry installation is available only after
a release exists; this checkout does not claim a published package.

Your project explicitly supplies its registry, graphs, templates, instructions,
and skills. The engine emits actions and verifies agent output; it does not
launch an LLM, provide credentials, generate prose, or publish results.

## Contributor quickstart

From a Git checkout, create a dedicated development environment and install
the package in editable mode:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
bin/specromancy init "describe the requested change" --pipeline implementation
bin/specromancy status RUN_ID
bin/specromancy resume RUN_ID
python -m unittest discover
bin/specromancy adapters generate --check
```

`init` returns the run ID and next action. Follow the emitted action packet and
use its exact output path, skill, mutation policy, and final validation command.
Runtime data is written only under ignored `.specromancy/runs/` storage.

The initial release baseline is `specromancy-engine` version `0.1.0`. It
provides the `specromancy` console command and `python -m specromancy_engine`. This
build is for local verification, not publication. The checkout wrappers
`bin/specromancy` and `adapters/generate.py` also work without installation as
producer-checkout conveniences. Consumers install the dependency; they do not
copy engine source or launchers into their projects.
Python consumers import `specromancy_engine`. Run and event formats use schema
version 1. See the [public contracts](docs/reference/contracts.md) for supported
interfaces, persistence, and ownership rules.

## Customize the workflow

Register pipelines in `workflow/pipelines.toml` and keep their graphs under
`workflow/pipelines/`. Every new run requires `--pipeline ID`; there is no default.
Adapters generate a `specromancy-<id>` launch skill for each registration.
The editable graphs and shared artifact templates live in [`workflow/`](workflow/).
These top-level resources configure this repository's own development workflow;
they are not automatically installed consumer defaults.
Phase procedures live in [`.agents/skills/`](.agents/skills/) for native harness
discovery, and repository-wide agent constraints live in [`AGENTS.md`](AGENTS.md).
The Python package under `src/specromancy_engine/` is the generic engine, not a workflow
customization surface. Start with the
[`workflow/README.md`](workflow/README.md) customization map.

## Documentation

- [Documentation and repository map](docs/README.md)
- [Consumer installation](docs/guides/installation.md)
- [Distribution verification and CI](docs/guides/distribution-verification.md)
- [Architecture](docs/reference/architecture.md)
- [CLI reference](docs/reference/cli.md)
- [Pipeline authoring](docs/guides/authoring-pipelines.md)
- [Harness usage](docs/guides/harnesses.md)
- [Public contracts](docs/reference/contracts.md)
- [Historical plans and refactoring records](docs/implementation-history/README.md)

The engine intentionally does not launch harnesses, migrate active runs between
pipeline versions, provide remote storage or distributed locking, authenticate
approvers, or implement parallel graph joins. See the architecture document for
the complete limitations and safety boundary.
