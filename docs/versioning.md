# Versioning and compatibility

The Python package uses semantic versioning. During `0.x`, a minor release may contain a breaking change, but every such change must be explicit in `CHANGELOG.md`, the compatibility table, and affected documentation.

Formats evolve independently:

| Surface | Current version | Representation | Compatibility rule |
| --- | ---: | --- | --- |
| Package | 0.1.0 | SemVer | Public CLI additions should remain additive within the release line. |
| Pipeline contract | 1 | String integer | Runtime contracts must match the supported value. |
| Run manifest schema | 1 | String integer | Unsupported future manifests are rejected before transition. |
| Artifact schema | 1 | String integer | Unsupported future frontmatter is rejected before parsing phase content. |
| Adapter manifest | 1 | Integer | Unsupported future manifests are rejected before generation, check, or cleanup. |

`specromancy --version --format json` reports each value independently. The legacy `schema_version` field remains an alias of the run-manifest schema for 0.1.0 compatibility.

Specromancy does not silently migrate durable files. A tool that encounters a future version stops with a validation error and directs the user to a compatible release. When an older known format exists, status and artifact inspection should remain read-only where feasible; mutation requires an explicit, separately approved migration design. Version 1 is the first format, so 0.1.0 has no older known version to inspect.

Generated adapters record their own schema and each adapter's implementation version. Changing a canonical skill without changing a wire format requires regeneration, not a schema bump. Breaking manifest meaning or structure requires a new independent integer version.
