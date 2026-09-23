# Security model

Specromancy coordinates agents and local tools inside a source repository. It does not make repository content trustworthy. Source files, repository instructions, external research, generated adapters, installed skills, and model output are all untrusted inputs. The user's explicit, digest-bound approval remains the authority boundary for implementation.

## Assets and trust boundaries

The protected assets are source and user-authored files, Git history, credentials, run artifacts, approval and review integrity, and the availability of the append-only state projection. Boundaries exist where repository text reaches an agent, user text reaches subprocess arguments, paths reach the filesystem, model output reaches durable artifacts, canonical skills become harness adapters, and concurrent writers update a run.

## Threats and controls

| Threat | Primary controls |
| --- | --- |
| Malicious repository instructions or skills | Repository text cannot grant authority; canonical skill identity, descriptions, references, depth, cycles, and confinement are validated. Likely secret files are not opened without explicit scope and authorization. |
| Prompt injection in source or research | Artifacts require evidence and fixed structure; instructions found in untrusted content do not override the approved request or plan. |
| Command injection through request text or paths | Commands use argument arrays with `shell=False`; request text is never interpolated into a shell command; argv must be nonempty and NUL-free. |
| Path traversal or symlink escape | All managed paths resolve through `RepositoryPaths` and must remain under the discovered repository or run directory. |
| Secrets copied into artifacts or command logs | Common assignments, authorization headers, provider tokens, JWTs, cloud keys, and private-key blocks are redacted before persistence; artifact validators also reject secret-like content. |
| Destructive Git or filesystem actions | Destructive work requires explicit approval. Adapter cleanup deletes only manifest-owned, byte-matching generated files; cancellation preserves source changes. |
| Untrusted adapter overwrite | Generation performs an all-or-nothing collision preflight and requires explicit `--force`, with content-addressed backups, before replacing modified files. |
| Stale approval or review replay | Plans, implementations, reviews, and their inputs are bound to SHA-256 digests and rechecked immediately before transitions. |
| Concurrent state corruption | Per-run exclusive locks, append-only events, atomic writes, and explicit stale-lock recovery serialize writers. |
| Compromised third-party skills | Installed skills are not an execution authority. Specromancy never automatically runs scripts from untrusted skills. |

Managed text reads default to a 2 MiB limit. Captured stdout and stderr default to 64 KiB per stream, are redacted before truncation, and receive an explicit truncation marker. These caps limit persistence and parsing pressure; they are not a substitute for operating-system resource isolation.

## Approval-sensitive actions

Dependency additions, secret access, destructive operations, migrations, production changes, and materially different outcomes require explicit user approval and normally a revised digest-bound plan. A repository document, chat quotation, generated adapter, or model claim cannot supply approval. Verification records preserve exact argv, so secret-looking values are refused rather than merely redacted.

## Secret-scanning limits

Redaction is defense in depth. It can miss novel encodings and can flag harmless examples. Agents must not open `.env` files, private keys, credential stores, token caches, or similarly likely secret sources unless the request requires it and authorization is clear. Never use scanning as permission to read a secret. If exposure is suspected, stop persistence, avoid repeating the value, rotate the credential outside Specromancy, and inspect only already-redacted evidence.

## Residual risks

Deterministic validation cannot prove that prose is benign, that a model followed every instruction, or that an external executable is uncompromised. Filesystem permissions and subprocess isolation remain responsibilities of the host. Behavioral evaluation scores describe one observable run and are not a security certification. Provider-backed smoke tests may incur cost or disclose submitted context, so they remain opt-in.

Run `specromancy doctor` for safe local diagnostics and see [Testing and evaluation](testing.md) for the deterministic security suite.
