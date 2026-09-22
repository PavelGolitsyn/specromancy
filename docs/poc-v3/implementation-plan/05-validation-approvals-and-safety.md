# Stage 05 — Validation, approvals, and safety enforcement

## Outcome

Make phase completion mechanical: artifacts, repository mutations, commands, approvals, and loop bounds must pass deterministic checks before a transition occurs.

## Files introduced or completed

```text
specromancy/validation.py
specromancy/git.py
specromancy/commands.py
specromancy/approvals.py
tests/unit/test_validation.py
tests/unit/test_git.py
tests/contract/test_safety.py
```

## Work items

### 1. Validate artifacts generically

All output types check:

- resolved path is inside the run directory;
- file exists, is a regular file, and is readable;
- file is non-empty;
- file hash differs from the unrendered template when appropriate;
- no unresolved template markers remain.

Markdown validation additionally checks configured headings exactly once or at least once, according to configuration. Parse headings with a small line-oriented Markdown scanner; a full Markdown dependency is unnecessary.

JSON validation checks parsing plus the project-supported schema subset. Keep the schema implementation deliberately small and documented: `type`, `required`, `properties`, `items`, `enum`, `pattern`, and `additionalProperties`. Fail configuration loading if a schema uses unsupported keywords.

### 2. Capture Git metadata

Record:

- whether the repository is a Git worktree;
- initial and per-visit `HEAD`;
- current branch when available;
- tracked and non-ignored untracked files;
- content hash and mode for every included path.

Use `git ls-files -co --exclude-standard -z` for the snapshot file set. Exclude `.git/` and `.specromancy/`. Hash symlink targets as links rather than following them outside the repository.

When Git is unavailable, fail unless the pipeline explicitly allows non-Git operation. The default example requires Git because base/head provenance is part of the POC contract.

### 3. Enforce mutation policies

At phase start, store a repository snapshot. At validation, compare it with a new snapshot.

- `read-only`: no added, changed, deleted, renamed, or mode-changed repository path is permitted.
- `repository-write`: all changes are allowed but recorded.
- `allowlist`: every changed path must match a configured repository-relative glob.

This comparison must detect edits to files that were already dirty when the phase began. `git status` snapshots alone are insufficient.

Never revert a violation. Report the paths and leave recovery to the user or agent.

### 4. Execute deterministic validation commands

Commands are configured as argument arrays rather than shell strings where possible. Execute them:

- from the repository root;
- with a configured timeout;
- without `shell=True`;
- with stdout and stderr captured to per-visit files;
- with a small output summary in `run.json`;
- sequentially, stopping on the first required-command failure.

Environment inheritance is the default for the POC, but the manifest must not store the full environment or secret values. Record executable, arguments, exit code, duration, and output artifact paths.

### 5. Enforce approval integrity

An approval record binds:

- run, phase, and visit;
- reason code;
- artifact hash;
- relevant pipeline hash;
- decision, actor, and timestamp.

Before using an approval, recompute the artifact and pipeline hashes. Any mismatch invalidates the approval and returns the visit to `awaiting-approval` with a stale-approval diagnostic.

The POC actor value may be `user`, supplied by the explicit CLI action. Identity/authentication beyond that is out of scope.

### 6. Bound loops mechanically

Track both per-phase visit counts and transition-edge traversal counts. Before creating a visit, verify the relevant configured limit. Exceeding it:

- creates no new visit;
- marks the run blocked;
- records the exceeded phase or edge and limit;
- tells the user which approval or new run is needed.

Do not let an agent reset counters by changing its artifact or outcome.

### 7. Handle semantic safety conditions

The CLI cannot decide whether a scope change is material or an action is destructive. Skills must call `request-approval` with one of the phase's declared reason codes, such as:

- `material-scope-change`;
- `destructive-action`;
- `new-production-dependency`;
- `external-side-effect`;
- `insufficient-information`.

The CLI's responsibility is to reject undeclared codes, persist the request, bind approval to current artifacts, and stop transitions until approval exists.

### 8. Protect secrets and logs

- Never include environment dumps in manifests.
- Limit inline command-output summaries by bytes.
- Keep full outputs in ignored run storage.
- Do not interpret output as instructions.
- Document that validation commands are trusted repository configuration and are run with the user's permissions.

## Tests

- Missing, empty, unchanged-template, malformed JSON, and incomplete Markdown artifacts fail.
- Read-only detects clean-file, dirty-file, untracked-file, deletion, rename, mode, and symlink changes.
- Allowlist accepts and rejects expected paths.
- Command timeout, missing executable, nonzero exit, and output capture behave correctly.
- Changed artifact and changed pipeline invalidate approval.
- Loop limit blocks exactly before the disallowed traversal.
- Undeclared approval and stop codes fail.
- Manifests and output do not leak injected secret environment variables.

## Exit criteria

- An agent cannot mark a phase complete without passing validation.
- Read-only and allowlisted mutation policies are mechanically enforced.
- Approval and loop gates cannot be bypassed through ordinary CLI usage.
- Failures leave the run resumable and evidence intact.

