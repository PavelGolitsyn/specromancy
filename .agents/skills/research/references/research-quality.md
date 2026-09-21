# Research quality checklist

Use this checklist before validation and completion.

- The request interpretation distinguishes the requested outcome from possible implementation choices.
- The repository map is short, relevant, and explains why each area matters.
- Current behavior describes observable behavior and its supporting evidence.
- Constraints include applicable repository instructions, compatibility boundaries, safety rules, and durable invariants.
- Every factual claim needed for planning is traceable to an evidence ID.
- Repository evidence puts a repository-relative POSIX path in `Source` and a line number in `Location` when stable. The validator also accepts `Repository` in `Source` with the path in `Location` for compatibility.
- External evidence contains a direct HTTP(S) URL and an access date in `YYYY-MM-DD` form.
- Inferences are labeled as inferences. Assumptions and unanswered questions appear under `## Unknowns and assumptions`.
- Risks describe consequences or uncertainty, not speculative implementation work.
- Planning inputs explicitly name affected areas, acceptance criteria gaps, and recommended verification.
- No `TODO`, `TBD`, template variable, empty table row, secret-like value, or copied credential remains.
- No repository file outside `.specromancy/runs/<run-id>/` was changed.

Confidence values mean:

- `High`: directly observed in current repository content or an authoritative source.
- `Medium`: supported by indirect evidence or a reasonable inference with a stated limitation.
- `Low`: incomplete or conflicting evidence that planning must resolve.
