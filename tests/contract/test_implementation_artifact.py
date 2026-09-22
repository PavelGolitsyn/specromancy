import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import unittest

from specromancy.artifacts.implementation import validate_implementation
from specromancy.clock import FixedClock
from specromancy.commands import run_verification_command
from specromancy.errors import (
    ApprovalRequiredError,
    ConcurrencyError,
    ExternalCommandError,
    ValidationError,
)
from specromancy.io import sha256_file
from specromancy.phases.implement import (
    complete_implementation,
    execute_verification,
    start_implementation,
    start_repair,
)
from specromancy.phases.plan import approve_plan, complete_plan, start_plan
from specromancy.phases.research import complete_research, start_research


RUN_ID = "20260922-implement"
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def implementation_artifact(
    *,
    files: str = "| README.md | planned | Updated the approved documentation. |",
    command_id: str = "CMD-001",
    exit_code: int = 0,
    deviations: str = "None.",
    review_handoff: str = "None.",
) -> str:
    return f'''---
schema-version: "1"
run-id: "{RUN_ID}"
stage: "implementation"
status: "ready"
created-at: "2026-09-22T12:00:00Z"
---

## Summary

Updated the approved fixture behavior.

## Plan items completed

| Change ID | Status | Notes |
| --- | --- | --- |
| CHG-001 | Completed | Applied the approved change. |

## Files changed

| Path | Classification | Notes |
| --- | --- | --- |
{files}

## Deviations from plan

{deviations}

## Verification performed

| Command ID | Exit code | Blocking | Outcome |
| --- | --- | --- | --- |
| {command_id} | {exit_code} | Yes | The focused check completed. |

## Known limitations

None.

## Review handoff

{review_handoff}
'''


def research_artifact() -> str:
    return f'''---
schema-version: "1"
run-id: "{RUN_ID}"
stage: "research"
status: "ready"
created-at: "2026-09-22T12:00:00Z"
---

## Request interpretation

Update the fixture documentation.

## Repository map

README.md contains the affected behavior.

## Current behavior

The fixture is documented (E-001).

## Constraints and invariants

Preserve unrelated work.

## Evidence

| Evidence ID | Claim | Source | Location | Confidence |
| --- | --- | --- | --- | --- |
| E-001 | The fixture is documented. | Repository | README.md:1 | High |

## Unknowns and assumptions

None.

## Risks

Documentation could drift.

## Planning inputs

- Affected areas: README.md.
- Acceptance criteria gaps: None.
- Recommended verification: Run a focused command.
'''


def plan_artifact() -> str:
    return f'''---
schema-version: "1"
run-id: "{RUN_ID}"
stage: "plan"
status: "ready"
created-at: "2026-09-22T12:00:00Z"
---

## Outcome

The fixture documentation is updated.

## Scope

Modify README.md only.

## Requirements traceability

| Requirement ID | Evidence IDs | Planned changes | Verification |
| --- | --- | --- | --- |
| REQ-001 | E-001 | CHG-001 | Run a focused command. |

## Proposed changes

| Change ID | Action | Path | Description | Approval-sensitive |
| --- | --- | --- | --- | --- |
| CHG-001 | modify | README.md | Update the fixture documentation. | No |

## Data and interface changes

None.

## Verification strategy

Run a focused command and inspect its exit code.

## Rollout and rollback

Revert the documentation change.

## Risks and mitigations

Review the resulting diff.

## Open decisions

None.

## Implementation sequence

1. Apply CHG-001.
2. Run verification.
'''


class ImplementationArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / "README.md").write_text("# Fixture\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_valid_artifact_accounts_for_plan_items_and_verification(self) -> None:
        artifact = validate_implementation(implementation_artifact(), self.root, RUN_ID, ["CHG-001"])
        self.assertEqual(artifact.plan_items[0].status, "completed")
        self.assertEqual(artifact.verifications[0].command_id, "CMD-001")

    def test_missing_plan_item_and_secret_like_value_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            validate_implementation(implementation_artifact(), self.root, RUN_ID, ["CHG-001", "CHG-002"])
        secret = implementation_artifact().replace("None.\n\n## Review handoff", "api_key=super-secret-value\n\n## Review handoff")
        with self.assertRaises(ValidationError):
            validate_implementation(secret, self.root, RUN_ID, ["CHG-001"])


class ImplementationLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        subprocess.run(["git", "init", "--quiet"], cwd=self.root, check=True)
        (self.root / ".gitignore").write_text(".specromancy/runs/\n", encoding="utf-8")
        (self.root / "README.md").write_text("# Fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Tests", "-c", "user.email=tests@example.invalid", "commit", "--quiet", "-m", "fixture"],
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
created-at: "2026-09-22T12:00:00Z"
---

# Request

Update the fixture documentation.
'''
        request_path = self.run_dir / "request.md"
        request_path.write_text(request, encoding="utf-8")
        manifest = {
            "schema_version": "1", "run_id": RUN_ID, "title": "Implementation fixture",
            "created_at": "2026-09-22T12:00:00Z", "updated_at": "2026-09-22T12:00:00Z",
            "status": "initialized", "current_phase": None, "repository_root": str(self.root),
            "repository_url": None, "git_base": None, "git_head": None, "git_branch": None,
            "initial_worktree": {"recorded_at": "2026-09-22T12:00:00Z", "staged_paths": [], "unstaged_paths": [], "untracked_paths": []},
            "implementation_baseline": None,
            "requirements": [{"id": "REQ-001", "text": "Update the fixture documentation.", "source": "request_goal"}],
            "artifacts": {"request": {"path": f".specromancy/runs/{RUN_ID}/request.md", "sha256": sha256_file(request_path), "validated_at": "2026-09-22T12:00:00Z", "schema_version": "1", "bindings": {}}},
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
        start_plan(self.root, RUN_ID, clock=self.clock)
        (self.run_dir / "plan.md").write_text(plan_artifact(), encoding="utf-8")
        complete_plan(self.root, RUN_ID, clock=self.clock)
        approve_plan(self.root, RUN_ID, approver="user", clock=self.clock)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_complete_records_changed_files_and_is_idempotent(self) -> None:
        start_implementation(self.root, RUN_ID, clock=self.clock)
        (self.root / "README.md").write_text("# Updated fixture\n", encoding="utf-8")
        command = execute_verification(self.root, RUN_ID, ["python3", "-c", "print('ok')"], clock=self.clock)
        (self.run_dir / "implementation.md").write_text(
            implementation_artifact(command_id=command.command_id), encoding="utf-8"
        )
        result = complete_implementation(self.root, RUN_ID, clock=self.clock)
        replay = complete_implementation(self.root, RUN_ID, clock=self.clock)
        self.assertEqual(result.changed_files[0]["classification"], "planned")
        self.assertTrue(replay.replayed)

    def test_interrupted_start_resumes_same_baseline(self) -> None:
        first = start_implementation(self.root, RUN_ID, clock=self.clock)
        manifest_before = json.loads((self.run_dir / "run.json").read_text(encoding="utf-8"))
        second = start_implementation(self.root, RUN_ID, clock=self.clock)
        manifest_after = json.loads((self.run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(manifest_before["implementation_baseline"], manifest_after["implementation_baseline"])

    def test_unrelated_preexisting_edit_is_preserved_and_identifiable(self) -> None:
        notes = self.root / "NOTES.md"
        notes.write_text("user work\n", encoding="utf-8")
        start_implementation(self.root, RUN_ID, clock=self.clock)
        (self.root / "README.md").write_text("# Updated fixture\n", encoding="utf-8")
        command = execute_verification(self.root, RUN_ID, ["python3", "-c", "print('ok')"], clock=self.clock)
        file_rows = "\n".join(
            (
                "| README.md | planned | Updated approved documentation. |",
                "| NOTES.md | pre_existing_user_change | Preserved unrelated user work. |",
            )
        )
        (self.run_dir / "implementation.md").write_text(
            implementation_artifact(files=file_rows, command_id=command.command_id), encoding="utf-8"
        )
        result = complete_implementation(self.root, RUN_ID, clock=self.clock)
        classifications = {item["path"]: item["classification"] for item in result.changed_files}
        self.assertEqual(classifications["NOTES.md"], "pre_existing_user_change")
        self.assertEqual(notes.read_text(encoding="utf-8"), "user work\n")

    def test_unplanned_file_and_material_deviation_block_completion(self) -> None:
        start_implementation(self.root, RUN_ID, clock=self.clock)
        (self.root / "README.md").write_text("# Updated fixture\n", encoding="utf-8")
        (self.root / "rogue.txt").write_text("outside plan\n", encoding="utf-8")
        command = execute_verification(self.root, RUN_ID, ["python3", "-c", "print('ok')"], clock=self.clock)
        file_rows = "\n".join(
            (
                "| README.md | planned | Updated approved documentation. |",
                "| rogue.txt | planned | Not in the approved plan. |",
            )
        )
        (self.run_dir / "implementation.md").write_text(
            implementation_artifact(files=file_rows, command_id=command.command_id), encoding="utf-8"
        )
        with self.assertRaises(ValidationError):
            complete_implementation(self.root, RUN_ID, clock=self.clock)
        (self.root / "rogue.txt").unlink()
        deviation = '''| Deviation ID | Material | Description |
| --- | --- | --- |
| DEV-001 | Yes | The outcome would require broader scope. |'''
        (self.run_dir / "implementation.md").write_text(
            implementation_artifact(command_id=command.command_id, deviations=deviation), encoding="utf-8"
        )
        with self.assertRaises(ApprovalRequiredError):
            complete_implementation(self.root, RUN_ID, clock=self.clock)

    def test_stale_approval_and_lock_contention_stop_before_mutation(self) -> None:
        (self.run_dir / "plan.md").write_text(plan_artifact().replace("fixture documentation", "fixture docs"), encoding="utf-8")
        with self.assertRaises(ApprovalRequiredError):
            start_implementation(self.root, RUN_ID, clock=self.clock)
        (self.run_dir / "plan.md").write_text(plan_artifact(), encoding="utf-8")
        (self.run_dir / "run.lock").write_text('{"owner_id":"other"}', encoding="utf-8")
        with self.assertRaises(ConcurrencyError):
            start_implementation(self.root, RUN_ID, clock=self.clock)

    def test_failed_blocking_verification_prevents_completion(self) -> None:
        start_implementation(self.root, RUN_ID, clock=self.clock)
        (self.root / "README.md").write_text("# Updated fixture\n", encoding="utf-8")
        command = execute_verification(self.root, RUN_ID, ["python3", "-c", "raise SystemExit(2)"], clock=self.clock)
        (self.run_dir / "implementation.md").write_text(
            implementation_artifact(command_id=command.command_id, exit_code=2), encoding="utf-8"
        )
        with self.assertRaises(ExternalCommandError):
            complete_implementation(self.root, RUN_ID, clock=self.clock)

    def test_repair_requires_every_current_finding_id(self) -> None:
        review = f'''---
schema-version: "1"
run-id: "{RUN_ID}"
stage: "review"
status: "changes_requested"
created-at: "2026-09-22T12:00:00Z"
---

## Findings

| Finding ID | Detail |
| --- | --- |
| REV-001 | Repair the documentation. |
'''
        review_path = self.run_dir / "review.md"
        review_path.write_text(review, encoding="utf-8")
        manifest = json.loads((self.run_dir / "run.json").read_text(encoding="utf-8"))
        manifest["status"] = "changes_requested"
        manifest["current_phase"] = None
        manifest["artifacts"]["review"] = {
            "path": f".specromancy/runs/{RUN_ID}/review.md",
            "sha256": sha256_file(review_path),
            "validated_at": "2026-09-22T12:00:00Z",
            "schema_version": "1",
            "bindings": {},
        }
        (self.run_dir / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
        start_repair(self.root, RUN_ID, clock=self.clock)
        (self.root / "README.md").write_text("# Repaired fixture\n", encoding="utf-8")
        command = execute_verification(self.root, RUN_ID, ["python3", "-c", "print('ok')"], clock=self.clock)
        (self.run_dir / "implementation.md").write_text(
            implementation_artifact(command_id=command.command_id), encoding="utf-8"
        )
        with self.assertRaises(ValidationError) as caught:
            complete_implementation(self.root, RUN_ID, clock=self.clock)
        self.assertEqual(caught.exception.details["missing_finding_ids"], ["REV-001"])

    def test_command_output_is_redacted_and_truncated(self) -> None:
        record = run_verification_command(
            self.root,
            RUN_ID,
            ["python3", "-c", "print('api_' + 'key=' + 'super-' + 'secret-value ' + 'x' * 1000)"],
            output_limit=256,
            clock=self.clock,
        )
        output = (self.root / record.stdout_path).read_text(encoding="utf-8")
        self.assertNotIn("super-secret-value", output)
        self.assertTrue(record.stdout_truncated)


if __name__ == "__main__":
    unittest.main()
