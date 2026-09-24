# POC release checklist

This gate produces a local, unpublished release candidate. It does not authorize package-index publication, a Git tag, credential use, or provider-backed paid calls.

## Source and deterministic checks

- Confirm the intended Git subject and account for every dirty path.
- Run `specromancy adapters check`; regenerate only after reviewing canonical changes.
- Run focused unit, contract, integration, security, static, example, and packaging tests.
- Run `python3 -m unittest discover -s tests -p 'test_*.py'` on Python 3.11 or newer.
- Run `specromancy doctor` and `specromancy doctor --format json`.
- Exercise the minimal example pass path and the disposable flawed-patch/repair path.
- Review one dated smoke observation per harness; unavailable or unexecuted live runs are not passes.
- Verify every documentation command against the release candidate.

## Build and clean-room checks

```bash
python3 -m build
python3 -m venv /tmp/specromancy-release-venv
/tmp/specromancy-release-venv/bin/python -m pip install --no-deps --no-index dist/specromancy-0.1.0-py3-none-any.whl
/tmp/specromancy-release-venv/bin/specromancy --version --format json
```

- Inspect wheel and sdist file lists. The wheel contains runtime Python, six JSON contracts, four Markdown templates, and license metadata.
- Confirm the sdist additionally contains docs, canonical skills, tests, and `examples/minimal`.
- Confirm neither archive contains `.specromancy/runs`, caches, compiled files, local backups, `build/`, `dist/`, or secret-bearing files.
- From outside the checkout, run installed `doctor --format json`, generate adapters into a disposable Git repository, and check their reproducibility.
- Generate SHA-256 checksums for the sdist and wheel into `dist/SHA256SUMS`, then verify them.

## Release agreement

- Confirm `0.1.0` agrees across package metadata, CLI output, changelog, documentation, wheel, and sdist.
- Confirm pipeline, run, artifact, and adapter compatibility versions agree with [Versioning](versioning.md).
- Confirm known limitations and breaking-change policy are current.
- Confirm the MIT license covers code, templates, and canonical skills.
- Tag or publish only after artifacts, checksums, documentation, and the checklist agree, and only under a separate explicit authorization.

## Post-POC priorities

Prioritize, but do not implement in this release: optional harness runners; signed skill/adapter bundles; remote artifact stores and multi-repository runs; optional richer JSON Schema validation; a web UI and run visualization; PR/CI integrations; regulated policy packs; and a benchmark suite spanning multiple models per harness.
