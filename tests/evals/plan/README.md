# Plan behavioral evaluations

These cases evaluate planning behavior rather than deterministic artifact parsing. A runner should provide the request, validated research, manifest requirements, and repository fixture, then score the produced plan using `cases.json`.

Score each case from 0 to 2 for completeness, minimality, testability, traceability, risk recognition, and absence of implementation edits. A passing plan has no zero score, resolves blocking choices before approval, and changes no repository file outside its active run directory.
