from __future__ import annotations

import json
import unittest

from specromancy.exit_codes import ExitCode

from tests.features.contract.support import DEFAULT_ARTIFACTS, CliRepository, advance_to


class DefaultPipelineContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = CliRepository()

    def tearDown(self) -> None:
        self.repo.close()

    def test_default_pipeline_completes_and_records_implementation_changes(self) -> None:
        run_id = self.repo.initialize("Change the tracked file")
        for phase in ("research", "plan"):
            self.repo.start_and_write(run_id, phase, DEFAULT_ARTIFACTS[phase])
            result = self.repo.command("validate", run_id, phase)
            self.assertEqual(result.returncode, ExitCode.AGENT_ACTION_REQUIRED)

        self.repo.start_and_write(
            run_id, "implement", DEFAULT_ARTIFACTS["implement"]
        )
        (self.repo.root / "tracked.txt").write_text("implemented\n", encoding="utf-8")
        implemented = self.repo.command("validate", run_id, "implement")
        self.assertEqual(implemented.returncode, ExitCode.AGENT_ACTION_REQUIRED)

        self.repo.start_and_write(run_id, "review", DEFAULT_ARTIFACTS["review"])
        completed = self.repo.command(
            "validate", run_id, "review", "--outcome", "approved"
        )
        self.assertEqual(completed.returncode, ExitCode.SUCCESS, completed.stderr)
        payload = self.repo.payload(completed)
        self.assertEqual(payload["status"]["status"], "completed")

        manifest = json.loads(
            (
                self.repo.root / ".specromancy" / "runs" / run_id / "run.json"
            ).read_text(encoding="utf-8")
        )
        implementation = next(
            visit for visit in manifest["visits"] if visit["phase_id"] == "implement"
        )
        self.assertEqual(implementation["mutation_result"]["paths"], ["tracked.txt"])
        self.assertEqual(implementation["mutation_result"]["status"], "passed")

    def test_plan_approval_pauses_and_resumes_the_run(self) -> None:
        run_id = self.repo.initialize("Require plan approval")
        advance_to(self.repo, run_id, "plan")
        self.repo.start_and_write(run_id, "plan", DEFAULT_ARTIFACTS["plan"])

        requested = self.repo.command(
            "request-approval", run_id, "--reason", "material-scope-change"
        )
        self.assertEqual(requested.returncode, ExitCode.APPROVAL_REQUIRED)
        status = self.repo.payload(self.repo.command("status", run_id))["status"]
        self.assertEqual(status["status"], "awaiting-approval")
        self.assertEqual(status["next_command"], ["specromancy", "approve", run_id, "plan"])

        approved = self.repo.command("approve", run_id, "plan")
        self.assertEqual(approved.returncode, ExitCode.AGENT_ACTION_REQUIRED)
        self.assertEqual(self.repo.payload(approved)["action"]["phase"], "implement")

    def test_review_repair_loop_returns_to_implementation_then_blocks(self) -> None:
        run_id = self.repo.initialize("Exercise repair limits")
        advance_to(self.repo, run_id, "implement")
        result = None
        for traversal in range(4):
            self.repo.start_and_write(
                run_id, "implement", DEFAULT_ARTIFACTS["implement"]
            )
            validated = self.repo.command("validate", run_id, "implement")
            self.assertEqual(validated.returncode, ExitCode.AGENT_ACTION_REQUIRED)
            self.repo.start_and_write(run_id, "review", DEFAULT_ARTIFACTS["review"])
            result = self.repo.command(
                "validate", run_id, "review", "--outcome", "changes-requested"
            )
            if traversal < 3:
                self.assertEqual(result.returncode, ExitCode.AGENT_ACTION_REQUIRED)
                self.assertEqual(self.repo.payload(result)["action"]["phase"], "implement")

        assert result is not None
        self.assertEqual(result.returncode, ExitCode.RUN_BLOCKED)
        status = self.repo.payload(result)["status"]
        self.assertEqual(status["status"], "blocked")
        self.assertEqual(status["block"]["reason"], "transition-traversal-limit")


if __name__ == "__main__":
    unittest.main()
