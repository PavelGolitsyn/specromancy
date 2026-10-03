# Test groups

The suite is split by the source of its test data:

- `features/` tests engine behavior with test-owned pipelines, skills, templates,
  and repositories. These tests must not depend on the checkout's customizable
  shipped configuration. CLI fixtures provide their own mandatory registry;
  low-level engine tests may load explicit test-owned graph paths. They assert
  exact values from their test configuration to verify the expected behavior.
- `shipped_configuration/` validates the real pipeline registry, all registered
  graphs, skills, templates, and generated harness adapters shipped by this checkout. These tests check
  validity and consistency without requiring specific configuration values.
  They must tolerate changes to the shipped configuration as long as it remains
  valid and consistent.

Run the groups independently:

```sh
python3 -m unittest discover -s tests/features -t .
python3 -m unittest discover -s tests/shipped_configuration -t .
```

Run everything with:

```sh
python3 -m unittest discover
```
