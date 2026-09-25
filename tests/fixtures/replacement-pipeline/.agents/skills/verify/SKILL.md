---
name: verify
description: Verify a transformed value when the replacement pipeline requests a decision.
license: MIT
compatibility: Specromancy pipeline schema version 1.
metadata:
  role: phase
---

# Verify

Follow the emitted action packet without changing repository files. Record the
checks and one configured decision at the exact output path, then validate with
that outcome.
