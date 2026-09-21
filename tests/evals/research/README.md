# Research behavioral evaluations

These fixtures evaluate artifact properties rather than exact prose. A harness run is scored for acceptance-criteria coverage, evidence traceability, explicit uncertainty, scope discipline, and absence of repository changes outside the active run.

The case catalog covers:

- a small documented Python project;
- an unfamiliar project with misleading filenames;
- an underspecified request;
- a request requiring current external documentation; and
- a repository containing irrelevant large generated directories.

Each evaluation must produce a validator-compliant `research.md`. External browsing is required only by the current-documentation case; if browsing is unavailable, the time-sensitive fact must remain an explicit unknown.
