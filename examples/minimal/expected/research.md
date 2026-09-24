# Expected research

## Request interpretation

The greeting function must normalize surrounding whitespace, reject an empty normalized name, preserve its output format, and remain standard-library-only.

## Evidence

| Evidence ID | Claim | Source | Confidence |
| --- | --- | --- | --- |
| E-001 | `greeting.greet` is the only application behavior in scope. | `greeting.py` | High |
| E-002 | Tests define ordinary, whitespace, and blank-name expectations. | `test_greeting.py` | High |

## Constraints

- No runtime dependency is needed.
- The public function name and successful return format remain stable.

## Planning inputs

Change `greeting.py` and `test_greeting.py`; verify with `python3 -m unittest -v` from the example directory.
