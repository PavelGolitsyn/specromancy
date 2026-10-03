# Staged refactoring plan

Status: Stages 01–02 implemented; Stages 03–08 remain proposed. Configuration
models, diagnostics, loading, serialization, and schema validation are separated
behind the existing public imports.
Prepared on 2026-10-03 against commit
`594c2983895903f09ac15f4b1d12a9309d39bbf8`.

The objective is to separate configuration, state decisions, persistence, and
presentation while preserving the current CLI, stored runs, pipeline hashes,
and generated adapters. Each stage should leave a usable, independently
reviewable repository. The sequence is deliberately conservative around the
run store, where seemingly mechanical changes can alter recovery behavior.

## Evidence and priorities

The checkout was clean before planning. These are responsibility observations,
not claims of confirmed runtime defects. Line counts describe the inspected
revision; reducing them is not an acceptance criterion.

| Area | Current evidence | Refactoring priority |
| --- | --- | --- |
| Run persistence | [`run_store.py`](../../specromancy/run_store.py), 1,413 lines: identity, record validation, locking, serialization, event recovery, visit creation, limits, and transitions | Separate validators, commit protocol, and state decisions in that order |
| Configuration | [`config.py`](../../specromancy/config.py), 1,134 lines: immutable records, field parsing, resource resolution, graph checks, canonicalization | Establish reusable models and explicit parsing/serialization boundaries |
| Execution | [`engine.py`](../../specromancy/engine.py), 951 lines: command orchestration, provenance, approval mutations, validation, response construction | Keep command methods as orchestration over focused collaborators |
| Adapters | [`adapters.py`](../../specromancy/adapters.py), 763 lines: discovery, rendering, hashes, ownership, drift detection, writes | Separate source capture, rendering, and filesystem ownership |
| CLI | [`cli.py`](../../specromancy/cli.py), 452 lines: parser, bootstrap, pipeline selection, dispatch, formatting; metadata reads argparse internals | Isolate selection and make command metadata explicit |
| Hashing | Configuration uses `json.dumps` defaults for Unicode escaping; [`hashing.py`](../../specromancy/hashing.py) explicitly uses `ensure_ascii=False` | Preserve each existing byte contract; do not merge serializers blindly |
| Import direction | `config._Loader.parse_validator` imports schema helpers from `validation` locally; `validation` imports `ValidatorConfig` from `config` | Remove the structural cycle through leaf model/schema modules |
| Test coverage boundaries | Architecture tests enumerate generic filenames; subprocess and dependency checks use top-level `glob("*.py")` | Cover newly extracted modules before moving implementation |
| Repeated filesystem code | Run, artifact, and adapter writers have similar temporary-file code but different hooks, checks, and directory syncing | Preserve specialized policies; share primitives only where equivalent |

Small focused modules such as `approvals.py`, `actions.py`, `graph.py`,
`registry.py`, and `locking.py` are useful existing boundaries. Keep them unless
a specific stage demonstrates a clearer responsibility split.

## Stage sequence

| Stage | Deliverable | Prerequisites | Relative risk |
| --- | --- | --- | --- |
| [01 — Compatibility baseline](01-compatibility-baseline.md) | Contract matrix, deterministic examples, complete architecture scans | None | Low |
| [02 — Configuration boundaries](02-configuration-boundaries.md) | Models, parsing, schema validation, and canonicalization separated | 01 | Medium: hashes and diagnostics |
| [03 — Persisted records](03-persisted-records.md) | Shared record types, selectors, and runtime validators | 01–02 | Medium: accepted persisted data |
| [04 — Persistence protocol](04-persistence-protocol.md) | One internal implementation of durable commits and recovery | 03 | High: fault and lock boundaries |
| [05 — Visit transitions](05-visit-transitions.md) | Explicit state decisions separated from disk effects | 04 | High: idempotency and atomic successors |
| [06 — Engine orchestration](06-engine-orchestration.md) | Validation, provenance, approvals, and responses separated | 02–05 | High: gate ordering |
| [07 — CLI and adapters](07-cli-and-adapters.md) | Explicit command metadata and adapter generation boundaries | 02, 06 | Medium: CLI output and ownership |
| [08 — Integration and closeout](08-integration-and-closeout.md) | Compatibility replay, complete documentation, release evidence | All previous stages | Medium |

Execute in the listed order. A stage may contain several small changes; do not
combine all stages into one rewrite. After each stage, record completed tasks,
verification results, deviations, and any deferred issues in its document.
Each stage document records its completed work and verification results.

## Contracts that every stage must preserve

1. Python 3.11+ support, standard-library runtime only, and execution from an
   unpacked source checkout without installation.
2. Workflow policy remains in `workflow/` and canonical procedures in
   `.agents/skills/`. Generic modules must not acquire shipped phase names.
3. CLI command names, flags, aliases, exit codes, JSON envelopes, output streams,
   action packets, and documented diagnostics remain compatible.
4. Existing schema-version-1 runs, events, pipelines, registries, and adapter
   manifests remain usable without migration or regeneration caused solely by
   internal moves. Preserve canonical bytes, hash inputs, defaults, and ordering.
5. A visit completes and prepares its successor in one committed manifest
   mutation. Loop limits, pauses, retry behavior, and approval invalidation
   retain their existing event/revision semantics.
6. Preserve the actual recovery protocol: an atomic manifest replacement is
   followed by an event append; a permitted one-revision gap is recovered on
   load. This is not a filesystem transaction spanning both files. Other
   disagreement remains corruption, and stale locks are not expired by age.
7. Request artifacts and completed outputs stay immutable. Read-only policies
   compare content snapshots, including files already dirty at visit start.
8. Runtime writes and cleanup remain inside the ownership rules in
   [`AGENTS.md`](../../AGENTS.md) and the
   [public contracts](../poc-v3/contracts.md). The CLI never deletes, resets,
   stages, or commits repository work; adapter cleanup requires manifest ownership.
9. Runtime decisions come from validated persisted state and configuration,
   never conversation history. Existing runs resolve their saved pipeline even
   if its registration is later removed, while a valid registry remains required.

## Intended module boundaries

The concrete proposed files are described in each stage. Keep existing public
modules as compatibility entry points; prefer ordinary functions and small
records over frameworks, plugin systems, or speculative abstractions.

```text
CLI command definitions / selection / formatting
                  |
                  v
Engine command orchestration ------> action and status responses
       |                |
       v                v
validation/provenance   approval and visit decisions
       |                |
       +-------> RunStore compatibility facade
                         |
                         v
                 persistence commit protocol
                         |
                         v
              locks / artifacts / filesystem

Configuration facade -> parser -> models / graph / schema subset
                              -> canonical pipeline serialization
Adapter facade -> source capture -> rendering -> ownership / writes
```

Configuration models and record validators must not import the CLI or engine.
Persistence must not import response builders or harness rendering. Proposed
internal modules are implementation details, not additional public APIs.

## Verification policy

Use the focused commands in each stage, then run the complete suite and adapter
check before considering that stage done:

```sh
python -m unittest discover
bin/specromancy adapters generate --check
git diff --check
```

If the local executable is `python3`, use the equivalent
`python3 -m unittest discover` and record its version. Do not change runtime
dependencies or install a test framework to execute this plan. Generation
experiments and destructive fixture scenarios belong in temporary test-owned
repositories, not the working checkout.

Behavior tests remain under `tests/features/` with test-owned workflows.
`tests/shipped_configuration/` checks the validity and consistency of the
customizable checkout without freezing its phase names or values. Add tests
only for meaningful contract gaps or new responsibility boundaries; do not
duplicate every private helper with a test that repeats its implementation.

Baseline adapter checking passed. The initial `python -m unittest discover`
could not start because this shell has no `python` executable; the equivalent
full-suite result using Python 3.14.4 is recorded in Stage 01.

## Scope limits and decision rules

This plan does not add a database, remote storage, new harnesses, authentication,
parallel graph execution, run migrations, or a general JSON Schema library.
Do not change workflow configuration or canonical procedures to accommodate an
internal refactor. Do not introduce a broad type-checking or formatting migration.

If characterization reveals a correctness defect, record a reproducer and its
contract impact. Handle its fix as an explicit, separately reviewed behavior
change; do not silently preserve a known violation or hide its repair in a move.
Questions about stale validation evidence, malformed nested records, and
interruption during initialization deserve investigation, not unsupported claims
that current tests prove them safe.

At any failed gate, stop advancing stages and repair or revert only the current
code change through the normal review process. Never roll back by rewriting run
artifacts or deleting repository work. Keeping wire formats and hashes stable
makes code rollback practical; any proposed incompatible format change requires
a separate versioning and compatibility plan.
