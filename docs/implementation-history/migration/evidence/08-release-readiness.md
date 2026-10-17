# Stage 08 release-readiness evidence

Completed on 2026-10-12 for [Stage 08](../08-release-readiness.md), as part of
the **specromancy-engine 0.1.0 implementation**. Artifacts are identified by
stage and original hash; command excerpts use explicit artifact-path placeholders
in place of obsolete filenames. Nothing was published, tagged, committed,
uploaded, or renamed remotely.

## Build origin and scope

The starting checkout was clean at
`6093c7812eff7a68e314e46ae8022144497d6e46` (`fix ci`). These artifacts were built
from that commit **plus the Stage 08 working-tree changes**, not a pristine
commit. The retained `build-origin.patch` records the changes present at build
time. No runtime implementation, package version, build requirements, canonical
workflow/skills, or generated adapters changed in this stage.

Changes finalize README, installation/migration/verification guidance, public
contracts, release notes, and test instructions. The distribution runner now
includes the existing engine orchestration tests: the previous installed subset
covered pending approval edits but omitted granted-approval and prepared-resource
cases. A new focused template-drift regression proves warnings, rejected
activation, and unchanged manifest/events. The installed suite grows from 52 to
62 tests; normal discovery grows from 282 to 283.

## Stage 01 reconciliation

The [accepted surface matrix](contracts.md) and its 1,760-row inventory were
reconciled against the final tree. A path map accounts for all 232 baseline
tracked files at `767a417850499bbe13d32cf2a6360a2f9bf04904`: 56 engine files
(52 Python modules and four schemas) map from `specromancy/` to
`src/specromancy_engine/`; the other 176 retain their original paths. No
unrelated source was moved or removed. All 47 files selected under historical
documentation, original compatibility fixtures, pipeline/registry configuration,
templates, and engine schemas match their baseline bytes.

| Surface | Verified result |
| --- | --- |
| Recorded build metadata | `specromancy-engine`; package and distribution version values agreed in the Stage 08 artifacts |
| Python namespace | `specromancy_engine`; six public facades, exports, aliases and exception identities pass; old `specromancy` import absent |
| Source and resources | `src/specromancy_engine/`; all four schemas installed and readable with `importlib.resources` |
| Commands | Installed `specromancy` and `python -m specromancy_engine` work outside checkout; deliberate old module/import break documented |
| CLI contracts | Command arguments, response schema 1 and exit codes retained; only the three captured action prefixes intentionally change |
| Configuration | Consumer-owned `AGENTS.md`, `workflow/`, `.agents/skills/`; producer policy stays outside engine |
| Run storage | `.specromancy/runs/<run-id>/`, schema 1, unchanged original records/hashes and recovery rules |
| Adapters | All 21 baseline output paths preserved; manifest schema 1, generator `specromancy` version 2; installed regeneration command |
| Dependencies | Python `>=3.11`, zero third-party runtime dependencies |
| Naming | `specromancy-engine` is the prospective repository/distribution identity; registry ownership and remote renaming are not claimed |

`reconciliation.json` and `baseline-path-map.json` retain the mechanical checks
locally. Original state, response, diagnostic, canonical, and adapter captures
were not refreshed. The separately versioned response/adapter expectations still
constrain only the intended namespace/renderer differences.

## Controlled migration rehearsal

This run used the plan's **independent original fixture replay** route. The
fixtures were captured from runtime commit
`7f8aafab4a4f7b6597fded823deb5cd49889450f`; their capture procedure and fault
boundaries are documented in the
[fixture README](../../../../tests/engine/fixtures/refactoring-compatibility/README.md).
No live consumer or producer run was used as a test fixture.

For each installed wheel, the verifier creates a temporary consumer using the
original test-owned configuration and exact persisted bytes. Only the runtime
comes from the new installation. Consumer configuration, relative artifact paths,
run IDs and run storage layout remain unchanged. The isolated runner contains
test code and fixtures, no producer runtime, launcher, or editable metadata.
Every runtime module's origin is checked under that fresh venv's site-packages.

| Original state | Observed continuation |
| --- | --- |
| Pending | Starts the original visit and matches the captured active state |
| Active | Repeated activation is a no-op with unchanged state/events |
| Awaiting approval | Run reports the existing request; approval advances to the captured paused boundary |
| Approved before advancement | Continues the recorded grant to the paused boundary without granting twice |
| Paused | Resume, successor activation and validation reach the captured completed state |
| Completed | Run reports terminal completion without changing persisted bytes |
| Recoverable interruption | First load appends the legitimate missing recovery event, matching the original recovered capture |
| Recovered counterpart | Repeated loads/event reads do not append a second recovery event |

These comparisons run for both direct and rebuilt wheels on both interpreters.
Normal transitions and recovery deliberately change state; only contractual
no-ops require byte identity. Fresh-process recovery, immutable completed outputs,
read-only enforcement, and original diagnostic/stream routing also pass.

Separate negative scenarios edit pending and **already granted** output artifacts
or graphs. Approval becomes stale, one invalidation revision/event is persisted,
and retry does not duplicate it. Changed or missing prepared skills warn on status
and reject continuation. Editing a prepared template similarly warns and rejects
activation without rewriting recorded provenance. These are configuration/artifact
changes, not engine-only upgrade failures, and no migration bypass was added.

The separate release-documentation consumer completes its documented custom
two-phase pipeline in a temporary real Git repository, through the installed CLI.
The documented public API example also passes, with consumer files unchanged.

## Separate adapter rehearsal

Original v1 generated bytes and their ownership manifest are restored into
temporary consumers. Check mode reports drift without writes. Generation upgrades
to the captured v2 output, a second generation is byte-identical, and check mode
then passes. Unrelated customer notes remain unchanged.

Existing conflict behavior is preserved: edited **current** manifest-owned
outputs are regenerated; edited stale owned files and unowned collisions are
protected with errors. Canonical source drift, concurrent stale-file edits,
unmanaged support files, and ownership-manifest tampering are covered by the
installed adapter suite. The producer's installed and checkout checks passed on
both Python versions; no producer adapters required regeneration.

## Executed commands and results

All retained outputs are under `/private/tmp/specromancy-stage08-20261012/`.
Fresh dedicated environments `venv311/` and `venv314/` were created using the
already provisioned managed CPython 3.11.15 and 3.14.4 interpreters from the
Stage 07 CI correction. Local platform: macOS 26.6.2 arm64. Both environments
installed tooling and the checkout **before** testing:

```sh
python -m pip install --no-index \
  --find-links /private/tmp/specromancy-migration-02/build-tools \
  -r tools/requirements-build.txt
python -m pip install --no-index --no-build-isolation -e .
```

All provisioning commands exited 0. Toolchain: `build==1.6.1`,
`setuptools==84.0.0`, `packaging==26.3`, `pyproject-hooks==1.3.3`.
The selected environment's `bin/` was first on `PATH` for tests and subprocess
shebang execution; inherited `PYTHONPATH` was removed. Toolchain logs record the
interpreter build and installed versions. Neither tests nor verification
downloaded dependencies.

| Gate | Python | Tests | Test seconds | Exit |
| --- | --- | ---: | ---: | ---: |
| Focused orchestration + packaging contracts | 3.14.4 | 17 | 0.747 | 0 |
| `python -m unittest discover` | 3.11.15 | 283 | 43.781 | 0 |
| `python -m unittest discover` | 3.14.4 | 283 | 47.247 | 0 |
| Direct wheel installed suite | 3.11.15 | 62 | 9.392 | 0 |
| Sdist-rebuilt wheel installed suite | 3.11.15 | 62 | 9.319 | 0 |
| Direct wheel installed suite | 3.14.4 | 62 | 10.058 | 0 |
| Sdist-rebuilt wheel installed suite | 3.14.4 | 62 | 9.976 | 0 |
| Installed adapter check | Both | — | — | 0 |
| Checkout adapter check | Both | — | — | 0 |

Every passing suite had **zero skips**. Full discovery includes fresh source-export
launcher/help/workflow tests with site packages disabled, plus architecture and
negative archive-boundary tests. `git diff --check` passed. The first focused run
failed because the new test used `template` instead of the existing configuration
field `output_template`; correcting the test made the focused and complete suites
pass. That initial log is retained; no runtime change was necessary.

Build and verification commands (with each environment selected in turn):

```sh
python -m unittest tests.engine.contract.test_engine_orchestration tests.packaging.test_distribution
python -m unittest discover
specromancy adapters generate --check
python bin/specromancy adapters generate --check
# Build once with 3.14.4; verify the exact pair with both interpreters.
python -m build --sdist --wheel --no-isolation \
  --outdir /private/tmp/specromancy-stage08-20261012/artifacts
# STAGE08_WHEEL and STAGE08_SDIST stand for the exact artifact paths
# identified by the SHA-256 values below.
python tools/verify_distribution.py \
  --wheel "$STAGE08_WHEEL" \
  --sdist "$STAGE08_SDIST" \
  --log /private/tmp/specromancy-stage08-20261012/distribution311.log
```

The second verifier uses `distribution314.log`. Build and both verifier commands
exited 0. Each `run_check.py` log has the exact argv; companion JSON records cwd,
exit code, and elapsed time. `full311.log`, `full314.log`, `build.log`,
`distribution311.log`, and `distribution314.log` retain the detailed results.

## Local artifacts and archive review

Artifact directory: `/private/tmp/specromancy-stage08-20261012/artifacts/`.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Stage 08 wheel | 95451 | `b027b98c44df51efbb709b7cae5a4fef0074025b171cf67ccc18aeb59c199b5e` |
| Stage 08 source archive | 115030 | `197cb8055fa0e229ffd73aa4ffa96528f159c8ab1794ef6e350d37ff8a82fdf7` |

Both temporary sdist-rebuilt wheels had SHA-256
`530ec5d1500534c55ba2e35803d52454a7491d5efc826b1a083303fe32a93bc3`.
Temporary verifier environments and rebuilt wheels are removed after checking;
the supplied wheel/sdist and logs remain. Equal rebuilt hashes are an observation,
not a promise of archive reproducibility across hosts or timestamps.

The exact wheel inventory has 62 files: 52 modules, four schemas, six metadata
files. The sdist has 89 regular files: 82 explicit source inputs plus seven
generated metadata files. Its only workflow/skills are the deliberate independent
release-documentation example, including hidden skills and ignore rules.
The allowlist/byte comparison rejected no members: neither archive includes the
legacy namespace, producer workflow/skills, adapters, private runs, caches,
environments, historical captures, tests, tools, or `game-of-life/`. Archive
member lists are retained next to the logs. No link or unsafe extraction member
was present. All schemas pass direct and rebuilt installation checks.

`build-inputs.json` records every included source file's SHA-256; its own hash is
`a7083a1eb7e1002fc5dacafb08818b46098749f618cce79c1a2e45be248bdf88`.
The completion report and migration checklist live outside the sdist allowlist,
so recording final hashes does not change the verified artifacts.

## Hosted evidence, preservation, and limitations

The corrected [PR run](https://github.com/PavelGolitsyn/specromancy/actions/runs/38251565471)
and [push run](https://github.com/PavelGolitsyn/specromancy/actions/runs/38251560389)
both completed successfully at build-origin commit
`6093c7812eff7a68e314e46ae8022144497d6e46`. The PR jobs API confirms all four
Ubuntu 24.04/macOS 15 × Python 3.11.15/3.14.4 jobs and every recorded step
succeeded, resolving Stage 07's pending provisioning result. `ci-jobs.json`
retains that read-only result. This is hosted evidence for the origin commit;
the Stage 08 documentation/test-runner changes were verified locally and have
not been submitted to hosted CI. The workflow remains credential-free with no
publication or automatic upload step.

Before/after hashes confirm all 96 existing producer run files are unchanged.
Historical documents, independent captures, canonical graphs/skills/templates,
engine source, and generated adapters are unchanged in Stage 08. Diff review
shows only the intended docs, evidence/checklist, focused test, and verifier
selection changes. No unrelated project file was modified.

Windows and untested Python versions remain unverified; the metadata's `>=3.11`
is not evidence that every platform/version was exercised. Real hosted harness
behavior remains outside the subprocess-wrapper tests. This forward fixture
replay does not establish downgrade safety after new state writes. Keep the
prior engine/configuration and a filesystem backup; follow the
[state-handling contracts](../../../reference/contracts.md#configuration-and-state-handling), never rewrite
state or audit history. Local `/private/tmp` artifacts must be retained elsewhere
by the release owner before temporary storage is cleared. Registry account
setup, name availability, credentials, tags, publishing, and remote repository
renaming remain outside this completed local-readiness stage.
