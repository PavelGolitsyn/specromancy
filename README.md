# Specromancy

Specromancy 0.1.0 is an unpublished proof of concept for durable, artifact-driven development. It coordinates a harness-agnostic `request -> research -> plan -> implementation -> review` workflow without making one chat session or model provider the source of truth.

It is alpha software: use it on a disposable branch or worktree, inspect every plan and artifact, and keep normal source-control backups.

## Requirements and installation

Specromancy requires Git and Python 3.11 or newer. Runtime code uses only the Python standard library.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/specromancy --version
.venv/bin/specromancy doctor
```

Windows environments use `.venv\Scripts\python` and `.venv\Scripts\specromancy`. The module entry point, `python -m specromancy`, is equivalent to the console script.

## Quick start

The checked-in [minimal greeting example](examples/minimal/README.md) is shared by every harness guide:

```bash
specromancy adapters generate
specromancy adapters check
specromancy init --id minimal-greeting --request examples/minimal/request.md
specromancy status minimal-greeting
```

Invoke the selected harness's pipeline skill with `Continue run minimal-greeting.` The pipeline creates evidence-backed research and a traceable plan, then stops. Inspect the plan before recording approval:

```bash
specromancy artifact verify minimal-greeting plan
specromancy approve minimal-greeting plan --by YOUR_IDENTITY
```

Invoke the pipeline again to implement and review. Durable state and redacted command evidence live under `.specromancy/runs/minimal-greeting/`. Start with the complete [under-fifteen-minute guide](docs/getting-started.md).

## How it works

- `AGENTS.md` defines repository-wide constraints; canonical procedures live in `.agents/skills/`.
- The CLI validates state and persists transitions. It does not perform model work.
- Markdown artifacts and SHA-256 bindings carry state across sessions.
- Plan approval is an explicit CLI record bound to the exact validated plan digest.
- Implementation is limited to the approved change inventory and records every verification command.
- Review independently inspects durable inputs, the actual diff, and verification evidence.
- Requested changes enter at most three repair cycles by default; exhausted work becomes blocked.

See [Concepts](docs/concepts.md) and [Run artifacts](docs/artifacts.md) for the state and trust model.

## Harnesses

Specromancy supports deterministic discovery surfaces for [Codex](docs/harnesses/codex.md), [Claude Code](docs/harnesses/claude-code.md), [GitHub Copilot](docs/harnesses/github-copilot.md), [Hermes](docs/harnesses/hermes.md), and [OpenCode](docs/harnesses/opencode.md). Capabilities are not assumed uniform. The dated [smoke observation table](docs/harnesses/smoke-observations.md) separates executable availability, deterministic adapter checks, and provider-backed runs.

Generated adapters contain no unique workflow policy. Generation refuses collisions; `--force` creates content-addressed backups. Cleanup is conservative:

```bash
specromancy adapters clean
```

It removes only manifest-owned files whose bytes still match the generated digest. It never removes user source, modified generated files, backups, canonical skills, or run artifacts.

## Documentation

- [Getting started](docs/getting-started.md) — install and complete the shared workflow.
- [Concepts](docs/concepts.md) — authority, state, permissions, approval, review, and repair.
- [Artifacts](docs/artifacts.md) — run layout, bindings, command records, retention, and recovery.
- [CLI reference](docs/cli.md) — every command, state, side effect, exit code, and recovery path.
- [Troubleshooting](docs/troubleshooting.md) — symptom-led safe recovery.
- [Security model](docs/security.md) — threats, controls, redaction limits, and residual risk.
- [Testing](docs/testing.md) — deterministic suites, fixtures, evaluations, and smoke policy.
- [Versioning](docs/versioning.md) — package and independent format compatibility.
- [Release checklist](docs/release-checklist.md) — reproducible local release gate.

## Development and release verification

Install the development-only build tool with `python3 -m pip install -e '.[dev]'`, then run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m specromancy adapters check
python3 -m specromancy doctor --format json
python3 -m build
```

The sdist includes the documentation, canonical skills, tests, and minimal example. The wheel includes runtime modules, contracts, artifact templates, and license metadata. Local `build/`, `dist/`, caches, backups, and `.specromancy/runs/` are excluded. Built artifacts and `dist/SHA256SUMS` are local release evidence; 0.1.0 is not published or tagged by this stage.

## Compatibility and limitations

The package follows semantic versioning. Pipeline contract, run manifest, artifact schema, and adapter manifest use independent integer versions, currently all version 1. The legacy CLI `schema_version` output remains available. Unsupported future data is rejected, and Specromancy never silently migrates artifacts.

Known POC limits include procedural rather than guaranteed process isolation for review, no signed skill bundles, no remote artifact store, no multi-repository run, no web UI, no built-in provider runner, no CI/PR service integration, and no provider-backed smoke test in the required suite. Repository skills are untrusted input, and redaction is not permission to inspect secrets.

See [CHANGELOG.md](CHANGELOG.md) for the release notes and disclosed breaking-change policy. The MIT license covers the code and repository-shipped templates and canonical skills.
