from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from specromancy.registry import load_registry
from specromancy.exit_codes import ExitCode
from specromancy.validation import markdown_heading_counts


ROOT = Path(__file__).resolve().parents[2]
COMMAND_VALIDATION_SENTINEL = "SPECROMANCY_SHIPPED_COMMAND_VALIDATION"


class ShippedPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pipelines = load_registry(ROOT).load_all()

    def test_pipeline_loads_as_a_valid_graph_with_resolved_files(self) -> None:
        for pipeline in self.pipelines:
            phase_ids = set(pipeline.phase_ids)
            self.assertIn(pipeline.start, phase_ids)
            for phase in pipeline.phases:
                with self.subTest(phase=phase.id):
                    self.assertTrue(phase.skill_path.is_file())
                    self.assertTrue(phase.skill_path.is_relative_to(ROOT))
                    if phase.output_template_path is not None:
                        self.assertTrue(phase.output_template_path.is_file())
                        self.assertTrue(phase.output_template_path.is_relative_to(ROOT))
                    self.assertTrue(phase.transitions)
                    for transition in phase.transitions:
                        if transition.target is None:
                            self.assertIn(
                                transition.outcome, pipeline.terminal_outcomes
                            )
                        else:
                            self.assertIn(transition.target, phase_ids)

    def test_templates_satisfy_declared_heading_contracts(self) -> None:
        for pipeline in self.pipelines:
            for phase in pipeline.phases:
                with self.subTest(phase=phase.id):
                    if (
                        phase.output_template_path is None
                        or phase.validator.type != "markdown"
                    ):
                        continue
                    headings = markdown_heading_counts(
                        phase.output_template_path.read_text(encoding="utf-8")
                    )
                    for heading in phase.validator.required_headings:
                        count = headings.get(heading, 0)
                        if phase.validator.heading_occurrence == "exactly-once":
                            self.assertEqual(count, 1)
                        else:
                            self.assertGreaterEqual(count, 1)

    def test_each_registered_pipeline_initializes_from_a_fresh_checkout(self) -> None:
        for pipeline in self.pipelines:
            with tempfile.TemporaryDirectory() as temporary:
                checkout = Path(temporary) / "specromancy"

                def ignore(_directory: str, names: list[str]) -> set[str]:
                    return {
                        name
                        for name in names
                        if name in {".git", ".specromancy", "__pycache__"}
                        or name.endswith((".pyc", ".pyo"))
                    }

                shutil.copytree(ROOT, checkout, ignore=ignore)
                subprocess.run(
                    ["git", "-C", str(checkout), "init", "--quiet"],
                    check=True,
                    capture_output=True,
                )
                result = subprocess.run(
                    [
                        str(checkout / "bin" / "specromancy"),
                        "--json",
                        "init",
                        "--pipeline",
                        pipeline.id,
                        "Validate the shipped configuration",
                    ],
                    cwd=checkout,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    result.returncode, ExitCode.AGENT_ACTION_REQUIRED, result.stderr
                )
                action = json.loads(result.stdout)["action"]
                phase = pipeline.phase(pipeline.start)
                self.assertEqual(action["phase"], phase.id)
                self.assertEqual(
                    action["skill"]["path"],
                    phase.skill_path.relative_to(ROOT).as_posix(),
                )
                self.assertEqual(action["mutation"]["policy"], phase.mutation)
                self.assertEqual(action["mutation"]["allowlist"], list(phase.allowlist))
                self.assertEqual(
                    action["completion_criteria"], list(phase.completion_criteria)
                )
                self.assertEqual(
                    action["approval_conditions"], list(phase.approval_conditions)
                )
                self.assertEqual(action["stop_conditions"], list(phase.stop_conditions))
                self.assertEqual(
                    action["outcomes"],
                    [transition.outcome for transition in phase.transitions],
                )
                self.assertEqual(action["validation"]["type"], phase.validator.type)
                self.assertEqual(
                    action["validation"]["required_headings"],
                    list(phase.validator.required_headings),
                )
                expected_template = (
                    None
                    if phase.output_template_path is None
                    else phase.output_template_path.relative_to(ROOT).as_posix()
                )
                actual_template = (
                    None if action["template"] is None else action["template"]["path"]
                )
                self.assertEqual(actual_template, expected_template)

    @unittest.skipIf(
        os.environ.get(COMMAND_VALIDATION_SENTINEL) == "1",
        "avoid recursively executing shipped validation commands",
    )
    def test_required_validation_commands_succeed(self) -> None:
        commands = [
            command
            for pipeline in self.pipelines
            for phase in pipeline.phases
            for command in phase.commands
            if command.required
        ]
        for command in commands:
            with self.subTest(argv=command.argv):
                argv = list(command.argv)
                if (
                    argv
                    and argv[0] in {"python", "python3"}
                    and shutil.which(argv[0]) is None
                ):
                    argv[0] = sys.executable
                environment = os.environ.copy()
                environment[COMMAND_VALIDATION_SENTINEL] = "1"
                result = subprocess.run(
                    argv,
                    cwd=ROOT,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=command.timeout_seconds,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
