# Stage 07 — Distribution verification and CI

Status: planned. Dependency: [Stage 06](06-consumer-example-and-docs.md).
Next: [Stage 08](08-release-readiness.md). Index: [migration plan](README.md).

## Objective

Make regular-install correctness a repeatable gate. Editable installation and
source-launcher checks remain useful, but cannot be the only evidence for an
installable product.

## Intended files

- New `tests/packaging/__init__.py` and focused packaging contract tests.
- New standard-library orchestration script `tools/verify_distribution.py`.
- `pyproject.toml` and, if needed, `MANIFEST.in` for deliberate sdist contents.
- New `.github/workflows/tests.yml` with no publishing credentials or upload step.
- `tests/README.md`, installation/contributor documentation, and evidence files.
- Existing launcher, release, architecture, and compatibility tests where needed.

## Work

1. Keep `python -m unittest discover` as the full-suite command. Pure packaging
   metadata checks may be part of discovery; isolated distribution integration
   belongs in the explicit verifier. The verifier must fail clearly when required
   artifacts or tools are absent, not silently skip and report success.
2. Define the verifier interface, for example:

   ```sh
   python tools/verify_distribution.py --wheel PATH_TO_WHEEL --sdist PATH_TO_SDIST
   ```

   It receives artifacts built before invocation, uses temporary directories,
   performs no network download itself, and never stages, commits, resets, or
   cleans the repository. Provision build tooling explicitly in the build job.
3. Inspect wheel metadata: distribution name, chosen version, Python `>=3.11`,
   license, README, console entry point, and no third-party runtime requirements.
   Assert version agreement with the import package. Enumerate installed modules
   and four schemas rather than checking only that an archive exists.
4. Enforce archive boundaries. The wheel contains the renamed runtime, schema
   data, and normal distribution metadata only. It excludes test fixtures,
   customer configurations, producer workflow/skills, generated harness files,
   source wrappers, caches, environments, runtime data, and unrelated projects.
5. Define sdist contents explicitly: build metadata, runtime source/data, README,
   license, and the complete release-documentation example with its hidden skill
   files. Additional documentation may be included deliberately. Do not require
   the sdist to be a full developer checkout; source-export tests target the Git
   checkout/export, while sdist tests prove rebuilding and consumer use.
6. Extract the sdist safely into a fresh temporary directory, build a wheel from
   it using pre-provisioned tooling, and run the same consumer smoke tests on
   that rebuilt wheel. Use offline/no-isolation build execution only when all
   declared build requirements are already installed and verified. This catches
   missing source files and schemas that a checkout build can conceal.
7. Create a fresh venv per installed artifact. Install using `--no-deps` and
   `--no-index` from the exact wheel path. Remove inherited `PYTHONPATH`, disable
   user-site imports, avoid producer cwd, and verify `__file__` is under that
   venv's installed package rather than the source checkout.
8. In these environments, verify imports, module entry point, console script,
   schema resources, explicit and discovered roots, two-project isolation,
   custom pipeline lifecycle, adapters, and public Python API use.
9. Run representative original-state replays against the installed distribution.
   Copy only required test code/fixtures to a temporary runner or use an explicit
   installed-package driver; do not expose producer runtime source as an import
   fallback. Verify old approvals, immutable artifacts, read-only enforcement,
   and recovery still follow original contracts.
10. Keep source-export tests for the thin developer wrappers, but exclude build
     outputs, venvs, and metadata caches when copying a checkout into fixtures.
     Otherwise new development environments can make those tests huge or hide
     stale packages. Do not broaden ignores to omit real workflow evidence.
11. Add CI jobs for Python 3.11 and the current supported development Python;
     include other claimed versions/platforms as appropriate to recorded support.
     Put the selected interpreter's bin directory on `PATH` for shebang tests.
     Do not infer Windows support from pure-Python code; test it before claiming it.
12. CI should provision tooling, install editable source, run full tests and
     adapter checks, build archives, then execute the verifier. Pin CI actions
     and record a reproducible toolchain according to repository policy at
     implementation time; avoid inventing unverified action versions now.

## Verification matrix

| Mode | Required evidence |
| --- | --- |
| Editable source | Full unit/contract/configuration suite and adapter check |
| Fresh source export | Checkout wrapper help and workflow smoke without installation |
| Direct wheel install | Metadata, public imports, schemas, entry points, consumer lifecycle |
| Wheel rebuilt from sdist | Same consumer checks with no original checkout dependency |
| Legacy-state replay | Original hashes/records, approval behavior, recovery, invariants |
| Adapter upgrade | Old owned outputs upgrade; new output deterministic; collisions safe |

`python -m build` is the normal build command once its build environment is
provisioned. Archive filenames passed to the verifier must be resolved explicitly
so stale multiple versions cannot silently choose the wrong artifact.

Repeat adapter generation against the same inputs and compare exact bytes.
For wheels, compare expected contents and metadata; do not claim byte-for-byte
archive reproducibility without controlling timestamps and build tooling.

## Acceptance criteria

- [ ] Full suite remains runnable with the documented editable setup.
- [ ] Wheel and sdist-rebuilt wheel pass isolated consumer verification.
- [ ] Missing schemas or a stale old namespace cause clear verification failures.
- [ ] No runtime dependency or consumer configuration leaks into the wheel.
- [ ] Example hidden skills survive the intended sdist inclusion rules.
- [ ] Minimum Python version and claimed platform coverage are recorded.
- [ ] CI can repeat the gates without publication credentials.

## Recovery and handoff

A missing package resource or sdist file blocks release: fix discovery/inclusion
and rerun the affected artifact gates. Do not compensate with repository-relative
imports or copied runtime code in test fixtures. Preserve failed-verification
logs and produce a fresh uniquely identified artifact set for Stage 8.
