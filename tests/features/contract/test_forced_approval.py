from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from specromancy.exit_codes import ExitCode


ROOT = Path(__file__).resolve().parents[3]


class ForcedApprovalContractTests(unittest.TestCase):
    def test_cli_forces_human_review_and_reissues_stale_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(
                ["git", "-C", str(root), "init", "--quiet"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.email", "test@example.invalid"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "Contract Test"],
                check=True,
            )
            skill = root / ".agents" / "skills" / "compose" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                "---\nname: compose\ndescription: Fixture.\n---\n", encoding="utf-8"
            )
            pipeline = root / "pipeline.toml"
            pipeline.write_text(
                textwrap.dedent(
                    """
                    schema_version = 1
                    id = "forced-review"
                    version = 1
                    start = "compose"
                    terminal_outcomes = ["done"]
                    artifact_pattern = "artifacts/{visit:03}-{phase}.md"
                    [[phases]]
                    id = "compose"
                    skill = "compose"
                    inputs = ["request"]
                    output_name = "{visit:03}-result.md"
                    mutation = "read-only"
                    completion_criteria = ["Write a reviewed result."]
                    validator = "file"
                    approval_required = true
                    approval_conditions = ["exception"]
                    stop_conditions = []
                    max_visits = 1
                    [[phases.transitions]]
                    outcome = "done"
                    """
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "-C", str(root), "add", "."], check=True, capture_output=True
            )
            subprocess.run(
                ["git", "-C", str(root), "commit", "--quiet", "-m", "fixture"],
                check=True,
                capture_output=True,
            )

            def command(*arguments: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "specromancy",
                        "--json",
                        "--root",
                        str(root),
                        "--pipeline",
                        str(pipeline),
                        *arguments,
                    ],
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )

            initialized = command("init", "Require an actual reviewer")
            run_id = json.loads(initialized.stdout)["action"]["run_id"]
            started = command("phase", run_id, "compose")
            action = json.loads(started.stdout)["action"]
            self.assertTrue(action["approval_required"])
            output = Path(action["output"]["absolute_path"])
            output.write_text("reviewable result\n", encoding="utf-8")

            gated = command("validate", run_id, "compose")
            self.assertEqual(gated.returncode, ExitCode.APPROVAL_REQUIRED, gated.stderr)
            approval = json.loads(gated.stdout)["approval"]
            self.assertEqual(approval["reason"], "human-review")
            status = json.loads(command("status", run_id).stdout)["status"]
            self.assertEqual(status["status"], "awaiting-approval")

            output.write_text("reviewable result after feedback\n", encoding="utf-8")
            stale = command("approve", run_id, "compose")
            self.assertEqual(stale.returncode, ExitCode.APPROVAL_REQUIRED)
            stale_payload = json.loads(stale.stdout or stale.stderr)
            self.assertEqual(
                stale_payload["details"]["error_code"], "stale-approval"
            )

            reissued = command("request-approval", run_id)
            self.assertEqual(reissued.returncode, ExitCode.APPROVAL_REQUIRED)
            self.assertEqual(json.loads(reissued.stdout)["approval"]["reason"], "human-review")
            completed = command("approve", run_id, "compose")
            self.assertEqual(completed.returncode, ExitCode.SUCCESS, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["status"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
