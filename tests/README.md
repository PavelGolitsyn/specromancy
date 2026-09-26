# Test groups

The suite is split by the source of its test data:

- `features/` tests runtime behavior with test-owned pipelines, skills, templates,
  and repositories. These tests must not depend on the checkout's customizable
  workflow files.
- `shipped_configuration/` validates the real pipeline, skills, templates, and
  generated harness adapters shipped by this checkout.

Run the groups independently:

```sh
python3 -m unittest discover -s tests/features -t .
python3 -m unittest discover -s tests/shipped_configuration -t .
```

Run everything with:

```sh
python3 -m unittest discover
```
