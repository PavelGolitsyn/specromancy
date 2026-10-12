# Migrate to specromancy-engine 0.2.0

The distribution is `specromancy-engine`; public imports move from `specromancy`
to `specromancy_engine`. This pre-1.0 release deliberately provides no legacy
import shim. Install the locally built wheel using the
[installation guide](installation.md); registry publication is a separate step.

| Before | Version 0.2.0 |
| --- | --- |
| `from specromancy import Engine, RunStore` | `from specromancy_engine import Engine, RunStore` |
| `from specromancy.config import load_pipeline` | `from specromancy_engine.config import load_pipeline` |
| `python -m specromancy` | `python -m specromancy_engine` |
| Checkout `bin/specromancy` | Installed `specromancy` (checkout wrapper remains optional) |
| Reading schemas from a checkout path | `importlib.resources.files("specromancy_engine").joinpath("schemas", NAME)` |

Update dependency metadata, imports, module invocations, and tooling that refers
to the old package path. Public facade responsibilities remain the same; private
underscore modules are not a consumer API. The command name `specromancy`, CLI
arguments, exit codes, response schema version 1, and version-1 run/event formats
remain. Schema filenames and the consumer `.specromancy/runs/` layout remain.

Preserve your `AGENTS.md`, registry, graph files, skills, templates, and existing
adapter manifest. Update canonical procedure command spelling to the installed
CLI where needed, then regenerate adapters and check drift under the
[ownership rules](harnesses.md#ownership-and-conflicts). Current manifest-owned
outputs can be replaced; preserve intentional edits in canonical sources first.
Do not overwrite user instructions by copying the producer's development workflow.

Existing runs resolve their recorded graph provenance. Finish active runs before
changing their graph or consumed resources, or retain the exact old files to
continue them. There is no automatic active-run conversion. Never rewrite run
records, hashes, request artifacts, or completed outputs to force compatibility.
If you need changed configuration, initialize a new run. Inspect `status` and
its warnings before continuation; it is not permission to bypass validation.

The [release notes](../releases/0.2.0.md) and
[public contracts](../reference/contracts.md) describe the preserved contracts.
The [consumer example](../../examples/release-documentation/README.md) shows a
fresh project using the wheel without modifying engine source.
