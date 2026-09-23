# Testing and evaluation

Specromancy uses four validation layers. Static checks validate canonical skills, packaged JSON, templates, repository-local documentation links, example command names, and adapter drift. Unit and contract tests cover state guards, parsers, digest bindings, Git snapshots, locks, atomic writes, recovery, stable exits, and JSON envelopes. Integration fixtures exercise complete and blocked workflows without model access. Behavioral evaluation cases score observable artifacts and repository outcomes with versioned rubrics.

## Local verification

Run focused suites first, then the full provider-free suite:

```bash
python -m unittest tests.security.test_boundaries tests.unit.test_evals tests.unit.test_doctor
python -m unittest discover -s tests -p 'test_*.py'
specromancy adapters check
specromancy doctor
specromancy doctor --format json
python -m build
```

The source checkout must be on `PYTHONPATH` when it is not installed. Wheel testing installs the built artifact into an isolated environment and reruns contract, adapter-resource, and CLI smoke tests.

## Fixtures and evaluations

`tests/fixtures/e2e/` describes seven deterministic repository scenarios: Python repair, TypeScript feature, unrelated dirty work, approval-sensitive migration, underspecified request, successful repair, and exhausted repair. Integration tests build temporary Git repositories and use pre-authored artifacts; they do not call a model.

Normalized cases live in `tests/evals/cases/`. Each phase has at least three cases, including a failure case, and declares initial state, allowed tools and mutations, required properties, forbidden behavior, a weighted rubric, and human-review notes. Expected deterministic results live in `tests/evals/expected/`. `specromancy.evals` scores structure, mutation boundaries, tests, requirement coverage, verdict consistency, and audit completeness. Scores are evidence for comparison, not a claim that one model run is definitive.

Normalized live results are stored below `.specromancy/evaluations/<harness>/<version>/`. Harness, harness version, and model label are recorded independently so results are not silently combined across versions. Failures are triaged as contract defect, skill defect, harness limitation, or model variability.

## CI and failure evidence

CI covers Ubuntu, macOS, and Windows on Python 3.11 and 3.14. Source tests, installed-wheel tests, security/static/adapter checks, and packaging are separate jobs. Failed jobs upload test and diagnostic evidence with short retention. Credentialed harness smoke runs are intentionally absent from required CI.

Manual harness observations are versioned in [Harness smoke observations](harnesses/smoke-observations.md). A missing executable or unauthenticated provider is recorded as unavailable or not run, never as a pass.
