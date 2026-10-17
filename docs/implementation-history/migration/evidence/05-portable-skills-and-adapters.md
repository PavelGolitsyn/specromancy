# Stage 05 portable skills and adapter verification

Completed on 2026-10-11 for [Stage 05](../05-portable-skills-and-adapters.md).
Verification ran on macOS arm64 with dedicated editable and regular-install
environments under `/private/tmp/specromancy-migration-05/`.

## Changes and preserved contracts

Generator version 2 renders `specromancy` in launch skills, all twelve harness
wrappers, and regeneration instructions. Both Markdown and YAML provenance
comments derive their version from `GENERATOR_VERSION`. The generator name
remains `specromancy`; manifest schema version 1, paths, targets, placeholder
conventions, quoting, argument order, and `--json` behavior are unchanged.

The five canonical procedures and current example-fixture procedures use the
installed command. Canonical procedures explain the consumer working directory
and harness process environment; terminal activation does not update an already
running GUI harness. Harness guides document `python -m specromancy_engine` as
a diagnostic route to the same CLI. Onboarding links the generic project-owned
pipeline procedure for explicit copying. Installation and generation still do
not create that canonical skill; a missing procedure fails without writes.
No phase names or workflow policy were added to the engine.

`actions.py`, `status.py`, source capture, and ownership code needed no changes.
Status `next_command` uses the consumer cwd; validation argv includes the
absolute consumer root. Both contexts are executed in the consumer smoke tests.

The unchanged ownership rules distinguish current and stale output:

- `--check` reports drift without writing, including edited current output.
- Generation restores a current manifest-owned file even if it was edited.
- Unowned destinations and edited stale files remain conflicts.
- Only unchanged owned stale files can be removed. Unrelated user files remain.

This distinction was confirmed by inspection and regression tests, and is now
explicit in the public contracts and harness guide. No overwrite bypass or
`--force` option was added. Generation retains per-file atomic replacement and
manifest-last writing; it is not a multi-file transaction. Intentional user
edits must be preserved and moved to canonical sources before regeneration.
The working tree was clean before this stage; no pre-existing edits were lost.

## Compatibility and permanent tests

The original `adapters.json`, all historical source records, and original
canonical/state/diagnostic/response captures remain untouched.
`adapters-generator-v2.json` separately captures the new rendering. Tests compare
its exact bytes and hashes and constrain its delta from the original to command
spelling, provenance version, manifest generator metadata, and generated hashes.
The canonical source records, discovery paths, and ownership schema stay equal.
Existing exact canonical/state/diagnostic comparisons and the separately
versioned Stage 03 response comparisons continue unchanged.

Upgrade tests restore original v1 files and their original manifest into a
fresh fixture, check drift without writes, regenerate, compare exact v2 bytes,
and repeat generation/check. An edited current owned file follows the existing
restoration behavior. Existing tests retain stale-file and collision coverage.
New tests cover check mode without a manifest or any generated output, and
explicitly forbid temporary writes during drift checks.

Command extraction rejects the old launcher spelling and requires nonempty
known-command matches. Wrapper checks preserve regeneration references and
command counts. The self-contained packaging suite additionally asserts all
twelve expected wrappers and both launch-skill paths, exact invocation strings,
Claude zero-based/OpenCode one-based placeholders, Copilot named placeholders,
argument boundaries, and `--json`. It substitutes representative arguments and
executes every invocation through the installed CLI, including descriptions
containing spaces, quotes, dollar signs, command-substitution text, and Unicode.
Substitution is performed as argv, never by evaluating description text as shell
code. Actual hosted harness substitution behavior is a separate integration
boundary and was not exercised.

## Commands and results

The Python 3.11.15 and 3.14.4 development environments installed the checkout
before testing with their own Python:

```sh
python -m pip install --no-index \
  --find-links /private/tmp/specromancy-migration-02/build-tools -e .
```

The cached setuptools 84.0.0 wheel supplied the build dependency. No tests
installed or downloaded dependencies. Each test invocation put its dedicated
environment's `bin/` first on `PATH`.

| Environment | Command/check | Tests | Seconds | Exit |
| --- | --- | ---: | ---: | ---: |
| Python 3.11.15 editable | Focused command below | 53 | 4.915 | 0 |
| Python 3.11.15 editable | `python -m unittest discover -s tests/shipped_configuration -t .` | 16 | 17.583 | 0 |
| Python 3.11.15 editable | `python -m unittest discover` | 265 | 33.855 | 0 |
| Python 3.14.4 editable | `python -m unittest discover` | 265 | 40.572 | 0 |
| Python 3.11.15 regular wheel | Copied consumer smoke module | 7 | 4.926 | 0 |
| Python 3.11.15 regular wheel | Documented Python examples | 3 | — | 0 |
| Python 3.11.15 editable | Second generation byte comparison and `--check` | — | — | 0 |

The focused command was:

```sh
python -m unittest \
  tests.engine.unit.test_adapters \
  tests.engine.unit.test_multi_pipeline_adapters \
  tests.engine.unit.test_skills \
  tests.engine.contract.test_adapter_drift \
  tests.engine.contract.test_compatibility \
  tests.packaging.test_consumer_roots
```

Final successful suites had no skips. Both editable environments passed the
final `specromancy adapters generate --check`; `git diff --check` also passed. The optional external skill-creator
`quick_validate.py` could not start because its interpreter lacks PyYAML;
repository skill/frontmatter/command tests passed and require no such dependency.
The repository allows its existing `compatibility` frontmatter field, which the
external validator's narrower allowlist also omits. No runtime dependency was
added to accommodate that tool.

All 21 repository adapters were regenerated from finalized canonical sources.
A second generation produced identical file bytes and manifest hashes. Final
manifest SHA-256:
`380cdb902deac73873e5955cd32b9b3516ba3be71d299cfb44e3351e810c7cbe`.
Canonical and generated instruction trees contain no `bin/specromancy` reference.
The initial sandboxed generation could not write `.agents`; the authorized
retry completed through the generator. No generated file was manually edited.

## Wheel-only consumer verification

A temporary export was built offline with:

```sh
python -m pip wheel --no-index \
  --find-links /private/tmp/specromancy-migration-02/build-tools --no-deps \
  /private/tmp/specromancy-migration-05/export \
  --wheel-dir /private/tmp/specromancy-migration-05/dist
```

A fresh environment installed the wheel with `pip install --no-index --no-deps`.
The wheel SHA-256 is
`ee10b4d3b6d3fb76fa01e0d0d33afd07cd256f82dec073fcf0d5014fb263cd04`.
Archive inspection found only the engine package and distribution metadata,
including the four unchanged engine schemas. No consumer skills were installed.

The copied self-contained smoke suite ran outside the producer with `python
-I -B`, inherited `PYTHON*`/`GIT_*` variables cleared, user sites disabled,
bytecode writes disabled, and `PATH` limited to the wheel environment and system
command directories. The imported package origin was:

```text
/private/tmp/specromancy-migration-05/wheel/lib/python3.11/site-packages/specromancy_engine/__init__.py
```

Consumers contain neither `bin/specromancy` nor engine source. They explicitly
supply their own instructions and skills, then generate and check adapters.
The installed package and empty home were made read-only. Before/after snapshots
confirmed the producer checkout (including Git metadata), installed package,
and home remained unchanged. All wrapper commands and launch skills executed;
status argv worked from a nested consumer directory and unchanged validation
argv worked from an unrelated directory.

Local logs and drivers remain in the verification directory: `focused.log`,
`shipped.log`, `tests311.log`, `tests314.log`, `generation.json`, `build_wheel.py`,
`verify_wheel.py`, `probe.py`, `wheel-smoke.log`, `wheel-contents.txt`, and
`wheel-report.json`. Permanent tests neither depend on those paths nor download
build dependencies. Stage 06 can now document complete consumer onboarding;
Linux/Windows and live hosted-harness behavior remain unverified here.
