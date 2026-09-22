import contextlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import tempfile
import unittest

from specromancy.artifacts.plan import validate_plan
from specromancy.clock import FixedClock
from specromancy.cli import main
from specromancy.errors import (
    ApprovalRequiredError,
    ExitCode,
    InvalidTransitionError,
    ValidationError,
)
from specromancy.io import sha256_file
from specromancy.phases.plan import (
    approve_plan,
    complete_plan,
    require_current_plan_approval,
    revoke_plan_approval,
    start_plan,
)
from specromancy.phases.research import complete_research, start_research
from specromancy.requirements import extract_requirements


RUN_ID = "20260921-plan"
NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
REQUIREMENTS = (
    {"id": "REQ-001", "text": "Add the planned behavior.", "source": "request_goal"},
)


def research_artifact() -> str:
    return f'''---
schema-version: "1"
run-id: "{RUN_ID}"
stage: "research"
status: "ready"
created-at: "2026-09-21T12:00:00Z"
---

## Request interpretation

Plan the fixture change.

## Repository map

`README.md` is the affected file.

## Current behavior

The fixture is documented (E-001).

## Constraints and invariants

Planning is read-only outside its run directory.

## Evidence

| Evidence ID | Claim | Source | Location | Confidence |
| --- | --- | --- | --- | --- |
| E-001 | The fixture is documented. | Repository | README.md:1 | High |

## Unknowns and assumptions

None.

## Risks

The documentation can drift.

## Planning inputs

- Affected areas: README.md.
- Acceptance criteria gaps: None.
- Recommended verification: Run contract tests.
'''


def plan_artifact(
    *,
    trace_rows: str | None = None,
    change_rows: str | None = None,
    decisions: str = "None.",
) -> str:
    trace_rows = trace_rows or (
        "| REQ-001 | E-001 | CHG-001 | Run the contract test and inspect its result. |"
    )
    change_rows = change_rows or (
        "| CHG-001 | modify | README.md | Document the planned behavior. | No |"
    )
    return f'''---
schema-version: "1"
run-id: "{RUN_ID}"
stage: "plan"
status: "ready"
created-at: "2026-09-21T12:00:00Z"
---

## Outcome

The fixture documents the requested behavior.

## Scope

Update the fixture documentation and its contract coverage.

## Requirements traceability

| Requirement ID | Evidence IDs | Planned changes | Verification |
| --- | --- | --- | --- |
{trace_rows}

## Proposed changes

| Change ID | Action | Path | Description | Approval-sensitive |
| --- | --- | --- | --- | --- |
{change_rows}

## Data and interface changes

None.

## Verification strategy

Run the focused contract test and then the complete suite.

## Rollout and rollback

No rollout is needed; revert the documentation change to roll back.

## Risks and mitigations

Documentation drift is mitigated by contract coverage.

## Open decisions

{decisions}

## Implementation sequence

1. Apply CHG-001.
2. Run focused and complete verification.
'''


class PlanArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / "README.md").write_text("# Fixture\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate(self, content: str, requirements=REQUIREMENTS):
        return validate_plan(content, self.root, RUN_ID, requirements, ("E-001",))

    def test_valid_plan_has_complete_traceability_and_paths(self) -> None:
        artifact = self.validate(plan_artifact())
        self.assertEqual(artifact.traceability[0].requirement_id, "REQ-001")
        self.assertEqual(artifact.planned_paths, ("README.md",))

    def test_missing_requirement_mapping_is_actionable(self) -> None:
        requirements = (*REQUIREMENTS, {"id": "REQ-002", "text": "Test it.", "source": "derived"})
        with self.assertRaises(ValidationError) as caught:
            self.validate(plan_artifact(), requirements)
        self.assertEqual(caught.exception.details["missing_requirement_ids"], ["REQ-002"])

    def test_verification_cannot_be_omitted(self) -> None:
        row = "| REQ-001 | E-001 | CHG-001 | None |"
        with self.assertRaises(ValidationError) as caught:
            self.validate(plan_artifact(trace_rows=row))
        self.assertIn("verification", caught.exception.message.lower())

    def test_invalid_existing_path_and_unmarked_new_file_are_rejected(self) -> None:
        rows = (
            "| CHG-001 | modify | missing.md | Add text. | No |",
            "| CHG-001 | modify | future.md | Add text. | No |",
        )
        for row in rows:
            with self.subTest(row=row), self.assertRaises(ValidationError) as caught:
                self.validate(plan_artifact(change_rows=row))
            self.assertIn("mark", caught.exception.hint or "")

    def test_create_requires_a_new_path(self) -> None:
        row = "| CHG-001 | create | README.md | Replace the document. | No |"
        with self.assertRaises(ValidationError):
            self.validate(plan_artifact(change_rows=row))

    def test_open_blocking_decision_prevents_validation(self) -> None:
        decisions = '''| Decision ID | Decision | Blocking | Status |
| --- | --- | --- | --- |
| DEC-001 | Choose the public behavior. | Yes | Open |'''
        with self.assertRaises(ValidationError) as caught:
            self.validate(plan_artifact(decisions=decisions))
        self.assertIn("blocking", caught.exception.message.lower())

    def test_sensitive_change_must_be_labeled(self) -> None:
        row = "| CHG-001 | modify | README.md | Add a new runtime dependency. | No |"
        with self.assertRaises(ValidationError) as caught:
            self.validate(plan_artifact(change_rows=row))
        self.assertIn("approval-sensitive", caught.exception.message)

    def test_purported_patch_is_rejected(self) -> None:
        content = plan_artifact().replace(
            "None.\n\n## Verification strategy",
            "```diff\n+implemented = True\n```\n\n## Verification strategy",
        )
        with self.assertRaises(ValidationError) as caught:
            self.validate(content)
        self.assertIn("patch", caught.exception.message)

    def test_requirement_extraction_is_stable(self) -> None:
        request = "# Request\n\n## Acceptance criteria\n\n- First result\n- [ ] Second result\n"
        requirements = extract_requirements(request)
        self.assertEqual([item["id"] for item in requirements], ["REQ-001", "REQ-002"])
        self.assertEqual(requirements[1]["text"], "Second result")


class PlanLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        subprocess.run(["git", "init", "--quiet"], cwd=self.root, check=True)
        (self.root / ".gitignore").write_text(".specromancy/runs/\n", encoding="utf-8")
        (self.root / "README.md").write_text("# Fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(
            [
                "git", "-c", "user.name=Specromancy Tests",
                "-c", "user.email=tests@example.invalid", "commit", "--quiet", "-m", "fixture",
            ],
            cwd=self.root,
            check=True,
        )
        self.run_dir = self.root / ".specromancy" / "runs" / RUN_ID
        self.run_dir.mkdir(parents=True)
        request = f'''---
schema-version: "1"
run-id: "{RUN_ID}"
stage: "request"
status: "ready"
created-at: "2026-09-21T12:00:00Z"
---

# Request

Add the planned behavior.
'''
        request_path = self.run_dir / "request.md"
        request_path.write_text(request, encoding="utf-8")
        request_digest = sha256_file(request_path)
        manifest = {
            "schema_version": "1", "run_id": RUN_ID, "title": "Plan fixture",
            "created_at": "2026-09-21T12:00:00Z", "updated_at": "2026-09-21T12:00:00Z",
            "status": "initialized", "current_phase": None,
            "repository_root": str(self.root), "repository_url": None,
            "git_base": None, "git_head": None, "git_branch": None,
            "initial_worktree": {"recorded_at": "2026-09-21T12:00:00Z", "staged_paths": [], "unstaged_paths": [], "untracked_paths": []},
            "implementation_baseline": None, "requirements": list(REQUIREMENTS),
            "artifacts": {"request": {"path": f".specromancy/runs/{RUN_ID}/request.md", "sha256": request_digest, "validated_at": "2026-09-21T12:00:00Z", "schema_version": "1", "bindings": {}}},
            "approvals": [], "changed_files": [], "review_subject_sha256": None,
            "review_cycle": 0, "max_review_cycles": 3, "last_error": None,
            "events_path": f".specromancy/runs/{RUN_ID}/events.jsonl",
            "lock_path": f".specromancy/runs/{RUN_ID}/run.lock",
        }
        (self.run_dir / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.run_dir / "events.jsonl").write_text("", encoding="utf-8")
        self.clock = FixedClock(NOW)
        start_research(self.root, RUN_ID, clock=self.clock)
        (self.run_dir / "research.md").write_text(research_artifact(), encoding="utf-8")
        complete_research(self.root, RUN_ID, clock=self.clock)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def ready_plan(self) -> None:
        start_plan(self.root, RUN_ID, clock=self.clock)
        (self.run_dir / "plan.md").write_text(plan_artifact(), encoding="utf-8")
        complete_plan(self.root, RUN_ID, clock=self.clock)

    def test_approval_requires_completed_validation(self) -> None:
        with self.assertRaises(InvalidTransitionError):
            approve_plan(self.root, RUN_ID, approver="user", clock=self.clock)

    def test_completion_and_identical_approval_are_idempotent(self) -> None:
        self.ready_plan()
        completed = complete_plan(self.root, RUN_ID, clock=self.clock)
        first = approve_plan(self.root, RUN_ID, approver="user", note="Reviewed", clock=self.clock)
        event_count = len((self.run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines())
        second = approve_plan(self.root, RUN_ID, approver="user", note="A replay note is ignored", clock=self.clock)
        self.assertTrue(completed.replayed)
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(second.note, "Reviewed")
        self.assertEqual(len((self.run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()), event_count)

    def test_modification_after_approval_is_stale(self) -> None:
        self.ready_plan()
        approve_plan(self.root, RUN_ID, approver="user", clock=self.clock)
        target = self.run_dir / "plan.md"
        target.write_text(plan_artifact().replace("fixture documents", "fixture clearly documents"), encoding="utf-8")
        with self.assertRaises(ApprovalRequiredError):
            require_current_plan_approval(self.root, RUN_ID)

    def test_approval_revocation_preserves_history_and_allows_replanning(self) -> None:
        self.ready_plan()
        approve_plan(self.root, RUN_ID, approver="user", clock=self.clock)
        revoked = revoke_plan_approval(
            self.root, RUN_ID, revoked_by="user", reason="Requirements changed", clock=self.clock
        )
        manifest = json.loads((self.run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(revoked.status, "plan_ready")
        self.assertEqual(manifest["approvals"][0]["status"], "revoked")
        self.assertEqual(start_plan(self.root, RUN_ID, clock=self.clock).status, "plan_in_progress")

    def test_cli_plan_lifecycle_and_approval(self) -> None:
        def invoke(*arguments: str):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(arguments)
            return code, json.loads(output.getvalue())

        common = ("--repo", str(self.root), "--format", "json")
        code, started = invoke("phase", "start", RUN_ID, "plan", *common)
        self.assertEqual(code, ExitCode.SUCCESS)
        self.assertEqual(started["data"]["status"], "plan_in_progress")
        (self.run_dir / "plan.md").write_text(plan_artifact(), encoding="utf-8")
        code, completed = invoke("phase", "complete", RUN_ID, "plan", *common)
        self.assertEqual(code, ExitCode.SUCCESS)
        self.assertEqual(completed["data"]["status"], "plan_ready")
        code, approved = invoke("approve", RUN_ID, "plan", "--by", "user", *common)
        self.assertEqual(code, ExitCode.SUCCESS)
        self.assertEqual(approved["data"]["status"], "plan_approved")
        code, revoked = invoke(
            "approval", "revoke", RUN_ID, "plan", "--by", "user", "--reason", "Revise", *common
        )
        self.assertEqual(code, ExitCode.SUCCESS)
        self.assertEqual(revoked["data"]["status"], "plan_ready")


if __name__ == "__main__":
    unittest.main()
