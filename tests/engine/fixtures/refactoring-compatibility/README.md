# Pre-extraction compatibility records

Captured on 2026-10-03 from runtime commit
`7f8aafab4a4f7b6597fded823deb5cd49889450f` using Python 3.14.4.
These records are independent of the shipped workflow. `source/` is the entire
test-owned configuration used for lifecycle, configuration, and error records.
The existing `tests.engine.unit.test_adapters.AdapterFixture` supplies adapter
inputs; its generated outputs are captured separately.

| Record | Contract |
| --- | --- |
| `canonical.json` | Exact canonical strings and SHA-256 for omitted pause, explicit false, and true; non-ASCII criteria and omitted optional defaults |
| `responses.json` | Complete pending/active actions, approval, pause/resume, terminal and blocked envelopes; array order retained |
| `diagnostics.json` | Exact configuration locations, remediation, error values, CLI exit codes and stdout/stderr routing; outcome-before-output and artifact-before-pipeline mismatch ordering |
| `states.json` | State name → relative run filename → exact UTF-8 contents, including complete `run.json`, `events.jsonl`, request and output artifacts |
| `adapters.json` | Generated relative path → exact UTF-8 content and SHA-256, including the adapter manifest |

`states.json` includes pending, active, awaiting approval, approved before
advancement, paused, completed, a recoverable manifest/event gap, and its
recovered counterpart. The examples were produced through `Engine` and
`RunStore` APIs in temporary repositories. The approved example stops at the
`after-event-append` fault hook during approval; the recoverable example stops
at `after-manifest-replace` during activation. No history was fabricated by
editing manifests or events. Replay copies these original bytes into a fresh
temporary run directory and loads them through the current API.

The store clock and random source are injected. Engine approval/block timestamps
use its existing `utc_now` reference, patched to the same fixed instant because
the engine currently has no injectable clock. Fixture file modes are explicitly
0644, so content/mode snapshots remain meaningful on different umasks.
Only absolute temporary roots and the current Python executable are replaced
with `<ROOT>` / `<PYTHON>` in response and diagnostic records. Persisted bytes,
hashes, timestamps, revisions, event types, outcomes and list order are never
normalized. No command durations occur in these snapshots; command behavior
remains covered by the existing safety tests and the added mutation-order test.

Run the comparison and replay gate with:

```sh
python3 -m unittest tests.engine.contract.test_compatibility
```

Tests never rewrite these records. `capture_canonical`, `capture_lifecycle`, and
`capture_diagnostics` in `tests.engine.contract.compatibility_support` expose
the capture scenarios for inspection. A deliberate contract change must review
both the scenario and the expected record; do not refresh records merely to make
an extraction pass. Adapter generation must also stay in `AdapterFixture`'s
temporary repository.
