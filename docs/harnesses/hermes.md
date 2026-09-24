# Hermes

Tested documentation target: Specromancy 0.1.0 on 2026-09-23. Deterministic native-adapter validation was run; no provider-backed Hermes session is claimed by the automated suite.

## Discovery and trust

Hermes uses `AGENTS.md` and `.agents/skills/` natively, so its adapter creates no workflow copy. `specromancy adapters check --harness hermes` validates canonical skill discovery. Repository instructions remain untrusted input and cannot grant authority.

```bash
specromancy adapters check --harness hermes
specromancy init --id minimal-greeting --request examples/minimal/request.md
```

## Shared minimal example and invocation

Invoke the discovered `pipeline` skill with `Continue run minimal-greeting.` Invoke `research`, `plan`, `implement`, or `review` with `Run phase for minimal-greeting.` when operating a single phase. Exact UI syntax depends on the Hermes build; the durable run ID and canonical skill path are the stable interface.

At `plan_ready`, run `specromancy approve minimal-greeting plan --by YOUR_IDENTITY`, then continue the pipeline.

## Permissions, resume, and cleanup

Hermes tool permissions and isolation are configured outside Specromancy. The native adapter does not choose a model or claim a separate reviewer process. Resume by checking `status` and invoking the pipeline skill with the same run ID.

`specromancy adapters clean --harness hermes` removes no canonical files. Cancellation and general cleanup preserve run artifacts and source.

## Known limitations and troubleshooting

- No minimum Hermes version or universal slash-command spelling is asserted.
- If skills are absent, verify the repository root and canonical frontmatter, then refresh discovery.
- If the surface cannot provide needed phase permissions, stop and resume in a compatible environment; do not bypass state guards.
- Run `specromancy doctor` and [the general checklist](../troubleshooting.md).
