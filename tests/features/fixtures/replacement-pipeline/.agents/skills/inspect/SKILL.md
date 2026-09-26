---
name: inspect
description: Inspect a source value when the replacement pipeline requests inspection.
license: MIT
compatibility: Specromancy pipeline schema version 1.
metadata:
  role: phase
---

# Inspect

Follow the emitted action packet. Do not change repository files. Record the
observed source and selected transformation at the exact output path, then run
the packet's validation command.
