# Stage 8: Validation, Evaluations, and Security

## Objective

Demonstrate that the POC is reliable enough to evaluate: deterministic contracts catch structural failures, behavioral evaluations catch workflow failures, and safety checks prevent obvious misuse or data loss.

## Dependencies

- Stages 0 through 7.

## Deliverables

- `src/specromancy/security.py`
- `src/specromancy/redaction.py`
- `src/specromancy/evals.py`
- `tests/security/`
- `tests/integration/`
- `tests/evals/cases/`
- `tests/evals/expected/`
- `docs/testing.md`
- `docs/security.md`
- CI workflows for supported operating systems and Python versions
- `specromancy doctor` command

## Validation layers

### Layer 1: Static repository checks

- Parse all canonical skill frontmatter.
- Enforce skill directory/name equality.
- Ensure descriptions state what the skill does and when it applies.
- Check referenced files exist and remain inside their skill directory.
- Reject deep or cyclic reference chains in canonical skills.
- Validate all JSON contracts and templates.
- Run adapter drift detection.
- Check documentation links and example commands.

### Layer 2: Unit and contract tests

- State transitions and phase guards.
- Artifact parsers and validators.
- Approval digest binding.
- Git snapshot and dirty-worktree behavior.
- Atomic writes, locks, event replay, and recovery.
- Adapter generation and collision handling.
- Stable exit codes and JSON error envelopes.

### Layer 3: End-to-end fixture runs

Create small fixture repositories representing:

- Python library bug fix;
- TypeScript feature with tests and docs;
- dirty worktree with unrelated edits;
- migration requiring explicit approval;
- underspecified request that must block;
- repair loop that passes;
- repair loop that exhausts its bound.

End-to-end tests may use pre-authored artifacts to test deterministic orchestration without model access. Harness smoke runs are a separate optional suite.

### Layer 4: Behavioral evaluations

For each phase, define cases with:

- repository fixture and initial state;
- user request;
- allowed tools and mutations;
- required artifact properties;
- forbidden behaviors;
- scoring rubric;
- human review notes where deterministic assertions are insufficient.

Store normalized evaluation results by harness and version without treating one model run as definitive.

## Evaluation metrics

Research:

- evidence traceability;
- relevant repository coverage;
- explicit assumptions and unknowns;
- mutation count, expected to be zero outside run artifacts.

Plan:

- requirement coverage;
- verification coverage;
- file/action specificity;
- unnecessary scope;
- approval-sensitive change detection.

Implementation:

- tests passing;
- requirement fulfillment;
- plan adherence;
- unrelated-change preservation;
- unexplained changed paths;
- deviation accuracy.

Review:

- true-positive and false-positive findings;
- severity correctness;
- evidence precision;
- requirement coverage;
- verdict consistency;
- mutation count, expected to be zero outside run artifacts.

Pipeline:

- successful resume rate;
- invalid-transition rejection;
- repair-loop termination;
- adapter portability;
- complete audit trail.

## Security work

### Threat model

Document at least:

- malicious repository instructions or skills;
- prompt injection in source files and external research;
- command injection through request text or paths;
- path traversal and symlink escape;
- secrets copied into artifacts or command logs;
- destructive Git or filesystem actions;
- untrusted generated adapter overwrite;
- stale approval or review replay;
- concurrent state corruption;
- compromised third-party skills.

### Required controls

1. Never interpolate request text into shell commands.
2. Run subprocesses with argument arrays and `shell=False`.
3. Constrain all managed paths to the discovered repository root.
4. Use allowlisted artifact names and phase identifiers.
5. Redact common token, credential, and private-key patterns before persistence.
6. Cap captured command output and artifact size.
7. Bind approvals and reviews to content digests.
8. Require explicit user approval for destructive or externally consequential actions.
9. Refuse automatic execution of scripts from untrusted installed skills.
10. Preserve user data; cancellation and cleanup must not delete source changes.

Secret scanning is defense in depth, not permission to read secrets. Skills must instruct agents not to open likely secret files unless the task explicitly requires it and authorization is clear.

## `doctor` command

`specromancy doctor` reports:

- Python and package versions;
- Git availability and repository discovery;
- write access to the run directory;
- contract resource integrity;
- adapter status;
- canonical skill validity;
- stale locks;
- unsupported or risky configuration;
- optional harness executables found on `PATH`, without requiring them.

It must not print environment variables, tokens, or full user configuration.

## CI matrix

Minimum:

- Ubuntu, macOS, and Windows.
- Python 3.11 and the latest stable supported Python.
- Source-checkout tests and installed-wheel tests.
- Unit, contract, integration, security, adapter drift, and packaging jobs.

Optional credentialed harness smoke tests must be separate, opt-in, and nonblocking for external contributors.

## Implementation tasks

1. Complete the threat model before enabling command execution records by default.
2. Implement path, redaction, size, and subprocess safety helpers.
3. Add adversarial unit tests for all input boundaries.
4. Build deterministic end-to-end fixture runs.
5. Define evaluation case and result schemas.
6. Add phase-specific scorers based primarily on artifact structure and repository outcomes.
7. Implement `doctor` and JSON output.
8. Configure the CI matrix and artifact retention for failed tests.
9. Run manual smoke tests on each harness and record versioned observations.
10. Triage failures into contract defect, skill defect, harness limitation, or model variability.

## Exit criteria

- All deterministic tests pass on the supported OS/Python matrix.
- Security tests cover path traversal, command injection, secret redaction, stale digest replay, and destructive cleanup.
- Every phase has at least three behavioral evaluation cases, including one failure case.
- A full POC run and repair run succeed from pre-authored fixture artifacts.
- Manual smoke results exist for each target harness.
- Known harness limitations are documented rather than hidden behind adapter behavior.

## Risks and mitigations

- **Brittle prose grading:** assert observable properties and use rubrics rather than exact text comparison.
- **Credential cost and availability:** keep deterministic tests provider-free and credentialed smoke tests optional.
- **Security scanner false confidence:** document scanner limits and retain explicit trust and approval boundaries.
- **Cross-platform flakiness:** isolate filesystem, newline, process, and executable-bit expectations in platform-aware tests.

