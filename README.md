# Specromancy

Specromancy is a harness-agnostic toolkit for artifact-driven, spec-driven development. Its proof of concept coordinates a durable `request -> research -> plan -> implement -> review` workflow without making a model provider or chat session the source of truth.

## POC terminology

- **Run:** One durable execution of the pipeline for a request, stored under `.specromancy/runs/<run-id>/`.
- **Phase:** One canonical unit of work: research, plan, implementation, or review. Orchestration coordinates phases but does not perform them.
- **Status:** The persisted state of a run, such as `research_ready`, `plan_approved`, or `passed`.
- **Artifact:** A Markdown phase handoff with restricted, versioned frontmatter and phase-specific validated content.
- **Manifest:** `run.json`, the current-state projection containing artifact digests, approvals, repository identity, and repair-cycle state.
- **Event log:** `events.jsonl`, the append-only audit history used to explain and replay manifest state.
- **Approval:** An explicit CLI record binding an approver-supplied identity to the exact validated plan digest. Approval in prose or chat does not count.
- **Canonical skill:** A workflow procedure in `.agents/skills/<name>/`; it is the source from which any harness-specific copy or launcher is generated.
- **Harness:** Codex, Claude Code, GitHub Copilot, Hermes, or OpenCode—the environment that invokes a skill and provides agent tools.
- **Adapter:** A generated harness discovery or invocation file. It contains no unique pipeline policy.
- **Repair cycle:** A bounded return from `changes_requested` to implementation, followed by a fresh review.
- **Validator:** Deterministic code that checks a manifest, artifact, repository subject, or transition guard before state can advance.

The version 1 architecture and public contracts are documented in [the POC architecture](docs/architecture/poc.md).

## Install and run

Specromancy requires Python 3.11 or later and has no runtime dependencies outside the standard library.

```bash
python -m pip install .
specromancy --help
specromancy --version --format json
```

The module entry point is equivalent when a console-script launcher is unavailable:

```bash
python -m specromancy --help
```

For development, install the optional build tooling with `python -m pip install -e '.[dev]'`. Run the full verification with:

```bash
python -m unittest discover -s tests -p 'test_*.py'
python -m specromancy adapters check
python -m build
```

The `build` package is development-only and is deliberately absent from the runtime dependency set.

The POC implements durable research, planning, implementation, review, orchestration, resume, and harness-adapter commands. Plan approval is explicit and digest-bound; prose approval never substitutes for the CLI gate.

For an initialized run, the research lifecycle is:

```bash
specromancy phase start RUN_ID research
specromancy artifact path RUN_ID research
specromancy validate RUN_ID research
specromancy phase complete RUN_ID research
```

The canonical procedure is in `.agents/skills/research/`. Completion validates the evidence-backed artifact, enforces research-only write scope, records its digest and request binding in `run.json`, and appends audit events.

After research reaches `research_ready`, the planning lifecycle is:

```bash
specromancy phase start RUN_ID plan
specromancy artifact path RUN_ID plan
specromancy validate RUN_ID plan
specromancy phase complete RUN_ID plan
specromancy approve RUN_ID plan --by IDENTITY
```

The canonical procedure is in `.agents/skills/plan/`. A plan must trace every initialized requirement to current research evidence, file-level changes, and verification. Approval binds the supplied identity to the exact validated plan digest; chat prose is never approval. Replanning after approval begins with:

```bash
specromancy approval revoke RUN_ID plan --by IDENTITY --reason TEXT
specromancy phase start RUN_ID plan
```

## Harness adapters

Generate, verify, inspect, or safely remove discovery adapters with:

```bash
specromancy adapters generate [--harness NAME]
specromancy adapters check [--harness NAME]
specromancy adapters clean [--harness NAME]
specromancy adapters list
```

Codex and Hermes use `AGENTS.md` and `.agents/skills` natively. Claude Code receives generated `CLAUDE.md` and complete skill copies; GitHub Copilot receives instructions and thin prompt launchers; OpenCode receives thin slash-command launchers. Generated paths and source digests are recorded in `specromancy/adapters/manifest.json`.

Generation refuses to overwrite user-authored or hand-edited files. `--force` preserves each replaced file under `specromancy/adapters/backups/<sha256>/<original-path>` before replacement. `clean` removes only manifest-declared files whose bytes still match their generated digest; backups are never cleaned automatically.

See the harness-specific setup and limitations under [`docs/harnesses/`](docs/harnesses/).

## Repository map

- `src/specromancy/` — CLI, artifact validators, phase handlers, templates, and reusable runtime primitives.
- `src/specromancy/resources/contracts/` — packaged version 1 pipeline contracts.
- `tests/unit/` and `tests/contract/` — focused behavior and public-contract tests.
- `docs/architecture/` — architectural decisions and trust boundaries.
- `docs/poc/implementation-plan/` — staged implementation plans.
