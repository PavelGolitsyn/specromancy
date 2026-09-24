# Run artifacts

Each run lives at `.specromancy/runs/<run-id>/`. Treat this directory as an auditable record: inspect it freely, but use the CLI and canonical skills to create transitions rather than editing `run.json` or `events.jsonl` by hand.

## Layout

| Path | Role |
| --- | --- |
| `request.md` | Immutable normalized request and extracted requirement source. |
| `research.md` | Repository-grounded evidence, constraints, unknowns, and planning inputs. |
| `plan.md` | Requirement traceability, `CHG-NNN` actions, verification, risks, and decisions. |
| `implementation.md` | Accounting for plan items, changed paths, deviations, commands, and repair findings. |
| `review.md` | Independent verdict, `REV-NNN` findings, requirement coverage, and repair guidance. |
| `run.json` | Current validated state, digests, approvals, baselines, changed files, and review cycle. |
| `events.jsonl` | Append-only events from which the state projection is checked. |
| `commands/CMD-NNN.json` | Redacted argv, cwd, blocking policy, exit code, and bounded output for verification. |
| `run.lock` | Temporary exclusive-writer record; absent when no mutation owns the run. |

## Frontmatter and bindings

Markdown artifacts use five restricted scalar fields: `schema-version`, `run-id`, `stage`, `status`, and `created-at`. Version 1 intentionally does not accept general YAML. Phase validators then require ordered sections and stable identifiers.

Accepted artifact records store SHA-256 digests. Research binds to the request; a plan binds to research; implementation binds to the approved plan and current repository subject; review binds to the implementation subject. Approval records bind an identity to the exact plan digest. Completion rechecks bindings immediately before transition.

## Command records

`specromancy verify RUN_ID -- COMMAND ARG...` executes an argument array without shell interpolation and writes the next `CMD-NNN.json`. Output is redacted before bounded persistence. A blocking command must exit zero. A failed nonblocking command is allowed only with `--nonblocking --reason TEXT` and must be disclosed in `implementation.md`.

Do not place credentials in argv. Redaction is defense in depth, not permission to access secrets.

## Inspection and recovery

```bash
specromancy status RUN_ID --format json
specromancy artifact path RUN_ID implementation
specromancy artifact verify RUN_ID
specromancy lock inspect RUN_ID
specromancy resume RUN_ID
```

`artifact verify` detects digest or binding drift. `resume` validates the manifest, event projection, repository identity, current artifacts, and lock state before reporting the next action. If a lock is proven stale, inspect it first and then run `lock recover`; never delete it blindly.

Keep completed run directories as evidence or archive them as a unit. Cancellation does not delete them. Generated adapter cleanup does not touch them. There is no silent schema migration; an unsupported future version requires a compatible Specromancy release. Version 1 is currently the only known run format, so older-version read-only inspection has no historical case yet.
