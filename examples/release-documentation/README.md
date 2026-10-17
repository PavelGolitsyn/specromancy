# Release documentation consumer

This project supplies a two-phase pipeline to an installed `specromancy-engine`:
`draft-release-notes` → `review-release-notes` → `approved` or `blocked`.
It contains no engine source. All release policy, skills, inputs, and templates
belong to this example. There is no repair loop; a blocked request needs a new
run after the user resolves its findings.

The engine emits actions for an agent or harness and verifies the results. It
does not launch an LLM, supply credentials, generate prose, or publish notes.
Both phases are read-only for project files, but may produce their designated
output in `.specromancy/runs/`. Completed outputs and the copied request are
immutable. Copying approved notes into project release docs is an explicit user
action after completion, outside this lifecycle. `approved` is a configured
review outcome, not a human approval gate or a guarantee of factual accuracy.

## Install and copy

Follow the [installation guide](../../docs/guides/installation.md) to build
`specromancy_engine-0.1.0-py3-none-any.whl`. This is a local wheel workflow;
registry installation is available only after a release exists.

From the producer checkout, copy into a **new** directory outside that checkout
(the trailing `/.` includes hidden files). Substitute your actual wheel path:

```sh
PRODUCER="$PWD"
CONSUMER="$(mktemp -d)/release-documentation"
mkdir "$CONSUMER"
cp -R "$PRODUCER/examples/release-documentation/." "$CONSUMER/"
cd "$CONSUMER"
git init --quiet
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --no-index --no-deps /absolute/path/to/specromancy_engine-0.1.0-py3-none-any.whl
```

No commit is required. For an existing project, review and merge the canonical
files individually; never bulk-copy over its instructions, registry, skills, or
harness files. Installation creates none of those files. See the installation
guide's configuration checklist and [adapter conflict guidance](../../docs/guides/harnesses.md#ownership-and-conflicts).
Documentation links here refer to the producer repository and are navigable
there; the copied project's executable walkthrough below is self-contained.

## Execute the walkthrough

With the consumer environment active, inspect help:

```sh
specromancy --help
python -m specromancy_engine --help
cat workflow/pipelines.toml
```

The registry explicitly registers `release-documentation`; there is no default.
The following Python block invokes the installed CLI using argument arrays.
Run it from the consumer root with `python` (paste it into a Python session or
save it outside the project). It generates/checks adapters **before** any phase
starts, captures RUN_ID and all artifact paths from responses, supplies
`sample-changes.md` through the supported `--description-file` request input,
and simulates an agent with deterministic prose for this sample only.

<!-- walkthrough: tested verbatim by tests/packaging/test_release_documentation.py -->
```python
import json
import subprocess
from pathlib import Path

root = Path.cwd().resolve()

def cli(*args, expected=0):
    result = subprocess.run(
        ["specromancy", "--root", str(root), "--json", *args],
        capture_output=True, text=True,
    )
    if result.returncode != expected:
        raise RuntimeError(result.stdout + result.stderr)
    return json.loads(result.stdout or result.stderr)

def validate(action, expected):
    # This argv already includes the consumer root and recorded run/phase IDs.
    result = subprocess.run(
        [*action["final_validation_command"], "--json"],
        capture_output=True, text=True,
    )
    if result.returncode != expected:
        raise RuntimeError(result.stdout + result.stderr)
    return json.loads(result.stdout or result.stderr)

cli("adapters", "generate")
cli("adapters", "generate", "--check")
initialized = cli("init", "--description-file", "sample-changes.md",
                  "--pipeline", "release-documentation", expected=8)
RUN_ID = initialized["action"]["run_id"]
cli("status", RUN_ID)
pending = cli("resume", RUN_ID, expected=8)["action"]
draft = cli("phase", RUN_ID, pending["phase"], expected=8)["action"]

# A real agent reads draft["skill"], draft["inputs"], and draft["template"],
# then authors this output according to the packet's criteria and policy.
request = Path(draft["inputs"][0]["absolute_path"]).read_text(encoding="utf-8")
assert "Lantern 1.4.0" in request
notes_path = Path(draft["output"]["absolute_path"])
notes_path.write_text(
    "# Lantern 1.4.0\n\n## Summary\n"
    "This release adds report export and fixes retry notifications.\n\n"
    "## Changes\n- Added CSV export for saved reports.\n"
    "- Fixed duplicate email notifications when a report is retried.\n"
    "- Renamed `report_timeout` to `report_timeout_seconds`.\n\n"
    "## Upgrade Notes\nRename `report_timeout` to `report_timeout_seconds` "
    "before upgrading; keep its numeric value unchanged.\n",
    encoding="utf-8",
)
next_action = validate(draft, expected=8)["action"]
cli("status", RUN_ID)
review = cli("phase", RUN_ID, next_action["phase"], expected=8)["action"]
inputs = {item["reference"]: Path(item["absolute_path"])
          for item in review["inputs"]}
assert inputs["latest:draft-release-notes"] == notes_path
assert inputs["request"].read_text(encoding="utf-8") == request
assert "CSV export" in notes_path.read_text(encoding="utf-8")
Path(review["output"]["absolute_path"]).write_text(
    "# Release Notes Review\n\n## Verdict\nApproved.\n\n"
    "## Findings\nThe draft covers the supplied changes without added claims.\n\n"
    "## Verification\nCompared CSV export, the duplicate notification fix, "
    "and the configuration rename with the request. The upgrade action "
    "retains the numeric value and precedes upgrading.\n",
    encoding="utf-8",
)
validate(review, expected=0)
status = cli("status", RUN_ID)["status"]
assert status["status"] == "completed"
assert status["terminal_result"]["outcome"] == "approved"
print(json.dumps({"run_id": RUN_ID, "notes": str(notes_path),
                  "review": review["output"]["absolute_path"],
                  "outcome": status["terminal_result"]["outcome"]}, indent=2))
```

Exit **8** means an agent must act; it is normal for init, resume, phase start,
and a transition to another phase. Shell scripts using `set -e` must capture
and handle it explicitly. The helper above checks each expected code, rather
than hiding errors. Validation failure (6) requires inspecting diagnostics and
fixing the active output or reported violation before retrying; never change a
sealed output. Blocked (9), approval-required (7), and paused (13) require the
recorded intervention. Lock contention (10) requires inspecting the lock owner;
do not delete a live lock. Missing configuration (3), usage errors (2), and
adapter drift (11) need configuration/ownership repair. See the
[complete exit table](../../docs/reference/cli.md#json-and-exit-codes).

For real work, replace the sample request and let your harness follow the
canonical pipeline skill and phase packets. The Markdown validators check
headings and repository mutation, not whether prose is true. Each phase has only
one successful outcome, selected automatically; passing `--outcome` would be an
error. A reviewer stops with `specromancy block RUN_ID --reason
unsupported-release-claims --details TEXT --json`, returning code 9 with a
persisted block reason. That stop does not validate or seal the active review
output. Preserve the completed draft;
do not edit it to repair a failed review. Do not commit `.specromancy/`.

## Python imports and maintenance

The dependency is `specromancy-engine`, the import is `specromancy_engine`,
and the executable is `specromancy`. The
[public API example](../../docs/guides/installation.md#python-project-dependency)
uses this registry with `Engine`, `RunStore`, and `load_registry`.

The generic `.agents/skills/pipeline/SKILL.md` is an exact copy of the producer's
canonical orchestrator. When that procedure changes, maintainers must update
this copy in the same change. A shipped-configuration consistency test enforces
byte equality and portable frontmatter for these example skills. Release-specific
procedures and templates remain example-owned; test-owned workflow fixtures are
independent. Examples are repository assets, kept outside the wheel; source
distribution inclusion is checked by the [distribution verifier](../../docs/guides/distribution-verification.md).
