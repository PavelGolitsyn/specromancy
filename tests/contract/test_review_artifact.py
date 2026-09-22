import contextlib
import io
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import unittest

from specromancy.artifacts.review import validate_review
from specromancy.clock import FixedClock
from specromancy.cli import main
from specromancy.errors import (
    ConcurrencyError,
    ExitCode,
    InvalidTransitionError,
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
from specromancy.phases.review import complete_review, start_review


RUN_ID = "20260922-review"
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
REQUIREMENTS = (
    {"id": "REQ-001", "text": "Update the fixture documentation.", "source": "request_goal"},
)


def review_artifact(
    *,
    verdict: str = "passed",
    findings: str = "None.",
    coverage: str = "| REQ-001 | Covered | README.md:1 and CMD-001 demonstrate the requested update. |",
    verification: str = "The reviewer inspected the recorded focused command and re-ran the assertion.",
    residual: str = "None.",
    repair: str = "None.",
    verdict_reason: str = "",
) -> str:
    reason = f"\n\n{verdict_reason}" if verdict_reason else ""
    return f'''---
schema-version: "1"
run-id: "{RUN_ID}"
stage: "review"
status: "{verdict}"
created-at: "2026-09-22T12:00:00Z"
---

## Verdict

{verdict}{reason}

## Findings

{findings}

## Requirement coverage

| Requirement ID | Status | Evidence |
| --- | --- | --- |
{coverage}

## Verification assessment

{verification}

## Residual risks

{residual}

## Repair guidance

{repair}
'''


def finding_row(
    finding_id: str = "REV-001",
    *,
    severity: str = "Medium",
    blocking: str = "Yes",
    location: str = "README.md:1",
) -> str:
    return f'''| Finding ID | Severity | Blocking | Title | Location | Observed | Expected | Impact | Repair guidance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| {finding_id} | {severity} | {blocking} | Required text is absent | {location} | The requested text is absent. | REQ-001 requires the requested text. | The user-visible requirement is not met. | Add the missing text and cover it with a test. |'''


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


def implementation_artifact(command_id: str) -> str:
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
| README.md | planned | Updated the approved documentation. |

## Deviations from plan

None.

## Verification performed

| Command ID | Exit code | Blocking | Outcome |
| --- | --- | --- | --- |
| {command_id} | 0 | Yes | The focused check completed. |

## Known limitations

None.

## Review handoff

None.
'''


class ReviewArtifactTests(unittest.TestCase):
    def test_passed_review_with_no_findings(self) -> None:
        artifact = validate_review(review_artifact(), RUN_ID, REQUIREMENTS)
        self.assertEqual(artifact.verdict, "passed")
        self.assertEqual(artifact.findings, ())

    def test_medium_finding_cannot_have_passed_verdict(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            validate_review(review_artifact(findings=finding_row()), RUN_ID, REQUIREMENTS)
        self.assertIn("blocking", caught.exception.message.lower())

    def test_missing_location_and_duplicate_id_are_rejected(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            validate_review(
                review_artifact(
                    verdict="changes_requested",
                    findings=finding_row(location="Unknown"),
                ),
                RUN_ID,
                REQUIREMENTS,
            )
        self.assertIn("location", caught.exception.message.lower())
        duplicated = finding_row() + "\n" + finding_row().splitlines()[-1]
        with self.assertRaises(ValidationError) as caught:
            validate_review(
                review_artifact(verdict="changes_requested", findings=duplicated),
                RUN_ID,
                REQUIREMENTS,
            )
        self.assertIn("duplicated", caught.exception.message.lower())

    def test_incomplete_requirement_coverage_is_rejected(self) -> None:
        requirements = (*REQUIREMENTS, {"id": "REQ-002", "text": "Test it.", "source": "derived"})
        with self.assertRaises(ValidationError) as caught:
            validate_review(review_artifact(), RUN_ID, requirements)
        self.assertEqual(caught.exception.details["missing_requirement_ids"], ["REQ-002"])

    def test_blocked_review_requires_named_missing_evidence(self) -> None:
        content = review_artifact(
            verdict="blocked",
            coverage="| REQ-001 | Blocked | The required environment is unavailable. |",
            verdict_reason="Required evidence cannot be inspected.",
        )
        with self.assertRaises(ValidationError) as caught:
            validate_review(content, RUN_ID, REQUIREMENTS)
        self.assertIn("evidence blocker", caught.exception.message.lower())
        valid = content.replace(
            "Required evidence cannot be inspected.",
            "Blocker: the required evidence cannot be inspected.",
        )
        self.assertEqual(validate_review(valid, RUN_ID, REQUIREMENTS).verdict, "blocked")

    def test_repair_reconciles_fixed_and_unresolved_prior_findings(self) -> None:
        fixed = '''| Finding ID | Status | Evidence |
| --- | --- | --- |
| REV-001 | Fixed | README.md:1 now satisfies REQ-001. |'''
        validate_review(
            review_artifact(repair=fixed),
            RUN_ID,
            REQUIREMENTS,
            prior_finding_ids=("REV-001",),
        )
        unresolved = '''| Finding ID | Status | Evidence |
| --- | --- | --- |
| REV-001 | Still present | README.md:1 still omits the behavior. |'''
        artifact = validate_review(
            review_artifact(
                verdict="changes_requested",
                findings=finding_row(),
                coverage="| REQ-001 | Missing | REV-001 demonstrates the omission. |",
                repair=unresolved,
            ),
            RUN_ID,
            REQUIREMENTS,
            prior_finding_ids=("REV-001",),
        )
        self.assertEqual(artifact.reconciliations[0].status, "still_present")


class ReviewLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        subprocess.run(["git", "init", "--quiet"], cwd=self.root, check=True)
        (self.root / ".gitignore").write_text(".specromancy/runs/\n", encoding="utf-8")
        (self.root / "README.md").write_text("# Fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(
            [
                "git", "-c", "user.name=Tests", "-c", "user.email=tests@example.invalid",
                "commit", "--quiet", "-m", "fixture",
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
created-at: "2026-09-22T12:00:00Z"
---

# Request

Update the fixture documentation.
'''
        request_path = self.run_dir / "request.md"
        request_path.write_text(request, encoding="utf-8")
        manifest = {
            "schema_version": "1", "run_id": RUN_ID, "title": "Review fixture",
            "created_at": "2026-09-22T12:00:00Z", "updated_at": "2026-09-22T12:00:00Z",
            "status": "initialized", "current_phase": None, "repository_root": str(self.root),
            "repository_url": None, "git_base": None, "git_head": None, "git_branch": None,
            "initial_worktree": {"recorded_at": "2026-09-22T12:00:00Z", "staged_paths": [], "unstaged_paths": [], "untracked_paths": []},
            "implementation_baseline": None, "requirements": list(REQUIREMENTS),
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
        start_implementation(self.root, RUN_ID, clock=self.clock)
        (self.root / "README.md").write_text("# Updated fixture\n", encoding="utf-8")
        command = execute_verification(
            self.root, RUN_ID, ["python3", "-c", "print('ok')"], clock=self.clock
        )
        (self.run_dir / "implementation.md").write_text(
            implementation_artifact(command.command_id), encoding="utf-8"
        )
        complete_implementation(self.root, RUN_ID, clock=self.clock)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_pass_records_subject_and_is_idempotent(self) -> None:
        started = start_review(self.root, RUN_ID, clock=self.clock)
        self.assertIsNotNone(started.review_subject_sha256)
        (self.run_dir / "review.md").write_text(review_artifact(), encoding="utf-8")
        completed = complete_review(self.root, RUN_ID, clock=self.clock)
        replay = complete_review(self.root, RUN_ID, clock=self.clock)
        self.assertEqual(completed.status, "passed")
        self.assertTrue(replay.replayed)

    def test_diff_change_and_repository_mutation_invalidate_review(self) -> None:
        start_review(self.root, RUN_ID, clock=self.clock)
        (self.run_dir / "review.md").write_text(review_artifact(), encoding="utf-8")
        (self.root / "README.md").write_text("# Mutated during review\n", encoding="utf-8")
        with self.assertRaises(ConcurrencyError):
            complete_review(self.root, RUN_ID, clock=self.clock)

    def test_new_repository_path_during_review_is_rejected(self) -> None:
        start_review(self.root, RUN_ID, clock=self.clock)
        (self.run_dir / "review.md").write_text(review_artifact(), encoding="utf-8")
        (self.root / "rogue.txt").write_text("reviewer mutation\n", encoding="utf-8")
        with self.assertRaises(ConcurrencyError):
            complete_review(self.root, RUN_ID, clock=self.clock)

    def test_review_cycle_boundary_prevents_another_repair(self) -> None:
        start_review(self.root, RUN_ID, clock=self.clock)
        manifest = json.loads((self.run_dir / "run.json").read_text(encoding="utf-8"))
        manifest["review_cycle"] = manifest["max_review_cycles"]
        (self.run_dir / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.run_dir / "review.md").write_text(
            review_artifact(
                verdict="changes_requested",
                findings=finding_row(),
                coverage="| REQ-001 | Missing | REV-001 demonstrates the omission. |",
            ),
            encoding="utf-8",
        )
        self.assertEqual(complete_review(self.root, RUN_ID, clock=self.clock).status, "changes_requested")
        with self.assertRaises(InvalidTransitionError):
            start_repair(self.root, RUN_ID, clock=self.clock)

    def test_cli_review_lifecycle(self) -> None:
        def invoke(*arguments: str):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(arguments)
            return code, json.loads(output.getvalue())

        common = ("--repo", str(self.root), "--format", "json")
        code, started = invoke("phase", "start", RUN_ID, "review", *common)
        self.assertEqual(code, ExitCode.SUCCESS)
        self.assertEqual(started["data"]["status"], "review_in_progress")
        (self.run_dir / "review.md").write_text(review_artifact(), encoding="utf-8")
        code, validated = invoke("validate", RUN_ID, "review", *common)
        self.assertEqual(code, ExitCode.SUCCESS)
        self.assertEqual(validated["data"]["phase"], "review")
        code, completed = invoke("phase", "complete", RUN_ID, "review", *common)
        self.assertEqual(code, ExitCode.SUCCESS)
        self.assertEqual(completed["data"]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
