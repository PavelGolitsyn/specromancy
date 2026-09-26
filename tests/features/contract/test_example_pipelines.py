from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from specromancy.config import load_pipeline
from specromancy.engine import Engine
from specromancy.exit_codes import ExitCode
from specromancy.run_store import RunStore


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "features" / "fixtures"
EXAMPLE_PIPELINE = FIXTURES / "example-pipeline"


class DefaultExamplePipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        shutil.copytree(EXAMPLE_PIPELINE, self.root, dirs_exist_ok=True)
        self.pipeline_path = self.root / "pipeline.toml"
        self.pipeline = load_pipeline(self.pipeline_path, self.root)
        self.store = RunStore(self.root)
        self.engine = Engine(self.pipeline, self.store)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_current(self, run_id: str, content: str) -> None:
        manifest = self.store.load(run_id)
        visit = manifest["current_visit"]
        assert visit is not None
        self.store.write_visit_output(run_id, visit, content)

    def start_and_write(self, run_id: str, phase: str, content: str) -> None:
        self.engine.start_phase(run_id, phase)
        self.write_current(run_id, content)

    def test_default_graph_has_mutation_approval_and_repair_contracts(self) -> None:
        phases = {phase.id: phase for phase in self.pipeline.phases}
        self.assertEqual(
            [phase.id for phase in self.pipeline.phases],
            ["research", "plan", "implement", "review"],
        )
        self.assertEqual(phases["research"].mutation, "read-only")
        self.assertEqual(phases["plan"].mutation, "read-only")
        self.assertEqual(phases["implement"].mutation, "repository-write")
        self.assertEqual(phases["review"].mutation, "read-only")
        self.assertEqual(
            phases["plan"].approval_conditions, ("material-scope-change",)
        )
        repair = next(
            item
            for item in phases["review"].transitions
            if item.outcome == "changes-requested"
        )
        self.assertEqual(repair.target, "implement")
        self.assertEqual(repair.max_traversals, 3)

    def test_plan_approval_and_review_repair_limit_are_enforced(self) -> None:
        initialized = self.engine.initialize("Implement the approved request")
        run_id = initialized["action"]["run_id"]

        self.start_and_write(
            run_id,
            "research",
            "# Research\n## Summary\nKnown.\n## Evidence\nFiles.\n## Open Questions\nNone.\n",
        )
        self.engine.validate(run_id, "research")
        self.start_and_write(
            run_id,
            "plan",
            "# Plan\n## Scope\nSmall.\n## Requirement Mapping\nMapped.\n"
            "## Intended Files\nOne.\n## Tests\nFocused.\n## Verification\nFull.\n"
            "## Risks and Approvals\nPlan approval.\n",
        )
        pending = self.engine.request_approval(
            run_id, reason="material-scope-change"
        )
        self.assertEqual(pending["code"], ExitCode.APPROVAL_REQUIRED)
        approved = self.engine.approve(run_id, "plan")
        self.assertEqual(approved["action"]["phase"], "implement")

        implementation = (
            "# Implementation\n## Changes\nApplied.\n## Deviations\nNone.\n"
            "## Verification\nPassed.\n"
        )
        review = (
            "# Review\n## Verdict\nChanges requested.\n## Findings\nRepair.\n"
            "## Verification\nInspected.\n"
        )
        for traversal in range(4):
            self.start_and_write(run_id, "implement", implementation)
            self.engine.validate(run_id, "implement")
            self.start_and_write(run_id, "review", review)
            result = self.engine.validate(
                run_id, "review", outcome="changes-requested"
            )
            if traversal < 3:
                self.assertEqual(result["action"]["phase"], "implement")

        self.assertEqual(result["code"], ExitCode.RUN_BLOCKED)
        manifest = self.store.load(run_id)
        self.assertEqual(manifest["status"], "blocked")
        self.assertEqual(
            manifest["block_reason"]["reason"], "transition-traversal-limit"
        )
        self.assertEqual(manifest["block_reason"]["limit"], 3)


class ReplacementPipelineContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        shutil.copytree(
            FIXTURES / "replacement-pipeline", self.root,
            dirs_exist_ok=True,
        )
        self.pipeline = self.root / "pipeline.toml"

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

    def start_write_validate(
        self,
        run_id: str,
        phase: str,
        content: str,
        *validation_arguments: str,
    ) -> dict[str, object]:
        started = self.command("phase", run_id, phase)
        self.assertEqual(started.returncode, ExitCode.AGENT_ACTION_REQUIRED, started.stderr)
        action = json.loads(started.stdout)["action"]
        Path(action["output"]["absolute_path"]).write_text(content, encoding="utf-8")
        validated = self.command("validate", run_id, phase, *validation_arguments)
        self.assertIn(
            validated.returncode,
            (ExitCode.AGENT_ACTION_REQUIRED, ExitCode.SUCCESS),
            validated.stderr,
        )
        return json.loads(validated.stdout)

    def test_unrelated_pipeline_completes_through_the_same_cli(self) -> None:
        configured = load_pipeline(self.pipeline, self.root)
        self.assertEqual(configured.phase_ids, ("inspect", "transform", "verify"))
        self.assertEqual(
            [item.outcome for item in configured.phase("verify").transitions],
            ["accepted", "rejected", "blocked"],
        )

        initialized = self.command("init", "Uppercase the source value")
        self.assertEqual(initialized.returncode, ExitCode.AGENT_ACTION_REQUIRED)
        run_id = json.loads(initialized.stdout)["action"]["run_id"]

        inspected = self.start_write_validate(
            run_id,
            "inspect",
            "# Inspection\n## Observations\nalpha\n## Selected Operation\nuppercase\n",
        )
        self.assertEqual(inspected["action"]["phase"], "transform")
        transformed = self.start_write_validate(
            run_id,
            "transform",
            "# Transformation\n## Operation\nuppercase\n## Result\nALPHA\n",
        )
        self.assertEqual(transformed["action"]["phase"], "verify")
        verified = self.start_write_validate(
            run_id,
            "verify",
            "# Verification\n## Checks\nMatched.\n## Decision\nAccepted.\n",
            "--outcome",
            "accepted",
        )
        self.assertEqual(verified["status"]["status"], "completed")
        self.assertEqual(verified["status"]["terminal_result"]["outcome"], "accepted")


if __name__ == "__main__":
    unittest.main()
