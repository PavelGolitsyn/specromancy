import contextlib
import io
import json
import subprocess
import tempfile
from pathlib import Path
import unittest

from specromancy.cli import main
from specromancy.events import load_events, replay_events
from specromancy.paths import RepositoryPaths

from tests.contract.test_review_artifact import (
    RUN_ID,
    finding_row,
    implementation_artifact,
    plan_artifact,
    research_artifact,
    review_artifact,
)


class CompleteRunIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name).resolve()
        self.root = base / "repository"
        self.root.mkdir()
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
        self.request = base / "request.md"
        self.request.write_text(
            "# Request\n\n## Goal\n\nUpdate the fixture documentation.\n",
            encoding="utf-8",
        )
        initialized = self.invoke(
            "init", "--id", RUN_ID, "--title", "Complete fixture",
            "--request", str(self.request),
        )
        self.assertEqual(initialized["data"]["status"], "initialized")
        self.run_dir = self.root / ".specromancy" / "runs" / RUN_ID

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def invoke(self, *arguments: str) -> dict:
        command = list(arguments)
        common = ["--repo", str(self.root), "--format", "json"]
        if "--" in command:
            marker = command.index("--")
            command[marker:marker] = common
        else:
            command.extend(common)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(command)
        try:
            envelope = json.loads(output.getvalue())
        except json.JSONDecodeError:
            self.fail(f"CLI did not return JSON: {output.getvalue()!r}")
        self.assertEqual(code, 0, envelope)
        self.assertTrue(envelope["ok"], envelope)
        return envelope

    def _through_implementation(self) -> str:
        self.invoke("phase", "start", RUN_ID, "research")
        (self.run_dir / "research.md").write_text(research_artifact(), encoding="utf-8")
        self.invoke("phase", "complete", RUN_ID, "research")
        self.invoke("phase", "start", RUN_ID, "plan")
        (self.run_dir / "plan.md").write_text(plan_artifact(), encoding="utf-8")
        self.invoke("phase", "complete", RUN_ID, "plan")
        approval_gate = self.invoke("next", RUN_ID)
        self.assertTrue(approval_gate["data"]["action"].startswith("approve "))
        self.assertIn("approval", approval_gate["data"]["required_gate"])
        self.invoke("approve", RUN_ID, "plan", "--by", "integration-test")
        self.invoke("phase", "start", RUN_ID, "implementation")
        (self.root / "README.md").write_text("# Updated fixture\n", encoding="utf-8")
        verified = self.invoke(
            "verify", RUN_ID, "--", "python3", "-c", "print('ok')"
        )
        command_id = verified["data"]["command_id"]
        (self.run_dir / "implementation.md").write_text(
            implementation_artifact(command_id), encoding="utf-8"
        )
        self.invoke("phase", "complete", RUN_ID, "implementation")
        return command_id

    def test_complete_happy_path_and_event_replay(self) -> None:
        self._through_implementation()
        self.invoke("phase", "start", RUN_ID, "review")
        (self.run_dir / "review.md").write_text(review_artifact(), encoding="utf-8")
        completed = self.invoke("phase", "complete", RUN_ID, "review")
        self.assertEqual(completed["data"]["status"], "passed")
        status = self.invoke("status", RUN_ID)
        self.assertTrue(status["data"]["terminal"])
        self.assertEqual(status["data"]["status"], "passed")
        self.invoke("artifact", "verify", RUN_ID)
        paths = RepositoryPaths(self.root)
        projection = replay_events(load_events(paths.run_events(RUN_ID)), RUN_ID)
        self.assertEqual(projection.status, "passed")
        manifest = json.loads(paths.run_manifest(RUN_ID).read_text(encoding="utf-8"))
        self.assertEqual(projection.status, manifest["status"])

    def test_changes_requested_repair_and_fresh_review_pass(self) -> None:
        self._through_implementation()
        self.invoke("phase", "start", RUN_ID, "review")
        (self.run_dir / "review.md").write_text(
            review_artifact(
                verdict="changes_requested",
                findings=finding_row(),
                coverage="| REQ-001 | Missing | REV-001 identifies incomplete wording. |",
            ),
            encoding="utf-8",
        )
        changed = self.invoke("phase", "complete", RUN_ID, "review")
        self.assertEqual(changed["data"]["status"], "changes_requested")
        repaired = self.invoke("phase", "repair", RUN_ID, "implementation")
        self.assertEqual(repaired["data"]["status"], "implementation_in_progress")
        (self.root / "README.md").write_text("# Repaired fixture documentation\n", encoding="utf-8")
        verified = self.invoke(
            "verify", RUN_ID, "--", "python3", "-c", "print('repair ok')"
        )
        artifact = implementation_artifact(verified["data"]["command_id"])
        handoff = """| Finding ID | Status | Notes |
| --- | --- | --- |
| REV-001 | Addressed | README.md:1 contains the repaired wording. |"""
        artifact = artifact.replace("## Review handoff\n\nNone.", f"## Review handoff\n\n{handoff}")
        (self.run_dir / "implementation.md").write_text(artifact, encoding="utf-8")
        self.invoke("phase", "complete", RUN_ID, "implementation")
        self.invoke("phase", "start", RUN_ID, "review")
        reconciliation = """| Finding ID | Status | Evidence |
| --- | --- | --- |
| REV-001 | Fixed | README.md:1 contains the repaired wording. |"""
        (self.run_dir / "review.md").write_text(
            review_artifact(repair=reconciliation), encoding="utf-8"
        )
        passed = self.invoke("phase", "complete", RUN_ID, "review")
        self.assertEqual(passed["data"]["status"], "passed")
        status = self.invoke("status", RUN_ID)
        self.assertEqual(status["data"]["review_cycle"], 1)


if __name__ == "__main__":
    unittest.main()
