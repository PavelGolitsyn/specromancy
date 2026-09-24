# CLI reference

Specromancy 0.1.0 accepts global `--repo PATH`, `--format text|json`, and `--help` options on the root and leaf commands. `--version` is root-only. Text is the default; JSON always uses the stable `ok`, `command`, `message`, `data`, and `errors` envelope.

Use `RUN_ID` values containing lowercase letters, digits, and internal hyphens. Commands discover the repository from the current directory unless `--repo` is supplied.

## Command summary

| Command | Syntax and arguments | Allowed state | Reads and writes | Idempotency and recovery |
| --- | --- | --- | --- | --- |
| Version | `specromancy --version [--format json]` | Any directory | Reads packaged metadata and contracts; writes nothing. | Repeatable. Reinstall if contract validation fails. |
| Help | `specromancy --help` | Any | Reads parser metadata; writes nothing. | Repeatable. |
| Initialize | `specromancy init [--title TEXT] [--request FILE] [--id RUN_ID]` | No existing selected run | Reads request/Git identity; creates the run directory, request, manifest, and events. One of request or title must supply content. | A duplicate ID is rejected; resume the existing run or choose another ID. |
| Status | `specromancy status RUN_ID` | Existing run | Validates and reads the manifest; writes nothing. | Repeatable; repair invalid durable state rather than reinitializing. |
| Next | `specromancy next RUN_ID` | Existing noncorrupt run | Reads state and prints the next permitted action; writes nothing. | Repeatable. |
| Start phase | `specromancy phase start RUN_ID research|plan|implementation|review` | `initialized`, `research_ready`, `plan_approved`, or `implementation_ready`, respectively | Validates inputs, records baselines/subject where applicable, appends an event, updates the manifest, and prepares the artifact path. | Starting an already active or wrong phase is rejected; use `status`/`next`. |
| Complete phase | `specromancy phase complete RUN_ID research|plan|implementation|review` | Matching `*_in_progress` | Validates artifact, bindings, phase write scope, and guards; appends event and updates manifest. Review target is derived from verdict. | Equivalent accepted completion replay succeeds without a duplicate transition; changed input is rejected. |
| Fail phase | `specromancy phase fail RUN_ID PHASE --reason TEXT` | Matching in-progress phase | Appends failure evidence and moves to `blocked`; source edits remain. | Terminal; start a revised run to continue. |
| Start repair | `specromancy phase repair RUN_ID implementation` | `changes_requested`, below cycle limit, current approval/review | Records a repair baseline and re-enters implementation. | A repeated or exhausted repair is rejected. Read `review.md` before retrying. |
| Abort implementation | `specromancy phase abort RUN_ID implementation --reason TEXT` | `implementation_in_progress` | Preserves changes/evidence and moves to `blocked`. | Terminal; it is not rollback. |
| Artifact path | `specromancy artifact path RUN_ID request|research|plan|implementation|review` | Existing run | Reads manifest/path rules; writes nothing. | Repeatable. Missing not-yet-created artifacts are reported. |
| Artifact verify | `specromancy artifact verify RUN_ID [ARTIFACT]` | Existing run | Validates current files, schema, digest, and bindings; writes nothing. | Repeatable. Restore the accepted artifact or return to its phase on drift. |
| Approve plan | `specromancy approve RUN_ID plan --by IDENTITY [--note TEXT]` | `plan_ready` | Reads the validated plan digest; appends approval event and updates manifest. | Exact same approval is idempotent. A changed plan needs revocation/replanning and new approval. |
| Revoke approval | `specromancy approval revoke RUN_ID plan --by IDENTITY --reason TEXT` | Active approval before implementation | Appends revocation and returns to a replannable state. | A missing/stale approval is rejected; inspect status first. |
| Validate artifact | `specromancy validate RUN_ID [research|plan|implementation|review]` | Existing artifact, normally its active phase | Reads request/inputs/artifact and repository evidence; writes nothing. | Repeatable; fix the canonical artifact path on failure. |
| Verify command | `specromancy verify RUN_ID [--cwd PATH] [--nonblocking --reason TEXT] -- COMMAND ARG...` | `implementation_in_progress` | Runs without a shell; writes redacted `commands/CMD-NNN.json`. | Every invocation is a new record. Fix failures and record a later passing command; never edit records. |
| Inspect lock | `specromancy lock inspect RUN_ID` | Existing run | Reads `run.lock`; writes nothing. | Repeatable. Wait if the owner is active. |
| Recover lock | `specromancy lock recover RUN_ID` | Demonstrably stale lock | Validates ownership/staleness and removes only the stale lock. | No lock is an error-free no-op only when reported as such; inspect first. |
| Resume | `specromancy resume RUN_ID` | Existing nonterminal run | Validates manifest, events, repository identity, artifacts, and lock; writes recovery metadata only when required by contract. | Repeatable; follow the returned next command. |
| Cancel | `specromancy cancel RUN_ID --reason TEXT` | Any nonterminal run | Appends cancellation event and updates manifest; does not revert or delete files. | Equivalent replay is stable; terminal runs cannot be cancelled again with different meaning. |
| Generate adapters | `specromancy adapters generate [--harness NAME] [--force]` | Valid repository | Reads `AGENTS.md`/canonical skills; writes deterministic harness files and adapter manifest. | Without drift it is reproducible. Collisions fail atomically; `--force` backs up replaced files. |
| Check adapters | `specromancy adapters check [--harness NAME]` | Valid repository | Reads canonical sources, manifest, and generated files; writes nothing. | Repeatable. Regenerate after reviewed canonical changes. |
| Clean adapters | `specromancy adapters clean [--harness NAME]` | Valid adapter manifest | Deletes only manifest-owned byte-matching outputs and updates/removes their records; never deletes backups or runs. | Repeatable for already-clean managed outputs; modified files are refused. |
| List adapters | `specromancy adapters list` | Any | Reads built-in adapter metadata; writes nothing. | Repeatable. Names are `claude`, `codex`, `copilot`, `hermes`, and `opencode`. |
| Doctor | `specromancy doctor` | Repository discoverable | Reads safe installation/repository metadata; writes nothing. | Repeatable. Follow each diagnostic remediation; warnings do not expose secret values. |

## Exit codes

| Code | Name | Meaning |
| ---: | --- | --- |
| 0 | `SUCCESS` | Operation succeeded, including an accepted idempotent replay. |
| 2 | `INVALID_INPUT` | Arguments, identifiers, or requested objects are invalid. |
| 3 | `INVALID_TRANSITION` | The action is not permitted from the current state. |
| 4 | `VALIDATION_FAILED` | A contract, artifact, manifest, or repository invariant failed. |
| 5 | `APPROVAL_REQUIRED` | No active approval matches the current plan digest. |
| 6 | `EXTERNAL_COMMAND_FAILED` | A recorded external verification failed. |
| 7 | `SAFETY_REJECTED` | Confinement, secret, destructive, or ownership protection rejected the action. |
| 8 | `CONCURRENCY_CONFLICT` | Another writer owns the run or state changed concurrently. |

## Output examples

Text:

```text
$ specromancy --version
specromancy 0.1.0 (pipeline 1, run schema 1, artifact schema 1, adapter manifest 1)
```

JSON:

```json
{"command":"version","data":{"adapter_manifest_version":1,"artifact_schema_version":"1","pipeline_version":"1","run_manifest_schema_version":"1","schema_version":"1","version":"0.1.0"},"errors":[],"message":"specromancy 0.1.0 (pipeline 1, run schema 1, artifact schema 1, adapter manifest 1)","ok":true}
```

Errors use the same envelope and place the stable symbolic code, hint, path, retryability, and safe details in `errors`. For automation, test the process exit code and `ok`; do not parse prose.

## Typical phase commands

```bash
specromancy phase start RUN_ID research
specromancy artifact path RUN_ID research
specromancy validate RUN_ID research
specromancy phase complete RUN_ID research
specromancy phase start RUN_ID plan
specromancy validate RUN_ID plan
specromancy phase complete RUN_ID plan
specromancy approve RUN_ID plan --by IDENTITY
specromancy phase start RUN_ID implementation
specromancy verify RUN_ID -- python3 -m unittest discover -s tests -p 'test_*.py'
specromancy validate RUN_ID implementation
specromancy phase complete RUN_ID implementation
specromancy phase start RUN_ID review
specromancy validate RUN_ID review
specromancy phase complete RUN_ID review
```

The phase skills create the required artifact content; the CLI enforces the state and records evidence. See [Artifacts](artifacts.md) and [Troubleshooting](troubleshooting.md).
