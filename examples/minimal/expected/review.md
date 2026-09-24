# Expected review after the flawed patch

## Verdict

changes_requested

## Findings

| Finding ID | Severity | Blocking | Title | Location | Observed | Expected | Impact | Repair guidance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| REV-001 | medium | Yes | Whitespace normalization was removed | `greeting.py:7` | The flawed patch uses the input verbatim. | REQ-001 and CHG-001 require trimming before validation and formatting. | Padded names produce changed output and the focused suite fails. | Restore `name.strip()` and rerun the example tests. |

## Expected repair result

Applying `fixtures/repair.patch` restores the normalization line and all three tests pass.
