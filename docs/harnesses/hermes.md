# Hermes

## Setup, trust, and discovery

Hermes consumes canonical `AGENTS.md` and `.agents/skills` without generated skill copies. Project skills are deliberately disabled until the repository is trusted. Review the checkout, then run once from inside it:

```bash
hermes skills trust
specromancy adapters generate --harness hermes
specromancy adapters check --harness hermes
```

The generate command records native-adapter metadata but creates no Hermes workflow file and never writes user-global Hermes configuration. Hermes documents project discovery, trust, and noninteractive behavior at <https://hermes-agent.nousresearch.com/docs/user-guide/features/skills>.

Discovery rules were reviewed on 2026-09-22; no minimum Hermes version is asserted by the adapter manifest.

## Invocation

After trust and in a fresh session inside the repository:

```text
/pipeline Continue run RUN_ID.
/research Research run RUN_ID.
/plan Plan run RUN_ID.
/implement Implement run RUN_ID.
/review Review run RUN_ID.
```

Resume with `/pipeline Continue run RUN_ID.`

## Trust, permissions, and limitations

Trust is a user decision stored by Hermes outside the repository. Noninteractive surfaces such as cron, API, and ACP inherit the prior trust decision and do not auto-trust or prompt. Specromancy does not enable inline shell execution, choose a model or provider, or write quick commands. Project skill trust is not permission to bypass Specromancy approval or safety gates.

## Troubleshooting

- Skills not listed: run `hermes skills trust` from the correct Git checkout, then start a fresh session.
- Wrong project: verify the working directory resolves to the intended nearest Git root.
- Noninteractive job cannot find skills: trust the repository interactively first and set the job working directory inside that checkout.
- Revoking trust: run `hermes skills untrust`; this changes Hermes discovery only and does not delete repository files.
