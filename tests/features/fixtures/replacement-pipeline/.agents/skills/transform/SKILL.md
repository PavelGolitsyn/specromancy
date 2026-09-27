---
name: transform
description: Transform an inspected value when the replacement pipeline requests it.
license: MIT
compatibility: Specromancy pipeline schema version 1.
metadata:
  role: phase
---

# Transform

Follow the emitted action packet. Apply only permitted workspace changes,
record the operation and result at the exact output path, and run the packet's
validation command.
