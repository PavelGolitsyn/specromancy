# Stage 02 packaging verification

Completed on 2026-10-11 for [Stage 02](../02-source-layout-and-packaging.md).
The intermediate distribution is `specromancy-engine==0.1.0`; imports and module
invocation remain `specromancy`. This is a local verification build, not a
published release. Stage 03 is next.

## Changes and preserved contracts

All 56 tracked runtime files moved from `specromancy/` to `src/specromancy/`:
52 Python sources and four JSON schemas. SHA-256 comparisons against a snapshot
taken before the move confirmed every file was byte-identical. There is no old
runtime directory or `src/__init__.py`. The 66 tracked fixture, history, and
example files in the initial inventory also remained byte-identical.

`pyproject.toml` uses `setuptools.build_meta`, pinned to `setuptools==84.0.0`.
This backend supports the Python 3.11 floor and the selected SPDX license and
license-file metadata. The selection follows the upstream
[release history](https://setuptools.pypa.io/en/stable/implementation-history.html) and
[pyproject configuration documentation](https://setuptools.pypa.io/en/stable/userguide/pyproject_config.html).
Build dependencies are separate from the empty runtime dependency list.
Discovery is limited to regular `specromancy` packages below `src/`; implicit
package data is disabled, with only `schemas/*.json` explicitly included.

Both checkout wrappers now prepend `src/`. Release subprocesses use `-S`, which
disables site packages, to prove installation-free source-export execution.
Launcher coverage compares installed console, module, and checkout help from
outside the repository. New checks compare installed metadata with the package
version and reject empty or missing roots in recursive source scans. Schema
unit tests now address the physical source location.

Repository instructions and current documentation describe editable installation
before testing. After changing `AGENTS.md`, `bin/specromancy adapters generate`
completed with exit 0 and reported 21 generated files. Only `.claude/CLAUDE.md`,
`.github/copilot-instructions.md`, and `adapters/manifest.json` changed contents.
Canonical phase skills, engine policy, public exports, CLI payloads, and legacy
compatibility records were unchanged.

## Environments and acquisition

Host: macOS arm64. Existing interpreters:

- Python 3.11.15: `/Users/sg/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3`
- Python 3.14.4: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`

Dedicated environments were created under
`/private/tmp/specromancy-migration-02/`: `dev311`, `dev314`, `build`, and `wheel`.
No base interpreter was modified. The first sandboxed editable-install attempt
failed because package-index DNS/network access was blocked; the approved retry
succeeded. Build tools were then downloaded separately from the tests:

```sh
/private/tmp/specromancy-migration-02/dev314/bin/python -m pip install -e .
/private/tmp/specromancy-migration-02/dev314/bin/python -m pip download \
  --dest /private/tmp/specromancy-migration-02/build-tools setuptools==84.0.0 build
/private/tmp/specromancy-migration-02/dev311/bin/python -m pip install \
  --no-index --find-links /private/tmp/specromancy-migration-02/build-tools -e .
/private/tmp/specromancy-migration-02/build/bin/python -m pip install \
  --no-index --find-links /private/tmp/specromancy-migration-02/build-tools build==1.6.1
```

All four commands exited 0. The build environment contains `build==1.6.1`,
`packaging==26.3`, and `pyproject_hooks==1.3.3`. The isolated backend is
`setuptools==84.0.0`. No unit test downloads or installs dependencies.

## Tests and adapter checks

From the checkout, run with each environment's `bin` directory first on `PATH`
so both Python invocations and executable wrapper shebangs use that environment:

```sh
export PATH=/private/tmp/specromancy-migration-02/dev311/bin:$PATH
python -m unittest tests.engine.contract.test_launcher tests.engine.contract.test_release tests.engine.contract.test_architecture tests.engine.contract.test_compatibility
python -m unittest discover
bin/specromancy adapters generate --check
specromancy adapters generate --check
```

Repeat with `dev314/bin` first on `PATH`.

| Interpreter | Gate | Tests | Seconds | Exit |
| --- | --- | ---: | ---: | ---: |
| 3.11.15 | Focused launcher, release, architecture, compatibility | 25 | 1.495 | 0 |
| 3.14.4 | Focused launcher, release, architecture, compatibility | 25 | 1.819 | 0 |
| 3.11.15 | Full discovery | 251 | 27.892 | 0 |
| 3.14.4 | Full discovery | 251 | 33.252 | 0 |
| 3.11.15 | Checkout and installed adapter checks | — | — | 0 each |
| 3.14.4 | Checkout and installed adapter checks | — | — | 0 each |

No failures, errors, or top-level skips occurred. As before, the shipped-command
test guards its nested full-suite invocation against recursive command testing.
Both full-suite logs are retained locally as `full311.log` and `full314.log` in
the temporary verification directory. Every adapter check reported
`generated adapters are up to date`. The 25-test focused gate includes successful
`python -m specromancy --help` and `specromancy --help` invocations on both versions.

## Build and regular installation

From the checkout, the following exited 0. The default `build` command first
produces an sdist, then builds the wheel from that sdist in isolation:

```sh
PIP_NO_INDEX=1 \
PIP_FIND_LINKS=/private/tmp/specromancy-migration-02/build-tools \
/private/tmp/specromancy-migration-02/build/bin/python -m build
```

Artifacts (ignored by Git):

| Artifact relative to checkout | SHA-256 |
| --- | --- |
| `dist/specromancy_engine-0.1.0-py3-none-any.whl` | `8d97deaa0d59ade74ad7e42c01757aea6e76475b0abcda076562c736950ee52b` |
| `dist/specromancy_engine-0.1.0.tar.gz` | `e98c47d73c2de95784a4fc699da27dd54a25a164973865b914f5aa11fbffb0df` |

A standard-library `zipfile` check compared the wheel's runtime member set and
every member's contents with all 56 source files. All nested modules and all
four schemas were included. Every wheel member was beneath `specromancy/` or
`specromancy_engine-0.1.0.dist-info/`. There were no workflows, skills, wrappers,
tests, run data, or `game-of-life/` files. Wheel metadata declared Python `>=3.11`,
license expression `MIT`, and no `Requires-Dist` entries. `tarfile` inspection
also confirmed all 56 sources in the sdist; it contains source, package metadata,
README, license, and build configuration, without repository workflow assets.

The exact wheel was installed in the fresh `wheel` environment:

```sh
/private/tmp/specromancy-migration-02/wheel/bin/python -m pip install \
  --no-deps --no-index \
  /Users/sg/projects/pavel/specromancy/dist/specromancy_engine-0.1.0-py3-none-any.whl
```

From `/private/tmp/specromancy-migration-02/outside-checkout`, with `PYTHONPATH`
removed from the subprocess environment, both commands exited 0 and printed
identical help:

```sh
/private/tmp/specromancy-migration-02/wheel/bin/python -I -m specromancy --help
/private/tmp/specromancy-migration-02/wheel/bin/specromancy --help
```

An isolated `python -I` probe imported all runtime modules other than the
executable `__main__` (exercised by the module command), parsed all four installed
schemas, compared installed/package versions, and confirmed no runtime
requirements. It asserted the imported package was inside `sys.prefix`, under
`site-packages`, and outside the checkout. Observed location:

```text
/private/tmp/specromancy-migration-02/wheel/lib/python3.14/site-packages/specromancy/__init__.py
```

The executed inspection/probe script is retained locally at
`/private/tmp/specromancy-migration-02/verify.py`; its reports are
`distribution.json`, `wheel-contents.txt`, and `sdist-contents.txt`. The build log
is `build.log` in the same directory. Build archives, environments, caches, and
package metadata are not committed.

## Handoff limits

This verifies Stage 02 on macOS arm64, with editable installs on both supported
minimum and development interpreters and a regular wheel install on Python 3.14.
Linux and Windows remain unverified. The consumer workflow rehearsal, portable
adapter invocation changes, namespace break, and release automation belong to
later stages. No release was published and no live run artifacts were migrated.
