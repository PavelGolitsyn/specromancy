# Changelog

All notable changes are documented here. The package uses semantic versioning; independent pipeline, run-manifest, artifact, and adapter versions are described in [docs/versioning.md](docs/versioning.md).

## 0.1.0 - 2026-09-23

Initial unpublished proof-of-concept release.

### Added

- Durable request, research, plan, implementation, review, approval, repair, resume, cancellation, lock, and verification workflows.
- Canonical repository skills and deterministic adapters for Codex, Claude Code, GitHub Copilot, Hermes, and OpenCode.
- Versioned packaged contracts and artifact templates with strict digest bindings and future-version rejection.
- Security/static checks, deterministic integration fixtures, behavioral evaluation contracts, clean-room packaging tests, and the shared minimal example.
- Complete getting-started, concepts, artifacts, CLI, harness, troubleshooting, security, versioning, and release documentation.

### Compatibility

- Package: 0.1.0.
- Pipeline contract: 1.
- Run manifest schema: 1.
- Artifact schema: 1.
- Adapter manifest: 1.

There are no older known run schemas to inspect or migrate. Version 0.x breaking changes will be called out in this file and will not silently rewrite existing artifacts.

### Known limitations

- Provider-backed harness smoke runs are optional and were not release-blocking.
- Review independence is procedural where a harness cannot guarantee separate process or identity isolation.
- The POC has no signed bundles, remote artifact store, multi-repository workflow, web interface, provider runner, PR/CI service integration, regulated policy packs, or cross-model benchmark suite.
- The release is local and unpublished; no package-index upload or Git tag is part of Stage 9.
