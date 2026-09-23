# Harness smoke observations

Observation date: 2026-09-23. Repository subject: Stage 8 implementation baseline on branch `poc`.

| Harness | Executable observation | Deterministic adapter observation | Live provider run | Known limitation |
| --- | --- | --- | --- | --- |
| Codex | `codex-cli 0.154.0-alpha.6.2` returned by a local version probe. | Native discovery validates canonical skills; no generated skill copy is required. | Not run; the Stage 8 plan does not authorize paid or credentialed model calls. | Behavior and tool policy vary by host configuration. |
| Hermes | `Hermes Agent v0.21.2 (2026.9.11)`, upstream `f364c197`, returned by a local version probe. | Native discovery validates canonical skills; no generated skill copy is required. | Not run; authentication and inference were not authorized. | Native skill support still depends on the installed harness version. |
| Claude Code | Unavailable in the recorded research environment. | Complete skill copies and `CLAUDE.md` are generated and drift-checked. | Not run because the executable was unavailable. | Generated discovery cannot prove live tool semantics. |
| GitHub Copilot | GitHub CLI/Copilot unavailable in the recorded research environment. | Instructions and thin prompt launchers are generated and drift-checked. | Not run because the executable was unavailable. | Prompt-file invocation and approval UX vary across clients. |
| OpenCode | Unavailable in the recorded research environment. | Thin slash-command launchers are generated and drift-checked. | Not run because the executable was unavailable. | Argument forwarding is deterministic, but live model/tool behavior is provider-specific. |

These observations separate executable discovery, deterministic adapter validity, and model-backed behavior. They must be refreshed when a target harness version or adapter contract changes; no unavailable or unexecuted smoke run is counted as passing.
