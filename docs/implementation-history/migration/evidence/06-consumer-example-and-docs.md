# Stage 06 consumer example and documentation verification

This records a stage of the 0.1.0 implementation. Artifacts are identified by
stage and original hash; historical command excerpts use explicit artifact-path
placeholders where obsolete filenames have been omitted.

Completed on 2026-10-12 for [Stage 06](../06-consumer-example-and-docs.md).
All checks ran on macOS arm64. The initial working tree was clean.

## Delivered behavior

`examples/release-documentation/` is a complete consumer project: instructions,
ignore rules, sample change request, explicit registry, two-phase graph,
templates, and portable canonical skills. The draft and review phases are both
read-only for repository files and write only designated run outputs. Successful
validation seals each output and ends with the configured `approved` result.
The reviewer can instead persist a declared stop with `block`, leaving the
sealed draft intact. There is no repair loop or publication operation.

The example's generic orchestrator is an exact copy of the producer procedure;
a permanent consistency test enforces equality. Phase procedures and release
policy remain example-owned. No runtime source, producer workflow/skill,
generated adapter, packaging metadata, historical record, or engine fixture
was changed. A source search found no release example IDs or stop reason in
`src/specromancy_engine/`.

The README walkthrough captures the run ID, phase IDs, resolved inputs, and
output paths from CLI responses. A deterministic agent writes the sample prose
only to the emitted artifact paths. It invokes the emitted validation argv and
handles exit 8 explicitly. Both phases have one successful outcome, so validation
must omit `--outcome`; blocking uses the declared stop command instead. The docs
explain that `approved` is a workflow verdict, not a human gate or publishing
permission, and that structural validation does not establish factual accuracy.

The installation guide separates CLI-only wheel installation, dependency
metadata in another Python project, and contributor editable installation.
Configuration is explicitly copied or authored, preserving existing consumer
instructions and adapter ownership. Distribution/import/executable names and
run formats are documented in the current public contracts. The separate
consumer migration guide drafted during this stage was removed because all
of this work belongs to the 0.1.0 implementation. Registry
publication is not claimed. Source-distribution inclusion remains Stage 07 work.

## Permanent coverage

`tests/packaging/test_release_documentation.py` has eight tests. It copies the
complete example including hidden files to a separate temporary Git repository,
uses the installed console script with explicit `--root`, and executes the
Markdown walkthrough and public API block verbatim. Assertions cover the final
outcome, output hashes, manifest/event revision agreement, unchanged sample and
project files, reproducible adapters, store refusal to overwrite completed
outputs, external artifact drift, read-only violation, declared blocking,
missing registry, missing orchestrator, and invalid/missing pipeline IDs.

The two new shipped-configuration tests enforce orchestrator equality and
portable example skill frontmatter. Existing test-owned fixtures stay independent.

## Commands and results

Dedicated editable environments were created with Python 3.14.4 at
`/private/tmp/specromancy-stage06-dev/` and Python 3.11.15 at
`/private/tmp/specromancy-stage06-dev311/`. Both installed the checkout before
testing with their own Python:

```sh
python -m pip install --no-index \
  --find-links /private/tmp/specromancy-migration-02/build-tools -e .
```

The local cache provided the pinned setuptools 84.0.0 build dependency. No tests
downloaded or installed dependencies. Each suite put its environment's `bin/`
first on `PATH`.

| Environment | Command/check | Tests | Seconds | Exit |
| --- | --- | ---: | ---: | ---: |
| Python 3.14.4 editable | Focused command below | 18 | 3.314 | 0 |
| Python 3.14.4 editable | `python -m unittest discover -s tests/shipped_configuration -t .` | 18 | 23.322 | 0 |
| Python 3.11.15 editable | `python -m unittest discover` | 275 | 40.275 | 0 |
| Python 3.14.4 editable | `python -m unittest discover` | 275 | 48.358 | 0 |
| Python 3.11.15 regular wheel | Copied consumer example suite | 8 | 2.828 | 0 |
| Python 3.11.15 dependency consumer | Documented API example and CLI help | — | — | 0 |
| Installed CLI and checkout launcher | `adapters generate --check` | — | — | 0 |

The focused command was:

```sh
python -m unittest \
  tests.packaging.test_release_documentation \
  tests.engine.contract.test_architecture \
  tests.shipped_configuration.test_consumer_example
```

All final suites passed without skips. The first focused run exposed two test
expectation errors: audit revisions use `manifest_revision`, and unknown pipeline
selectors return 3. Those assertions were corrected to the existing public
behavior; the engine was unchanged. Documentation relative links and heading
anchors were checked, command spelling was reviewed against the implementation,
and `git diff --check` passed. Producer adapters required no regeneration;
consumer generation was repeated and compared for unchanged bytes.

## Wheel-only and dependency consumer verification

The verification driver exported only metadata, license, README, and engine
source into `/private/tmp/specromancy-stage06-verification/export/`, then ran:

```sh
python -m pip wheel --no-index \
  --find-links /private/tmp/specromancy-migration-02/build-tools --no-deps \
  /private/tmp/specromancy-stage06-verification/export \
  --wheel-dir /private/tmp/specromancy-stage06-verification/dist
```

The Stage 06 wheel has SHA-256:
`72d5b29e0f1da9d9cbcf560a590dc6ef8dfc608069eb163f54a46357fefd9af6`.
Archive inspection found only the engine package and distribution metadata,
with all four engine schemas and no consumer examples, skills, or configuration.

A fresh Python 3.11 environment installed only that wheel with
`python -m pip install --no-index --no-deps WHEEL`. The example, installation
guide, and standalone test module were copied into a bundle outside the producer.
The test process used `python -I -B`, cleared inherited `PYTHON*`/`GIT_*` settings,
disabled user sites and bytecode writes, and used the wheel environment plus
system command directories on `PATH`:

```sh
SPECROMANCY_CONSUMER_BUNDLE=/private/tmp/specromancy-stage06-verification/bundle \
  /private/tmp/specromancy-stage06-verification/wheel-env/bin/python -I -B \
  /private/tmp/specromancy-stage06-verification/bundle/test_release_documentation.py -v
```

The imported engine originated at
`/private/tmp/specromancy-stage06-verification/wheel-env/lib/python3.11/site-packages/specromancy_engine/__init__.py`.
The consumer contained neither engine source nor a checkout launcher. The suite
completed the documented lifecycle and verified project file preservation.

A second fresh environment installed a separate minimal Python project whose
`[project].dependencies` pinned `specromancy-engine` to the tested Stage 06 build.
It resolved the
local wheel via `pip install --no-index --find-links DIST --find-links BUILD_TOOLS .`.
The documented public API snippet and installed CLI help both succeeded there.
Thus both installation routes were executed without a registry release.

The local driver is `/private/tmp/specromancy-stage06-verify.py`; logs, copied
bundle, wheel, archive listing, and `report.json` remain under
`/private/tmp/specromancy-stage06-verification/`. Full suite logs are
`full311.log` and `full314.log`. These local artifacts are verification evidence,
not committed run state or dependencies of the permanent tests.

Stage 07 remains responsible for repeatable distribution tooling, source archive
contents, and CI. No package publication or hosted harness session was attempted;
Linux and Windows were not exercised in this stage.
