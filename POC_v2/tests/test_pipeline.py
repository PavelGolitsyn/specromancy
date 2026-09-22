from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "pipeline.py"


class PipelineTests(unittest.TestCase):
    def run_cli(self, workspace: Path, *arguments: str, expected: int = 0):
        result = subprocess.run(
            [sys.executable, str(CLI), *arguments, "--workspace", str(workspace)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(expected, result.returncode, result.stderr or result.stdout)
        return result

    def test_example_pipeline_can_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.run_cli(workspace, "validate")
            self.run_cli(workspace, "start", "--run", "demo", "--task", "Do work")

            prompt = self.run_cli(workspace, "prompt", "--run", "demo").stdout
            self.assertIn("# Pipeline stage: research", prompt)
            self.assertIn("name: research", prompt)

            for outcome in ("complete", "complete", "complete", "approved"):
                self.run_cli(
                    workspace,
                    "advance",
                    "--run",
                    "demo",
                    "--outcome",
                    outcome,
                    "--summary",
                    "stage finished",
                )

            state_path = workspace / ".specromancy/runs/demo/state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual("done", state["state"])
            self.assertEqual("completed", state["status"])
            self.assertEqual(4, state["transition_count"])

    def test_review_can_request_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.run_cli(workspace, "start", "--run", "loop", "--task", "Do work")
            for outcome in ("complete", "complete", "complete", "changes_requested"):
                self.run_cli(
                    workspace,
                    "advance",
                    "--run",
                    "loop",
                    "--outcome",
                    outcome,
                    "--summary",
                    "stage finished",
                )
            status = self.run_cli(workspace, "status", "--run", "loop", "--json")
            state = json.loads(status.stdout)
            self.assertEqual("implement", state["state"])
            self.assertEqual("active", state["status"])

    def test_unknown_outcome_is_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.run_cli(workspace, "start", "--run", "safe", "--task", "Do work")
            self.run_cli(
                workspace,
                "advance",
                "--run",
                "safe",
                "--outcome",
                "invented",
                "--summary",
                "not valid",
                expected=2,
            )
            status = self.run_cli(workspace, "status", "--run", "safe", "--json")
            state = json.loads(status.stdout)
            self.assertEqual("research", state["state"])
            self.assertEqual(0, state["transition_count"])

    def test_controller_has_no_dependency_on_example_stage_names(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            definition = workspace / "definition"
            skill = definition / "skills/draft/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                "---\nname: draft\ndescription: Draft a result.\n---\n\nDraft it.\n",
                encoding="utf-8",
            )
            config = definition / "pipeline.toml"
            config.write_text(
                """\
schema_version = 1
name = "replaceable-example"
initial = "draft"
work_dir = ".runs"
max_transitions = 2

[states.draft]
skill = "skills/draft/SKILL.md"

[states.draft.transitions]
ready = "shipped"

[states.shipped]
terminal = "completed"
""",
                encoding="utf-8",
            )
            config_args = ("--config", str(config))
            self.run_cli(workspace, "validate", *config_args)
            self.run_cli(
                workspace,
                "start",
                "--run",
                "custom",
                "--task",
                "Draft a note",
                *config_args,
            )
            prompt = self.run_cli(
                workspace, "prompt", "--run", "custom", *config_args
            ).stdout
            self.assertIn("# Pipeline stage: draft", prompt)
            self.run_cli(
                workspace,
                "advance",
                "--run",
                "custom",
                "--outcome",
                "ready",
                "--summary",
                "drafted",
                *config_args,
            )
            status = self.run_cli(
                workspace, "status", "--run", "custom", "--json", *config_args
            )
            self.assertEqual("completed", json.loads(status.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
