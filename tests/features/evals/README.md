# Behavior eval fixtures

These fixtures evaluate workflow behavior, not model phrasing. Each JSON file
declares a repository setup, a request, the expected phase visits, the expected
terminal or gate boundary, and semantic properties that the produced artifacts
must demonstrate.

The POC does not launch a model or harness, so execution remains manual:

1. create the declared repository state;
2. initialize the request through the CLI;
3. let the selected harness follow each emitted action packet;
4. compare persisted visits and artifacts with the fixture expectations.

`python -m unittest tests.evals.test_cases` validates the fixture format and
ensures the required behavior categories remain represented. Exact wording,
heading prose beyond the pipeline validator, and implementation style are not
evaluation criteria.

## Fixture contract

- `schema_version`: `1`;
- `id`: unique lowercase kebab-case identifier;
- `category`: stable behavior category;
- `initial_repository`: Git state and relevant files or conditions;
- `request`: user request supplied to `init`;
- `expected_phase_sequence`: ordered phase visits through the gate or terminal state;
- `expected_boundary`: persisted status plus an optional reason;
- `required_artifact_properties`: semantic assertions for manual or future automated grading.
