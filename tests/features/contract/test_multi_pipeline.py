from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from specromancy.exit_codes import ExitCode
from tests.features.support import MultiPipelineFixture


ROOT = Path(__file__).resolve().parents[3]


class MultiPipelineContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = MultiPipelineFixture()
        self.root = self.fixture.root

    def tearDown(self) -> None:
        self.fixture.close()

    def command(self, *arguments: str) -> tuple[int, dict]:
        result = subprocess.run(
            [sys.executable, "-m", "specromancy", "--root", str(self.root), "--json", *arguments],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        return result.returncode, json.loads(result.stdout or result.stderr)

    def initialize(self, pipeline_id: str) -> dict:
        code, payload = self.command("init", "Record evidence", "--pipeline", pipeline_id)
        self.assertEqual(code, ExitCode.AGENT_ACTION_REQUIRED, payload)
        return payload["action"]

    def test_init_requires_registered_id_even_for_one_pipeline(self) -> None:
        for ids in (("alpha", "beta"), ("alpha",)):
            self.fixture.register(*ids)
            code, payload = self.command("init", "Record evidence")
            self.assertEqual(code, ExitCode.USAGE_ERROR, payload)
            self.assertIn("no default", payload["message"])
            for selector in ("absent", str(self.root / "workflow/pipelines/alpha.toml")):
                code, payload = self.command("--pipeline", selector, "init", "Record evidence")
                self.assertEqual(code, ExitCode.INVALID_PIPELINE, payload)
            self.assertFalse((self.root / ".specromancy").exists())

    def test_fresh_processes_complete_two_graphs_using_recorded_selection(self) -> None:
        actions = [self.initialize("alpha"), self.initialize("beta")]
        for action, pipeline_id, phase in zip(actions, ("alpha", "beta"), ("compose", "inspect")):
            run_id = action["run_id"]
            self.assertNotIn("--pipeline", action["final_validation_command"])
            code, payload = self.command("status", run_id)
            self.assertEqual(code, ExitCode.SUCCESS, payload)
            self.assertEqual(payload["status"]["pipeline"]["id"], pipeline_id)
            code, payload = self.command(phase, run_id)
            self.assertEqual(code, ExitCode.AGENT_ACTION_REQUIRED, payload)
            self.assertEqual(payload["action"]["phase"], phase)
            Path(payload["action"]["output"]["absolute_path"]).write_text("## Result\nRecorded evidence.\n", encoding="utf-8")
            result = subprocess.run(payload["action"]["final_validation_command"], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, ExitCode.SUCCESS, result.stderr)
            code, payload = self.command("resume", run_id)
            self.assertEqual(code, ExitCode.SUCCESS, payload)
            self.assertEqual(payload["status"]["terminal_result"]["outcome"], "done")

    def test_alias_and_selector_cannot_switch_a_runs_graph(self) -> None:
        run_id = self.initialize("alpha")["run_id"]
        for selector in (
            "beta", "absent", "workflow/pipelines/beta.toml",
            "workflow/pipelines/alpha.toml", str(self.root / "workflow/pipelines/alpha.toml"),
        ):
            code, payload = self.command("status", run_id, "--pipeline", selector)
            self.assertEqual(code, ExitCode.USAGE_ERROR, payload)
        code, payload = self.command("inspect", run_id)
        self.assertEqual(code, ExitCode.USAGE_ERROR, payload)
        code, payload = self.command("status", run_id, "--pipeline", "alpha")
        self.assertEqual(code, ExitCode.SUCCESS, payload)
        code, payload = self.command("phase", run_id, "inspect")
        self.assertEqual(code, ExitCode.ILLEGAL_TRANSITION, payload)

    def test_unrelated_graph_edits_and_registry_reordering_preserve_run(self) -> None:
        run_id = self.initialize("alpha")["run_id"]
        self.fixture.register("beta", "alpha")
        (self.root / "workflow/pipelines/beta.toml").write_text("invalid [", encoding="utf-8")
        code, payload = self.command("resume", run_id)
        self.assertEqual(code, ExitCode.AGENT_ACTION_REQUIRED, payload)
        path = self.root / "workflow/pipelines/alpha.toml"
        path.write_text(path.read_text().replace("\nversion = 1", "\nversion = 2"), encoding="utf-8")
        code, payload = self.command("status", run_id)
        self.assertEqual(code, ExitCode.SUCCESS, payload)
        self.assertIn("pipeline-drift", {item["code"] for item in payload["status"]["warnings"]})
        code, payload = self.command("resume", run_id)
        self.assertEqual(code, ExitCode.INVALID_PIPELINE, payload)
        self.assertEqual(payload["details"]["error_code"], "pipeline-hash-mismatch")

    def test_removed_registration_disables_init_and_preserves_existing_run(self) -> None:
        run_id = self.initialize("alpha")["run_id"]
        self.fixture.register("beta")
        code, payload = self.command("init", "New request", "--pipeline", "alpha")
        self.assertEqual(code, ExitCode.INVALID_PIPELINE, payload)
        code, payload = self.command("compose", run_id)
        self.assertEqual(code, ExitCode.AGENT_ACTION_REQUIRED, payload)
        Path(payload["action"]["output"]["absolute_path"]).write_text("## Result\nEvidence.\n", encoding="utf-8")
        code, payload = self.command("validate", run_id)
        self.assertEqual(code, ExitCode.SUCCESS, payload)

    def test_common_option_positions_and_description_file(self) -> None:
        description = self.root / "request.md"
        description.write_text("A file request\n", encoding="utf-8")
        code, payload = self.command("--pipeline=beta", "init", "--description-file", "request.md")
        self.assertEqual(code, ExitCode.AGENT_ACTION_REQUIRED, payload)
        request = Path(payload["action"]["inputs"][0]["absolute_path"])
        self.assertEqual(request.read_text(), "A file request\n")
        run_id = payload["action"]["run_id"]
        code, payload = self.command("--pipeline", "beta", "status", run_id)
        self.assertEqual(code, ExitCode.SUCCESS, payload)
        code, payload = self.command("init", "Inline", "--description-file", "request.md", "--pipeline", "alpha")
        self.assertEqual(code, ExitCode.USAGE_ERROR, payload)

    def test_missing_registry_and_corrupt_or_missing_run_are_reported(self) -> None:
        code, payload = self.command("status", "20261003T000000Z-00000000")
        self.assertEqual(code, ExitCode.NOT_FOUND, payload)
        action = self.initialize("alpha")
        manifest = self.root / ".specromancy/runs" / action["run_id"] / "run.json"
        # Deliberately tamper only with test-owned state to exercise corruption.
        manifest.write_text("{}", encoding="utf-8")
        code, payload = self.command("status", action["run_id"])
        self.assertEqual(code, ExitCode.INTERNAL_ERROR, payload)
        (self.root / "workflow/pipelines.toml").unlink()
        code, payload = self.command("init", "Request", "--pipeline", "alpha")
        self.assertEqual(code, ExitCode.INVALID_PIPELINE, payload)
        code, payload = self.command("--help")
        self.assertEqual(code, ExitCode.SUCCESS, payload)

    def test_overlapping_phase_names_keep_pipeline_provenance(self) -> None:
        self.fixture.add_pipeline("beta", "compose")
        for pipeline_id in ("alpha", "beta"):
            action = self.initialize(pipeline_id)
            code, payload = self.command("compose", action["run_id"])
            self.assertEqual(code, ExitCode.AGENT_ACTION_REQUIRED, payload)
            code, payload = self.command("status", action["run_id"])
            self.assertEqual(payload["status"]["pipeline"]["id"], pipeline_id)
