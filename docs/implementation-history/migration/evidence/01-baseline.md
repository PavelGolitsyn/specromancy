# Stage 01 baseline

Completed on 2026-10-11. This is evidence for [Stage 01](../01-contracts-and-baseline.md),
not a package migration. The [contract decisions](contracts.md) govern the next
stages; [inventory.tsv](inventory.tsv) records the inspected references.

## Checkout and environment

| Item | Observed value |
| --- | --- |
| Commit | `767a417850499bbe13d32cf2a6360a2f9bf04904` (`fix file names`) |
| Branch | `refactoring/folderStructure` |
| Initial worktree | Clean: `git status --porcelain=v1` returned no entries |
| Source files | 232 tracked files; 97 Python files plus the Python checkout launcher |
| Runtime | 52 Python files and four JSON schemas under `specromancy/` |
| Host | macOS 26.6.2, arm64 |
| Git | `git version 2.54.0` |
| Development Python | 3.14.4, Clang 17.0.0 |
| Minimum Python | 3.11.15, Clang 22.1.3 |
| Current package version | `0.1.0` in `specromancy/__init__.py` |

Interpreter paths:

```text
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
/Users/sg/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3
```

The interactive shell has no `python` command and no `python3.11` command on
its original PATH. The existing minimum interpreter was found at the path
recorded by the previous refactoring evidence. No interpreter was installed.
The commands below use each interpreter explicitly and put its bin directory
first on PATH; `python3` used by launcher shebangs resolves to that same
interpreter. This is the interpreter-specific execution of the plan's
`python -m unittest` commands, without substituting a different test runner.

`git tag --list` returned no tags. Inspection of all locally available history
for `specromancy/__init__.py` found only version `0.1.0`, introduced in
`d3374452bcd74aba3c40be74764fe48d5f337baf`. A case-insensitive local history
search for release/publish/version subjects found no release entries. There is
no tracked `pyproject.toml`, setup configuration, dependency/lock file,
changelog, or CI workflow. The repository has an MIT `LICENSE`; fixture skills
declare MIT. The development interpreter reports no installed distribution
whose name contains `specromancy`. These are local observations, not evidence
about remote releases, registry availability, or publication rights.

Current documentation claims Python 3.11+ and a standard-library-only runtime,
but does not declare an operating-system support matrix. This execution proves
the baseline on macOS arm64 only. Keep Python 3.11+ as the requirement; record
Linux and Windows as unverified until their own gates run. Do not infer OS
support from pure Python or the list of supported harnesses.

## Executed verification

From the repository root, run this sequence once for each path above:

```sh
baseline_python=/Users/sg/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3
baseline_bin="${baseline_python%/*}"
env PATH="$baseline_bin:$PATH" "$baseline_python" -m unittest tests.engine.contract.test_compatibility
env PATH="$baseline_bin:$PATH" "$baseline_python" -m unittest tests.engine.contract.test_launcher tests.engine.contract.test_release
env PATH="$baseline_bin:$PATH" "$baseline_python" -m unittest discover
env PATH="$baseline_bin:$PATH" bin/specromancy adapters generate --check
```

For the second sequence, `baseline_python` was
`/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`.
The two interpreter sequences ran concurrently; commands within each sequence
ran in the displayed order. Times below are the unittest-reported durations
(wall time for adapter checks), not performance comparisons.

| Interpreter | Command suffix | Tests | Seconds | Exit | Result |
| --- | --- | ---: | ---: | ---: | --- |
| 3.11.15 | `-m unittest tests.engine.contract.test_compatibility` | 9 | 0.279 | 0 | OK |
| 3.11.15 | `-m unittest tests.engine.contract.test_launcher tests.engine.contract.test_release` | 7 | 0.629 | 0 | OK |
| 3.11.15 | `-m unittest discover` | 249 | 28.610 | 0 | OK |
| 3.11.15 | `bin/specromancy adapters generate --check` | — | 0.040 | 0 | up to date |
| 3.14.4 | `-m unittest tests.engine.contract.test_compatibility` | 9 | 0.296 | 0 | OK |
| 3.14.4 | `-m unittest tests.engine.contract.test_launcher tests.engine.contract.test_release` | 7 | 0.540 | 0 | OK |
| 3.14.4 | `-m unittest discover` | 249 | 34.073 | 0 | OK |
| 3.14.4 | `bin/specromancy adapters generate --check` | — | 0.050 | 0 | up to date |

No failures, errors, or skips occurred. Test stdout was empty; unittest reported
`OK` on stderr. Both adapter checks emitted exactly
`generated adapters are up to date\n` on stdout with empty stderr.
All 232 tracked file contents were SHA-256 compared before and after each
interpreter sequence: no changes. The manifest and all 21 managed adapter
files were included. The worktree remained clean before writing this evidence.
No adapters or compatibility records were regenerated in the checkout.

The launcher/release gate includes nested-directory checkout execution,
`python -m specromancy`, the standalone adapter wrapper, recursive
standard-library dependency scans, and a fresh source copy executed without
installation. It does not establish wheel/sdist installation correctness;
those gates belong to later stages.

## Independent legacy records

The existing records under
`tests/engine/fixtures/refactoring-compatibility/` were captured on 2026-10-03
from runtime commit `7f8aafab4a4f7b6597fded823deb5cd49889450f` with Python
3.14.4. Their README and test-owned hidden skills remain authoritative for
capture and normalization. Stage 01 reused the records and did not recapture
them from the current engine.

| State key in `states.json` | Manifest status | Revision | Events | Replay obligation |
| --- | --- | ---: | ---: | --- |
| `pending` | awaiting-agent | 2 | 2 | Activate the prepared visit without resolving inputs again |
| `active` | active | 3 | 3 | Repeated start does not create another event |
| `awaiting-approval` | awaiting-approval | 4 | 4 | Grant and continue to the configured pause |
| `approved` | awaiting-approval | 5 | 5 | Resume advancement after the durable grant |
| `paused` | paused | 6 | 6 | Resume the pending successor and complete |
| `completed` | completed | 9 | 9 | Terminal replay leaves state unchanged |
| `recoverable` | active | 3 | 2 | Append exactly one recovery event for the interrupted commit |
| `recovered` | active | 3 | 3 | Subsequent loads do not append another recovery event |

These are exact stored file strings, including artifacts and events. Only
temporary absolute roots and Python executable paths are normalized in
response/diagnostic records. Hashes, revisions, timestamps, outcome order, and
persisted bytes are not normalized.

| Record | Bytes | SHA-256 at baseline |
| --- | ---: | --- |
| `canonical.json` | 4560 | `39bd114b1a4a7adebdc6411fe8d30a576ba507b4323010195f7aedf293a5b17b` |
| `responses.json` | 12417 | `6f5d78c2a7cd65e41c38b9095316311f5b1ee522c88d31e2d07830f8c3f6f51b` |
| `diagnostics.json` | 2642 | `a4a7d32beda3b4e5751b846872dcb7189e264fd7ab3ab34f51a1e8675f534c6f` |
| `states.json` | 59156 | `2cde9a1fa06c42ccb9583f36b23863a779f452efd96182bf3e69fc37bc6b975c` |
| `adapters.json` | 18056 | `f4b7a49099fd61e677b8eba31b814e4275e098d5c1ec26b318dc1b5cbb69f0e1` |

## Local runs and pre-existing conditions

Run-directory names were enumerated only to issue the normal command
`bin/specromancy status RUN_ID --json` for each of the 11 directories. Ignored
run storage was excluded from source searches. No request text, artifacts,
manifests, or event logs are copied into this evidence.

| CLI observation | Count | Exit |
| --- | ---: | ---: |
| completed | 6 | 0 |
| active | 1 | 0 |
| `pipeline-not-found`: former `workflow/pipeline.toml` | 2 | 3 |
| `pipeline-not-found`: former `workflow/pipelines/requirements-gathering.toml` | 2 | 3 |

The active run is `20261010T120859Z-fe81300f`, using pipeline `implementation`.
Its reported next command is
`specromancy validate 20261010T120859Z-fe81300f research`; status reports no
warnings. The current graph declares that phase read-only. This run was not
adopted as the migration's workflow, resumed, validated, or edited.

Status cannot determine whether the four runs with missing pipeline files are
active or terminal. Their failures precede the migration; restoring their
original consumer configuration is separate work. Do not rewrite provenance
or relabel those failures as a package regression.

SHA-256 comparison of each local run's `run.json` and `events.jsonl` before and
after inspection found no changes. Normal status inspection can append an
allowed recovery event, but none did here.

Even adding this evidence changes the producer repository snapshot. Moving
source or changing canonical skills later can also invalidate mutation or
provenance checks. A warning-free status is not proof that the active read-only
visit will validate after these edits. Upgrade rehearsal must use independent
consumer files that remain unchanged, preserving the legacy record bytes.

## Stage 2 handoff

The baseline is clean and the original captures are preserved. Proceed with
the physical move and packaging under the temporary `specromancy` namespace
at version `0.1.0`. Use the contract matrix for later implementation stages, including
the discovered action-command discrepancy. No runtime source, canonical
workflow, generated adapter, or local run artifact changes are part of Stage 01.
