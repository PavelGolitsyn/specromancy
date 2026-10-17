# Stage 07 distribution verification and CI evidence

This records a stage of the 0.1.0 implementation. Artifacts are identified by
stage and original hash; historical command excerpts use explicit artifact-path
placeholders where obsolete filenames have been omitted.

Completed on 2026-10-12 for [Stage 07](../07-distribution-verification.md).
The starting working tree was clean. The initial execution below ran on macOS
arm64 before hosted CI. The CI provisioning correction at the end records the
subsequent hosted results and follow-up verification.

## Delivered gate

`tools/verify_distribution.py` takes explicit prebuilt wheel and sdist paths and
returns nonzero for missing artifacts, resources, tools, archive violations, or
failed/skipped tests. It uses only standard-library imports and invokes separately
provisioned build tooling. It never downloads dependencies or changes repository
work. Its temporary environments, extraction, rebuild, and copied test runners
are outside the producer checkout. Logs persist on both success and failure.

The wheel allowlist contains all 52 runtime Python modules, four schemas, and
six normal distribution metadata files. The gate compares runtime bytes against
the current checkout and checks distribution name/version, Python >=3.11,
MIT license, README, console entry point, and no runtime requirements. Installed
checks enumerate imports and schemas, verify every module's origin under that
venv's site-packages, match package/distribution versions, and reject a legacy
`specromancy` import namespace. Module and console help must agree.

`MANIFEST.in` now starts with an exclusion and explicitly includes runtime,
build/normal distribution metadata, README, license, the complete example with
hidden skills/ignore rules, and current guides/reference/release documentation.
It excludes the producer's workflow/skills, generated harness files, tests,
historical documentation, tools, runtime data, environments, caches, and unrelated
projects. The sdist is not a developer checkout. Its contents are checked before
regular-file-only extraction; links, traversal, duplicate paths, special files,
and unexpected roots/members fail. A fresh wheel is rebuilt offline with
`--no-isolation` only after verifying the pinned tools and all backend-declared
wheel build requirements.

Each wheel is installed with `--no-index --no-deps` into its own fresh venv.
The `python -I -B` runner exposes only required copied test code and fixtures,
with no runtime source, editable metadata, or producer wrappers. Environment
sanitization removes inherited Python, Git, Pip, and Specromancy settings. The
sdist-rebuilt consumer gets its example and guide from the extracted archive.

The same 52-test installed suite covers two independent projects, explicit and
discovered roots, real Git worktrees/non-Git roots, public APIs, complete custom
lifecycles, immutable outputs, read-only violations, approval invalidation,
fresh-process recovery, all harness wrappers, and adapter collisions. Original
canonical hashes, run/event/artifact bytes, diagnostics, approvals, and recovery
states replay against installed code. Original adapter bytes upgrade through
existing ownership rules and repeated generation is byte-identical. The original
fixtures and engine implementation were not changed.

Seven fast packaging contract tests were added to normal discovery. They cover
valid inventories and failures for missing schemas/artifacts, old namespaces,
runtime dependencies, configuration/fixture/cache leaks, omitted hidden skills,
unsafe tar members, and arbitrarily named venv exclusion. Both source-export
callers now use one filter that excludes build outputs, egg/dist metadata,
bytecode, and directories containing `pyvenv.cfg`, while retaining real workflow,
skill, historical, adapter, and unrelated-project source evidence.

## Provisioning and executed commands

Dedicated environments:

- `/private/tmp/specromancy-stage07-dev311/`: Python 3.11.15.
- `/private/tmp/specromancy-stage07-dev/`: Python 3.14.4.

Both were provisioned before tests, using the existing local wheel cache:

```sh
python -m pip install --no-index \
  --find-links /private/tmp/specromancy-migration-02/build-tools \
  -r tools/requirements-build.txt
python -m pip install --no-index --no-build-isolation -e .
```

The toolchain is `build==1.6.1`, `setuptools==84.0.0`, `packaging==26.3`, and
`pyproject-hooks==1.3.3`. Each full-suite command had its environment's `bin/`
first on `PATH`, including subprocess shebang tests. No suite downloaded tools.

| Gate | Interpreter | Tests | Seconds | Exit |
| --- | --- | ---: | ---: | ---: |
| Focused `tests.packaging.test_distribution` | 3.14.4 | 7 | 0.245 | 0 |
| `python -m unittest discover` | 3.11.15 | 282 | 40.679 | 0 |
| `python -m unittest discover` | 3.14.4 | 282 | 49.373 | 0 |
| Direct wheel installed suite | 3.11.15 | 52 | 7.545 | 0 |
| Sdist-rebuilt wheel installed suite | 3.11.15 | 52 | 7.528 | 0 |
| Direct wheel installed suite | 3.14.4 | 52 | 9.287 | 0 |
| Sdist-rebuilt wheel installed suite | 3.14.4 | 52 | 9.154 | 0 |
| Installed `specromancy adapters generate --check` | 3.14.4 | — | — | 0 |
| Checkout `bin/specromancy adapters generate --check` | 3.14.4 | — | — | 0 |

All passing test runs had zero skips. `git diff --check` passed. No generated
adapter changes were required. Focused rejection coverage remains in discovery.
A separate real invocation in an environment without the build frontend exited 1
with `required build tool build==1.6.1; found missing`, rather than skipping.

The final artifacts were built directly from the checkout, with both targets
specified so the first wheel did not itself depend on the sdist build:

```sh
python -m build --sdist --wheel --no-isolation \
  --outdir /private/tmp/specromancy-stage07-final-20261012
# STAGE07_WHEEL and STAGE07_SDIST stand for the exact artifact paths
# identified by the SHA-256 values below.
python tools/verify_distribution.py \
  --wheel "$STAGE07_WHEEL" \
  --sdist "$STAGE07_SDIST" \
  --log /private/tmp/specromancy-stage07-verify314.log
```

The verifier command was repeated with the 3.11 environment and
`--log /private/tmp/specromancy-stage07-verify311.log`. Both invocations passed.
The full logs include actual venv import origins, all runtime paths, subprocess
commands, rebuilt wheel hashes, test names/results, and tool versions.

## Artifact handoff to Stage 08

The fresh artifact set is `/private/tmp/specromancy-stage07-final-20261012/`:

| Artifact | SHA-256 |
| --- | --- |
| Stage 07 wheel | `99ab88f558112c8a99b26ffd3e4aa379a43a95edfdb7b9b7b0220b904ddcd873` |
| Stage 07 source archive | `8099d3f4ae42afa555301c53372f74f46b08c3953bdfa9a82d1e32fed637aae7` |

The two temporary rebuilt wheels both had hash
`36496e7707cd9bb3726ff66970e743077c61f58364d2f6a8b5f07cfefd48a134` in these
runs. This is observed evidence, not a claim of byte-for-byte archive
reproducibility across builds or hosts. The permanent gate verifies exact
contents/metadata and compares deterministic adapter bytes.

Retained local logs:

- `/private/tmp/specromancy-stage07-build-final.log`
- `/private/tmp/specromancy-stage07-full311.log`
- `/private/tmp/specromancy-stage07-full314.log`
- `/private/tmp/specromancy-stage07-verify311.log`
- `/private/tmp/specromancy-stage07-verify314.log`
- `/private/tmp/specromancy-stage07-initial.log` (expected archive gate failure
  during implementation: the initial allowlist omitted generated egg metadata;
  fixed by explicit inclusion, followed by successful fresh builds).
- `/private/tmp/specromancy-stage07-missing-tools.log` (intentional missing-tool
  negative verification).

Temporary extraction/consumer environments are intentionally removed by the
verifier. Logs and the supplied artifact set remain. No publication, tag, commit,
registry check, or remote repository change was performed.

## Initial CI pins and coverage boundary

`.github/workflows/tests.yml` provisions tooling, installs editable source,
runs the full suite and both adapter checks, builds exact artifacts, and runs the
same verifier. The matrix is Python 3.11.15 and 3.14.4 on Ubuntu 24.04 and macOS
15. It adds the environment's bin directory to `GITHUB_PATH`, uses read-only
repository permissions, disables persisted checkout credentials, and has no
publishing or upload step. The log is printed with `if: always()`.

No separate repository CI pinning policy existed. Actions were resolved through
upstream GitHub tag-reference APIs and the corresponding commits verified on
2026-10-12, then pinned to those full commits:

- [actions/checkout v6 reference](https://api.github.com/repos/actions/checkout/git/ref/tags/v6):
  [`d23441a48e516b6c34aea4fa41551a30e30af803`](https://github.com/actions/checkout/commit/d23441a48e516b6c34aea4fa41551a30e30af803).
- [actions/setup-python v6 reference](https://api.github.com/repos/actions/setup-python/git/ref/tags/v6):
  [`ece7cb06caefa5fff74198d8649806c4678c61a1`](https://github.com/actions/setup-python/commit/ece7cb06caefa5fff74198d8649806c4678c61a1).

The package requires Python >=3.11. Local passing evidence is macOS arm64 on
3.11.15 and 3.14.4. The Linux/macOS hosted matrix is configured, not yet observed
running here. Windows and other interpreter versions were not tested and no
Windows support is claimed. Stage 08 should include the actual hosted CI result
before making broader release-readiness claims.

## CI provisioning correction — 2026-10-12

The initial hosted [PR run](https://github.com/PavelGolitsyn/specromancy/actions/runs/38240801925)
and [push run](https://github.com/PavelGolitsyn/specromancy/actions/runs/38214095533)
passed both Ubuntu jobs and macOS Python 3.14.4. The macOS 3.11.15 job failed in
`setup-python`, before project installation, tests, or builds. Its runner was
macOS ARM64. The action's catalog had no macOS 3.11.15 build; the local 3.11.15
used for the original verification was supplied by uv, a different interpreter
provider. The original matrix incorrectly assumed those catalogs were equivalent.

The corrected workflow uses the same managed CPython provider on all four jobs.
[`astral-sh/setup-uv` v10.3.0](https://github.com/astral-sh/setup-uv/releases/tag/v10.3.0)
is pinned to `1c37ad07a6a961277cf70c0d37d6f313000f5884`, with uv pinned to
`0.11.27`. The upstream tag and action inputs were checked before use. Caching is
disabled, preserving the workflow's no-upload behavior. Explicit
`uv python install --no-bin "$TEST_PYTHON_VERSION"` provisions the selected
interpreter; `uv python find --managed-python` selects its executable to create
the standard-library venv. The venv bin directory remains first on `PATH` for
all later gates and shebang tests. Python/pip continue to own installation,
testing, and package builds. The runtime and package build dependencies did not
change. All exact Python versions, operating systems, and verification gates
remain in the matrix.

The pinned uv download catalog was checked for all four targets: CPython
3.11.15 and 3.14.4, Linux x86_64 glibc and macOS ARM64. Both macOS interpreters
were then downloaded into the initially empty
`/private/tmp/specromancy-ci-fix/python/`, using a separate empty cache. This
exercised provisioning without an existing interpreter installation. Download
builds were `20260623` for 3.11.15 and `20260414` for 3.14.4. Local network access
required sandbox escalation; the authorized downloads succeeded.

Fresh dedicated venvs under `/private/tmp/specromancy-ci-fix/venv311/` and
`venv314/` used those downloaded interpreters. Both installed the pinned tools
from the existing local wheel cache, then installed the checkout with
`python -m pip install --no-index --no-build-isolation -e .` before tests.
The full `python -m unittest discover` suite passed with no skips: 282 tests
in 41.473 seconds on 3.11.15 and 44.745 seconds on 3.14.4. Both installed and
checkout adapter checks passed. YAML parsing verified the four matrix entries;
every workflow shell block passed `bash -n`.

Fresh artifacts were built under `/private/tmp/specromancy-ci-fix/artifacts/`
using `python -m build --sdist --wheel --no-isolation`. The distribution gate was
run using each new environment against these exact artifact paths. All four
installed suites passed 52 tests with zero skips: direct/rebuilt wheel times
were 7.705/7.668 seconds on 3.11.15 and 8.326/8.300 seconds on 3.14.4. The fresh
wheel SHA-256 is
`e959d42ada6cb6ae21ea33c4f14a12392eaa015d6b2982bd42ff04e7e1b8454c`;
the fresh sdist SHA-256 is
`1d87c0f27595527f4afeac3895e693d291e01d87809ea637d4d82514996d3674`.
These artifacts include the updated provisioning guide. Full-suite,
build, and distribution logs are retained under `/private/tmp/specromancy-ci-fix/`.
The corrected hosted workflow still requires a run after these changes are
pushed; local provisioning and tests do not substitute for that hosted result.
