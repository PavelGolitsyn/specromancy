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


class CliContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".git").mkdir()
        skill = self.root / ".agents" / "skills" / "compose" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\nname: compose\ndescription: Fixture.\n---\n", encoding="utf-8"
        )
        self.pipeline = self.root / "pipeline.toml"
        self.pipeline.write_text(
            textwrap.dedent(
                """
                schema_version = 1
                id = "cli-fixture"
                version = 1
                start = "compose"
                terminal_outcomes = ["done"]
                artifact_pattern = "artifacts/{visit:03}-{phase}.md"
                allow_non_git = true
                [[phases]]
                id = "compose"
                skill = "compose"
                inputs = ["request"]
                output_name = "{visit:03}-result.md"
                mutation = "read-only"
                completion_criteria = ["Write a result."]
                validator = "file"
                approval_conditions = []
                stop_conditions = []
                max_visits = 1
                [[phases.transitions]]
                outcome = "done"
                """
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def command(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "specromancy",
                "--json",
                "--root",
                str(self.root),
                "--pipeline",
                str(self.pipeline),
                *arguments,
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_fresh_process_drives_full_run_with_dynamic_alias(self) -> None:
        initialized = self.command("init", "Build the fixture")
        self.assertEqual(initialized.returncode, ExitCode.AGENT_ACTION_REQUIRED)
        init_payload = json.loads(initialized.stdout)
        self.assertEqual(init_payload["schema_version"], 1)
        self.assertEqual(init_payload["action"]["visit_status"], "pending")
        run_id = init_payload["action"]["run_id"]

        started = self.command("compose", run_id)
        self.assertEqual(started.returncode, ExitCode.AGENT_ACTION_REQUIRED)
        action = json.loads(started.stdout)["action"]
        self.assertEqual(action["visit_status"], "active")
        Path(action["output"]["absolute_path"]).write_text(
            "complete\n", encoding="utf-8"
        )

        status = self.command("status", run_id)
        self.assertEqual(status.returncode, ExitCode.SUCCESS)
        self.assertEqual(json.loads(status.stdout)["status"]["status"], "active")
        completed = self.command("validate", run_id, "compose")
        self.assertEqual(completed.returncode, ExitCode.SUCCESS, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"]["status"], "completed")
        resumed = self.command("resume", run_id)
        self.assertEqual(resumed.returncode, ExitCode.SUCCESS)

    def test_generic_phase_and_run_commands_stop_at_agent_boundary(self) -> None:
        first = json.loads(self.command("init", "Generic phase").stdout)
        run_id = first["action"]["run_id"]
        generic = self.command("phase", run_id, "compose")
        self.assertEqual(generic.returncode, ExitCode.AGENT_ACTION_REQUIRED)
        self.assertEqual(json.loads(generic.stdout)["action"]["phase"], "compose")

        second = json.loads(self.command("init", "Deterministic run").stdout)
        run_id = second["action"]["run_id"]
        run = self.command("run", run_id)
        self.assertEqual(run.returncode, ExitCode.AGENT_ACTION_REQUIRED)
        self.assertEqual(json.loads(run.stdout)["action"]["visit_status"], "active")


if __name__ == "__main__":
    unittest.main()
