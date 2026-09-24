# Getting started

This walkthrough uses the repository's `examples/minimal` greeting change and is designed to take less than fifteen minutes. Specromancy 0.1.0 is a proof of concept; use a disposable branch or worktree.

## 1. Verify prerequisites and install

You need Git, Python 3.11 or newer, and a repository containing the canonical `.agents/skills/` directory. From the Specromancy checkout:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/specromancy --version
.venv/bin/specromancy doctor
```

On Windows, use `.venv\Scripts\python` and `.venv\Scripts\specromancy`. `doctor` is read-only. Resolve failed diagnostics before continuing; warnings identify optional harnesses or recoverable local state.

## 2. Generate and verify discovery adapters

Generate every harness surface, then verify it is byte-for-byte current:

```bash
specromancy adapters generate
specromancy adapters check
specromancy adapters list
```

Generation refuses collisions. Do not use `--force` unless replacing a known user-authored file is intentional; forced replacements are backed up.

## 3. Initialize the minimal request

The same request is used by every harness guide:

```bash
specromancy init --id minimal-greeting --request examples/minimal/request.md
specromancy status minimal-greeting
specromancy next minimal-greeting
```

This creates `.specromancy/runs/minimal-greeting/`. Run state belongs there, not in chat. If that ID already exists, choose another ID and substitute it in the remaining commands.

## 4. Invoke the pipeline

Open your selected harness at the repository root and invoke its pipeline skill with: `Continue run minimal-greeting.` See the guides for [Codex](harnesses/codex.md), [Claude Code](harnesses/claude-code.md), [GitHub Copilot](harnesses/github-copilot.md), [Hermes](harnesses/hermes.md), or [OpenCode](harnesses/opencode.md).

The pipeline starts research, creates and validates `research.md`, creates and validates `plan.md`, and stops at `plan_ready`. It must not treat conversational assent as approval.

## 5. Approve the exact plan

Inspect the plan before recording approval:

```bash
specromancy artifact path minimal-greeting plan
specromancy artifact verify minimal-greeting plan
specromancy approve minimal-greeting plan --by YOUR_IDENTITY
```

Approval binds the identity to the current plan digest. Editing or replacing the plan makes that approval stale. Continue the pipeline only after approval.

## 6. Inspect progress and evidence

```bash
specromancy status minimal-greeting --format json
specromancy artifact verify minimal-greeting
specromancy lock inspect minimal-greeting
```

Review `.specromancy/runs/minimal-greeting/implementation.md`, the redacted `commands/CMD-NNN.json` records, and `review.md`. A successful run ends at `passed`; requested changes return through one of at most three repair cycles.

## 7. Finish, cancel, or clean up

Let the pipeline complete a passing review. To stop a nonterminal run without deleting source edits or artifacts:

```bash
specromancy cancel minimal-greeting --reason "No longer needed"
```

To remove generated harness files safely:

```bash
specromancy adapters clean
```

Cleanup removes only manifest-owned files whose bytes still match the generated digest. It leaves modified generated files, backups, user source, and `.specromancy/runs/` intact. See [Concepts](concepts.md), [Artifacts](artifacts.md), [CLI reference](cli.md), and [Troubleshooting](troubleshooting.md) for the full model.
