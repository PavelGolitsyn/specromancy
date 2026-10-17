# Stage 03 namespace verification

Completed on 2026-10-11 for [Stage 03](../03-python-namespace.md), applying the
[Stage 01 namespace decision](contracts.md), within the 0.1.0 implementation.
Artifacts below are identified by stage and original hash. No publication or
remote repository rename was performed.

## Changes and preservation

All 56 runtime files moved from `src/specromancy/` to
`src/specromancy_engine/`. Compared with their pre-stage Git contents, only
three files changed beyond their location: `__init__.py` updates build metadata,
`__main__.py` documents the new module command, and `actions.py` emits the
installed command prefix. The other 53 runtime files, including all four
schemas, are byte-identical. Public facades, signatures, re-export identities,
exception identities, and private subsystem boundaries therefore remain intact.
The old source package is absent, with no shim or duplicate implementation.

Packaging discovery, package data, and the console entry point now use
`specromancy_engine`. Both thin checkout wrappers, test imports, dotted mock
targets, synthetic modules, subprocess module names, dependency allowlists,
physical scans, and schema paths were updated by category. CLI names,
`.specromancy/`, pipeline IDs, harness paths, and generator identity remain.
The [public contracts](../../../reference/contracts.md) describe the implemented
namespace and persisted-state behavior.

The original compatibility captures and all other tracked fixture/history
files remain byte-identical. A separate `responses-current.json` preserves the
original formatting and key order, removing only `<PYTHON>` and `-m` from the
three action command prefixes (`action-pending`, `action-active`, `resumed`).
A dedicated test verifies exactly those changes and compares every remaining
field. Replay continues to compare original state, canonical bytes/hashes,
diagnostics, and test-owned adapter output without refreshing records.

Regenerating after the canonical `AGENTS.md` edit reported 21 files. Only
`.claude/CLAUDE.md`, `.github/copilot-instructions.md`, and
`adapters/manifest.json` changed generated contents. Adapter rendering code and
the original adapter fixture remain unchanged; portable rendering is Stage 05.

## Environments and tests

Dedicated environments live under `/private/tmp/specromancy-migration-03/`:
`dev311`, `dev314`, `build`, and `wheel`. Python versions are 3.11.15 and 3.14.4
on macOS arm64. Each development checkout was installed before testing:

```sh
python -m pip install --no-index \
  --find-links /private/tmp/specromancy-migration-02/build-tools -e .
```

Previously downloaded build tools supplied setuptools 84.0.0 and build 1.6.1;
no runtime dependency or network download was added. Tests ran with the
corresponding environment's `bin/` first on `PATH`, including nested subprocesses
and execution of emitted command argv.

| Interpreter | Check | Tests | Seconds | Result |
| --- | --- | ---: | ---: | --- |
| 3.11.15 | Focused contracts and engine | 42 | 3.541 | pass |
| 3.14.4 | Focused contracts and engine | 42 | 4.425 | pass |
| 3.11.15 | `python -m unittest discover` | 252 | 28.606 | pass |
| 3.14.4 | `python -m unittest discover` | 252 | 34.465 | pass |

The focused command was:

```sh
python -m unittest tests.engine.contract.test_compatibility \
  tests.engine.contract.test_architecture tests.engine.contract.test_launcher \
  tests.engine.contract.test_release tests.engine.contract.test_multi_pipeline \
  tests.engine.unit.test_engine
```

The full runs had no failures, errors, or top-level skips. Final compatibility
replay also passed after preserving the new fixture's original JSON ordering.
Module and console help are identical. Installed adapter checks passed on both
interpreters; the checkout wrapper check also passed. `git diff --check` passed.
Logs are `tests311.log` and `tests314.log` in the temporary verification directory.

## Clean build and wheel-only verification

A fresh export was assembled from existing tracked and nonignored new files,
without `.git`, ignored metadata, caches, old build directories, or old wheels.
The default build produces an sdist and then builds the wheel from that sdist:

```sh
PIP_NO_INDEX=1 \
PIP_FIND_LINKS=/private/tmp/specromancy-migration-02/build-tools \
/private/tmp/specromancy-migration-03/build/bin/python -m build \
  /private/tmp/specromancy-migration-03/export \
  --outdir /private/tmp/specromancy-migration-03/dist
```

| Artifact | SHA-256 |
| --- | --- |
| Stage 03 wheel | `e050047246fb661c8b8afb857b8376fb29c06d66d4598958ac32be7566c71241` |
| Stage 03 source archive | `2a5cb3f0b77ec0d413864439c9ccdaab198abf5b44ed475d19a88994623659d3` |

Archive inspection compared all 56 runtime members and their bytes with the
checkout in both artifacts. The wheel contains only `specromancy_engine/` and
distribution metadata, with no legacy package or consumer workflow assets.

The wheel was installed with `--no-index --no-deps` in a fresh Python 3.11
environment. An isolated `python -I` probe imported all 51 non-executable modules
and package initializers, checked facade/error identities, read all four schemas,
and checked package/distribution versions and the empty dependency list. The
package resolved inside that environment's `site-packages`, outside the producer
checkout. Both `find_spec` and a real import confirmed the old namespace absent;
old module execution also failed as expected.

From outside the checkout, `python -I -m specromancy_engine --help` and the
installed `specromancy --help` succeeded with identical output. An unchanged
copy of the independent compatibility consumer completed its compose/approval/
seal lifecycle; executing the emitted final argv through `PATH` returned exit 0
and a completed status. The initial manual probe tried validation before phase
activation and correctly received exit 5; the corrected lifecycle probe passed.

The verification script and reports are retained locally as `verify.py`,
`distribution.json`, `wheel-contents.txt`, `sdist-contents.txt`, and `build.log`
under `/private/tmp/specromancy-migration-03/`.

## Search audit and handoff

Reviewed current tracked/new sources for old imports, dotted references, module
invocations, and physical paths, including hidden harness files. Remaining hits
are explicit old/new upgrade examples, the original-prefix assertion in the
compatibility test, and the unchanged Windows executable `specromancy.exe`.
Historical plans, original fixtures, and Stage 01/02 evidence intentionally
retain their old names. Schema `$id` URLs remain unchanged.

Stage 04 can proceed with the renamed package. Linux and Windows execution
remain unverified. No live run was migrated; consumer-root/resource changes,
portable adapter rendering, and release automation remain later-stage work.
