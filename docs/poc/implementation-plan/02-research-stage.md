# Stage 2: Research Stage

## Objective

Implement a repeatable, evidence-backed research phase that turns an initial request into a durable description of the problem, repository context, constraints, evidence, uncertainties, and planning inputs.

## Dependencies

- Stage 0 artifact and state contracts.
- Stage 1 package, I/O, hashing, and test helpers.

## Deliverables

- `.agents/skills/research/SKILL.md`
- `.agents/skills/research/references/research-quality.md`
- `.agents/skills/research/assets/research-template.md`
- `src/specromancy/phases/research.py`
- `src/specromancy/artifacts/frontmatter.py`
- `src/specromancy/artifacts/research.py`
- `specromancy/templates/research.md`
- `tests/contract/test_research_artifact.py`
- `tests/evals/research/`

## Input and output contract

Inputs:

- `request.md`, including goal and acceptance criteria if known.
- Repository contents and Git metadata.
- Root and applicable nested instructions.
- Optional user-provided sources.

Output:

- `.specromancy/runs/<run-id>/research.md`

Required sections:

1. `## Request interpretation`
2. `## Repository map`
3. `## Current behavior`
4. `## Constraints and invariants`
5. `## Evidence`
6. `## Unknowns and assumptions`
7. `## Risks`
8. `## Planning inputs`

The evidence section uses a table containing evidence ID, claim, source, location, and confidence. Repository evidence uses relative file paths and line numbers when stable. External evidence uses direct URLs and access dates.

## Skill behavior

The research skill must:

1. Confirm the active run and transition it to `research_in_progress`.
2. Read the request before exploring the repository.
3. Inspect repository instructions and identify the build system and relevant subsystem.
4. Prefer targeted search over indiscriminate file loading.
5. Separate facts, inferences, and assumptions.
6. Use external research only when required by the request or when facts are time-sensitive.
7. Record unresolved questions without fabricating answers.
8. Avoid source-code modifications.
9. Write `research.md` from the template.
10. Run the research validator and repair structural failures.
11. Complete the phase only when validation succeeds.

The skill description must include clear positive triggers such as researching a change, understanding an unfamiliar codebase, gathering requirements, or preparing evidence for a plan. It must say not to use the skill for implementation.

## Validator behavior

The research validator checks:

- frontmatter version, run ID, stage, and status;
- every required heading occurs exactly once and in the defined order;
- at least one repository evidence entry exists;
- every stated assumption appears in the assumptions section;
- planning inputs include affected areas, acceptance criteria gaps, and recommended verification;
- no placeholder markers such as `TODO`, `TBD`, or empty template rows remain;
- the artifact does not contain likely secrets;
- all repository paths are relative and remain inside the repository;
- cited local files exist at validation time.

The POC should warn, but not fail, when line numbers drift after subsequent implementation.

## Implementation tasks

1. Implement the restricted frontmatter parser shared by all artifacts.
2. Implement heading-order and table-row helpers.
3. Create the research template and quality reference.
4. Write the canonical skill using imperative steps and explicit inputs/outputs.
5. Add phase start and completion handlers.
6. Bind the research artifact digest into `run.json` at completion.
7. Append start, validation, completion, and failure events to `events.jsonl`.
8. Add `specromancy artifact path <run-id> research` and `specromancy validate <run-id> research` behavior.
9. Reject completion if repository files other than the run directory changed during a research-only fixture test.
10. Add helpful remediation text for every validation error.

## Tests and evaluations

Contract tests:

- valid minimal research artifact;
- missing or duplicated heading;
- malformed evidence table;
- unknown run ID;
- local evidence path outside the repository;
- placeholder content left behind;
- secret-like value detection;
- completion from an invalid prior state;
- repeated completion with unchanged content.

Behavioral evaluation fixtures:

- a small documented Python project;
- an unfamiliar project with misleading filenames;
- an underspecified request;
- a request requiring current external documentation;
- a repository containing irrelevant large generated directories.

Evaluate artifact properties, not exact prose. Score coverage of acceptance criteria, evidence traceability, explicit uncertainty, scope discipline, and absence of code changes.

## Exit criteria

- A valid `request.md` can produce a contract-compliant `research.md` through the skill.
- Invalid evidence and incomplete sections prevent phase completion.
- The phase performs no repository mutation outside its run directory.
- The artifact contains enough grounded information for planning without access to the originating conversation.
- Research behavior is consistent from at least two harnesses before full adapter work begins.

## Risks and mitigations

- **Research becomes a code dump:** cap the repository map and require relevance explanations.
- **Unsupported claims:** require evidence IDs and distinguish inference from fact.
- **Web availability differences:** external browsing is optional; unknown current facts must remain explicit unknowns when unavailable.
- **Secret leakage:** scan artifacts before persistence and instruct the skill to summarize sensitive configuration rather than copy it.

