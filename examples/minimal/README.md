# Minimal greeting example

This is the shared example for every harness guide. The checked-in application represents the passing result for [the request](request.md). The `expected/` directory contains named research, plan, and review fixtures; it is not live `.specromancy/runs` state.

Pass path:

```bash
cd examples/minimal
python3 -m unittest -v
```

Repair path in a disposable copy:

```bash
cp -R examples/minimal /tmp/specromancy-minimal
cd /tmp/specromancy-minimal
git apply fixtures/flawed.patch
python3 -m unittest -v
git apply fixtures/repair.patch
python3 -m unittest -v
```

The first test run after the flawed patch must fail on whitespace normalization. The repair patch restores the pass. Do not run the patch flow in the source checkout; the release tests exercise it in a temporary directory.

For a durable Specromancy run, return to the repository root and use:

```bash
specromancy init --id minimal-greeting --request examples/minimal/request.md
```

Then invoke `Continue run minimal-greeting.` through the selected harness as described in [Getting started](../../docs/getting-started.md).
