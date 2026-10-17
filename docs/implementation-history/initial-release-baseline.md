# 0.1.0 metadata and documentation correction

The implementation plan, refactoring, and packaging/namespace migration all
belong to the 0.1.0 implementation. The migration records document internal
implementation stages of this version.

On 2026-10-17, package metadata, runtime version, CI artifact paths,
installation examples, and packaging expectations were corrected to 0.1.0.
Current documentation describes the supported interfaces directly. The redundant
release notes and consumer migration guide were removed; the numbered stages
and evidence under `migration/` retain the actual implementation history.

Development artifacts are identified by implementation stage and their original
hashes and results. Historical command excerpts use explicit artifact-path
placeholders instead of obsolete filenames. These records verify the artifacts
tested at each stage; current artifacts have their own verification below.

Runtime behavior, public namespace, schemas, and adapter generator behavior
are unchanged by this correction. Regression coverage is retained. The response expectation is named `responses-current.json`; its contents were preserved when it was renamed.

## Verification

Verified locally on 2026-10-17 with Python 3.14.4 on macOS 26.6.2 arm64.
The existing dedicated `.venv` was refreshed with
`python -m pip install --no-index --no-build-isolation -e .` using the pinned
build tools already installed there. No runtime dependencies were added.

- Focused release, compatibility, distribution, and executable documentation
  checks: 32 tests passed.
- `python -m unittest discover`: 283 tests passed.
- `specromancy adapters generate --check` and
  `bin/specromancy adapters generate --check`: both passed without regeneration.
- Fresh wheel and sdist built with `python -m build --sdist --wheel --no-isolation`.
- `python tools/verify_distribution.py --wheel PATH --sdist PATH`: passed;
  direct wheel and sdist-rebuilt wheel each passed 62 isolated consumer tests.
- Renamed response fixture compared byte-for-byte with its original Git version.
- Relative file links in changed Markdown and `git diff --check`: passed.

Artifacts are retained locally under
`/private/tmp/specromancy-initial-release-20261017/`:

| Artifact | SHA-256 |
| --- | --- |
| `specromancy_engine-0.1.0-py3-none-any.whl` | `f666db7005d876fb1f77dd0c69ca7a7e7f4ccb50354c47f59d25a2cd932e6b7c` |
| `specromancy_engine-0.1.0.tar.gz` | `705269b5c6f6dc671710f0a7a1f48df99ed6307d9d556a777cd59ce28a51784e` |

The retained verifier log is
`/private/var/folders/yj/jn92n54553gd97js97cbt6nh0000gn/T/specromancy-distribution-eu86h5kr.log`.
These temporary paths are local evidence, not distribution URLs. Hosted CI and
other interpreters/platforms were not rerun as part of this change.
