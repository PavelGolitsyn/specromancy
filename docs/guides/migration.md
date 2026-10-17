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

## Controlled upgrade sequence

1. Stop overlapping engine commands. Keep the prior verified engine installation
   and configuration history, and take a normal filesystem backup of the consumer's
   run directory and configuration. Keep private run contents out of public reports.
2. Select the verified `0.2.0` wheel and compare its SHA-256 with the release
   evidence using `shasum -a 256 /absolute/path/to/specromancy_engine-0.2.0-py3-none-any.whl`
   (or `sha256sum` on Linux). Use a new isolated environment, or a controlled
   dependency update in your existing project:

   ```sh
   python3 -m venv .venv-engine-0.2.0
   . .venv-engine-0.2.0/bin/activate
   python -m pip install --no-index --no-deps /absolute/path/to/specromancy_engine-0.2.0-py3-none-any.whl
   specromancy --help
   python -m specromancy_engine --help
   ```

   Ignore the environment in Git before starting a read-only phase. Python
   projects can instead pin `specromancy-engine==0.2.0` in their dependency
   metadata and install using the local wheel directory as described in the
   [installation guide](installation.md#python-project-dependency).
3. Update Python imports and module commands using the table above. Ensure the
   harness process can find this environment's `specromancy` executable on
   `PATH`; restarting a GUI harness with that environment may be necessary.
   `bin/specromancy` is producer-checkout convenience only. Do not copy engine
   source or launcher code into consumer projects.
4. First inspect persisted state with **unchanged** consumer configuration:

   ```sh
   specromancy --root /absolute/consumer --json status RUN_ID
   ```

   Keep `.specromancy/` at its existing location. Never edit `run.json`,
   `events.jsonl`, artifact hashes, or completed outputs to make an upgrade pass.
   A legitimate interrupted commit can cause status to append one recovery
   event; status is not guaranteed to leave every run byte-identical.
5. Review canonical skill, template, graph, and instruction changes as a separate
   configuration upgrade. Preserve `AGENTS.md`, registry entries, and user
   instructions. Do not copy the producer's development workflow over them.
   Finish affected active runs using their original resources, or retain those
   resources and initialize new runs for the changed configuration.
6. Rehearse adapter regeneration separately, before starting a read-only phase:

   ```sh
   specromancy --root /absolute/consumer adapters generate --check
   specromancy --root /absolute/consumer adapters generate
   specromancy --root /absolute/consumer adapters generate --check
   ```

   The first check may legitimately return drift (11). Review canonical changes
   and preserve intentional managed-file edits in canonical sources before
   generation. Current manifest-owned outputs are regenerated even when edited;
   edited stale owned outputs and unowned collisions are protected with errors.
   Keep the manifest and follow the existing
   [ownership rules](harnesses.md#ownership-and-conflicts); do not manufacture
   ownership by editing it. Unrelated customer files must stay unchanged.
7. Inspect `status RUN_ID` again and follow its emitted next command for each
   run. Pending, active, approval, paused, terminal, and recoverable states have
   different continuation behavior; do not approve or resume every run blindly.

## State and configuration compatibility

An engine-only upgrade preserves compatible version-1 state when consumer
configuration and artifacts remain unchanged. Original fixture replays exercise
pending, active, awaiting approval, approved before advancement, paused,
completed, and interrupted/recovered states through installed packages.
Recovery and normal transitions can legitimately append events and change the
manifest; unchanged bytes are required only for operations with a no-op contract.

Editing graphs, skills, or templates is a separate change. Graph and artifact
drift can invalidate approval; prepared skill/template drift produces provenance
warnings and prevents continuation. Editing an approved output before advancement
still marks the approval stale and requires a fresh decision. Migration never
disables these checks.

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

## Rollback and support

For an engine-only upgrade failure, select the prior verified installation and
inspect status through its CLI. Downgrade safety for state newly written by
0.2.0 has not been established by this forward-upgrade rehearsal. Rehearse that
direction before relying on it. A package downgrade also does not undo separately
adopted renderer or configuration changes; retain their original history.

Do not roll back by deleting `.specromancy/`, rewriting audit events, weakening
ownership checks, or resetting repository work. Any future stored-format
conversion needs its own versioned design. A support report should include the
engine/Python versions, artifact hash, failing command and diagnostic, and whether
configuration or adapters changed, without exposing private run contents.

`specromancy-engine` is also the prospective repository name. Registry account
setup, package-name ownership, remote renaming, tags, publication, and credentials
are outside this local migration; no remote ownership or availability is claimed.
