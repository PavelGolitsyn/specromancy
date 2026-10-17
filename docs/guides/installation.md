# Install the engine in a consumer project

Python 3.11 or newer is required. The distribution **specromancy-engine** provides
the **specromancy_engine** Python package and **specromancy** executable, with no
third-party runtime dependencies. Installation supplies the generic engine and
four published schemas. Your project supplies its workflow configuration,
instructions, and skills; these are not installed defaults.

## Obtain a local wheel

The initial release baseline is version 0.1.0. These instructions do not assume that
the package is published or available on PyPI. From a producer checkout, a
maintainer builds the wheel in a dedicated build environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r tools/requirements-build.txt
python -m build --sdist --wheel --no-isolation --outdir dist
```

The separately provisioned toolchain includes the pinned build backend declared
in `pyproject.toml`; these are build dependencies, not engine runtime dependencies. The result is
`dist/specromancy_engine-0.1.0-py3-none-any.whl`. Transfer that wheel to the
consumer. The consumer needs no engine source or editable install. The
[distribution verification guide](distribution-verification.md) documents the
repeatable wheel and sdist gates and links their executed evidence.
Verify the wheel hash against its build evidence before installation. `bin/specromancy` and
`adapters/generate.py` are producer-checkout conveniences; do not copy them or
the engine source into each consumer project.

## CLI-only project environment

From the consumer project root (which may be a non-Python project):

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --no-index --no-deps /absolute/path/to/specromancy_engine-0.1.0-py3-none-any.whl
specromancy --help
python -m specromancy_engine --help
```

Keep `.venv/` ignored. Ensure the harness inherits this environment's `PATH`;
activating a terminal does not update an already-running GUI process. See
[Harness usage](harnesses.md) for command environments and generated adapters.

## Python project dependency

In an existing Python project's `pyproject.toml`, merge this entry into its
existing dependency list; preserve its other metadata and dependencies:

```toml
[project]
dependencies = ["specromancy-engine==0.1.0"]
```

Use a directory containing the local wheel when installing that project:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --find-links /absolute/path/to/wheels .
```

The local wheel satisfies the pinned engine dependency. Pip may obtain your
project's other dependencies and build backend from its configured indexes;
use `--no-index` only if all of those are supplied locally too. Do not add the
engine's source directory to `PYTHONPATH`. After a registry release exists, the
same dependency entry can resolve from that registry, and CLI-only consumers
can use `python -m pip install specromancy-engine==VERSION` for a published
version. Registry availability is not asserted by this guide.

With the release-documentation example configured, this runnable API example
initializes a separate run, reads persisted status, and starts the emitted phase:

<!-- public-api: tested with the release-documentation consumer -->
```python
from pathlib import Path
from specromancy_engine import Engine, RunStore, load_registry

root = Path.cwd().resolve()  # Run from the explicitly selected consumer root.
pipeline = load_registry(root).load("release-documentation")
store = RunStore(root)
engine = Engine(pipeline, store)
response = engine.initialize((root / "sample-changes.md").read_text(encoding="utf-8"))
run_id = response["action"]["run_id"]
status = engine.status(run_id)
manifest = store.load(run_id)
action = engine.start_phase(run_id, response["action"]["phase"])["action"]
assert action["mutation"]["policy"] == "read-only"
print(action["output"]["absolute_path"])
# An agent writes the designated output using action's inputs and skill.
# Then: response = engine.validate(run_id, action["phase"])
```

The API returns actionable response dictionaries; `EngineError` reports expected
failures. It does not call an LLM or author the output. For an existing run, use
the recorded pipeline path, as shown in [Pipeline authoring](authoring-pipelines.md#embed-the-installed-engine).
The [consumer walkthrough](../../examples/release-documentation/README.md)
executes both phases through completion using the CLI and a deterministic agent.

## Supply consumer configuration explicitly

Copy the complete [release-documentation example](../../examples/release-documentation/README.md)
into a new directory, including hidden `.agents/` and `.gitignore`, or author
the following resources in your existing project:

| Resource | Your responsibility |
| --- | --- |
| `AGENTS.md` | Preserve existing user instructions; merge applicable constraints |
| `workflow/pipelines.toml` | Merge an explicit unique registration; there is no default |
| `workflow/pipelines/<id>.toml` | Own phases, policies, outcomes, and input selectors |
| `workflow/templates/` | Supply every template referenced by your graph |
| `.agents/skills/pipeline/SKILL.md` | Explicitly copy/review the generic orchestrator |
| `.agents/skills/<phase-skill>/SKILL.md` | Own the phase procedures and portable frontmatter |
| `.gitignore` | Ignore `.specromancy/`, local environments, and development outputs |

Use a real Git repository for this example. Specify `--root /absolute/consumer`
when invoking from elsewhere, especially while inspecting an example inside a
producer checkout: otherwise Git discovery can select the producer. A non-Git
consumer needs both explicit `--root` and graph `allow_non_git = true`.

The engine has no implicit scaffolding step. Installing it never silently
overwrites `AGENTS.md`, skills, a registry, or harness files. After reviewing
your configuration, explicitly run `specromancy adapters generate` and
`specromancy adapters generate --check`. Generate before starting a read-only
phase because adapter generation changes repository files. Keep the manifest
with its generated files. Resolve conflicts using the
[documented ownership model](harnesses.md#ownership-and-conflicts), preserving
existing instructions before regeneration. Do not manufacture ownership by
editing the manifest.

The producer's top-level `workflow/` and `.agents/skills/` configure development
of this repository. They remain in place and are not customer defaults. The
example's own corresponding directories configure release documentation.

## Contributor environment

Contributors editing engine source use a dedicated editable installation from
the producer checkout, separate from the consumer routes above:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover
specromancy adapters generate --check
```

Editable tests alone do not prove a wheel works in another project. See the
[test guide](../../tests/README.md) for independent consumer verification and
the [public contracts](../reference/contracts.md) for supported interfaces and state handling.
