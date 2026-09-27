# Stage 02 — Pipeline configuration and graph validation

## Outcome

Load an arbitrary declarative pipeline and reject configurations that cannot be executed safely or deterministically.

## Files introduced or completed

```text
specromancy/pipeline.toml
specromancy/config.py
specromancy/graph.py
specromancy/schemas/pipeline.schema.json
tests/unit/test_config.py
tests/unit/test_graph.py
tests/fixtures/config-*/
```

## Configuration model

Top-level fields:

- `schema_version`: integer format version.
- `id`: stable pipeline identifier.
- `version`: author-controlled pipeline revision.
- `start`: initial phase ID.
- `terminal_outcomes`: outcomes that complete or stop a run.
- `artifact_pattern`: default output path pattern.
- `phases`: ordered phase definitions; ordering is for display only, transitions control execution.

Every phase declares:

- `id` and `skill`;
- symbolic `inputs`;
- `output_name` and optional template;
- `mutation` policy;
- completion criteria shown to the agent;
- validator rules and deterministic commands;
- approval conditions;
- stop conditions;
- transitions keyed by outcome;
- visit or edge bounds for cycles.

Example shape:

```toml
schema_version = 1
id = "default"
version = 1
start = "research"
artifact_pattern = "artifacts/{visit:03}-{phase}.md"

[[phases]]
id = "research"
skill = "research"
inputs = ["request"]
output_name = "{visit:03}-research.md"
output_template = "templates/research.md"
mutation = "read-only"
required_headings = ["Summary", "Evidence", "Open Questions"]
max_visits = 1

[[phases.transitions]]
outcome = "validated"
target = "plan"
```

Terminal transitions use a terminal outcome rather than a special fake phase target.

## Work items

### 1. Parse into immutable domain objects

Use `tomllib` for syntax and frozen dataclasses for validated configuration. Do not allow engine code to access arbitrary raw dictionaries. Normalize paths relative to the pipeline file and retain both the declared and resolved form where diagnostics need them.

### 2. Validate identifiers and paths

- Phase and outcome IDs match `^[a-z0-9]+(?:-[a-z0-9]+)*$`.
- IDs are unique and cannot use reserved CLI command names.
- Skill paths resolve to `.agents/skills/<skill>/SKILL.md` inside the repository.
- Template and validator paths cannot escape the repository through `..` or symlinks.
- Output patterns resolve inside the current run directory.
- Referenced files exist at configuration-load time.

### 3. Validate the graph

Reject:

- missing start phase;
- duplicate phase IDs;
- transitions to unknown phases;
- duplicate outcomes within a phase;
- phases unreachable from the start;
- non-terminal phases with no outgoing transition;
- terminal outcomes used as phase IDs;
- cycles without a finite `max_visits` or `max_traversals` bound;
- bounds less than one;
- input references that can never have a producer on any incoming route.

Cycles are permitted. Use strongly connected components or depth-first cycle detection, then require every cyclic component to have a mechanical bound.

### 4. Validate phase contracts

Every phase must have exactly one declared primary output for the POC. It must declare:

- a mutation policy;
- at least one completion criterion;
- a validator type;
- at least one possible outcome;
- approval and stop condition lists, even when empty.

Supported mutation policies:

- `read-only`;
- `repository-write`;
- `allowlist`, with one or more repository-relative glob patterns.

Supported POC validators:

- `markdown`;
- `json`;
- `file` for existence and non-empty checks.

### 5. Canonicalize and hash

Serialize the validated model into canonical JSON with sorted keys and compact separators, then compute a SHA-256 configuration hash. Store this hash in each run so a changed pipeline cannot silently alter an in-progress run.

An in-progress run with a mismatched hash must stop with an actionable diagnostic. Migration is out of scope; users may restore the old configuration or start a new run.

### 6. Provide diagnostics

Configuration failures should report:

- a stable error code;
- configuration file path;
- phase and field, where applicable;
- invalid value;
- concise remediation.

Do not emit a Python traceback for expected configuration errors.

## Tests

Add table-driven fixtures for:

- smallest valid one-phase pipeline;
- valid branch and valid bounded loop;
- duplicate, missing, and unreachable phases;
- unknown transition targets;
- unbounded cycles;
- unsafe paths;
- missing skill and template;
- invalid mutation policies;
- stable hash independent of TOML key order;
- hash change after a semantic configuration edit.

## Exit criteria

- The default configuration loads into immutable domain objects.
- Invalid graphs fail before a run is created.
- The loader contains no checks for example phase names.
- A fixture with unrelated phase names passes validation.
- Configuration hashes are deterministic.

