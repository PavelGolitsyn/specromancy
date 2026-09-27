from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from specromancy.config import load_pipeline
from specromancy.engine import Engine, EngineError
from specromancy.exit_codes import ExitCode
from specromancy.run_store import RunStore


PIPELINE = """
schema_version = 1
id = "engine-fixture"
version = 1
start = "survey"
terminal_outcomes = ["done", "blocked"]
artifact_pattern = "artifacts/{visit:03}-{phase}.md"
allow_non_git = true

[[phases]]
id = "survey"
skill = "survey"
inputs = ["request"]
output_name = "{visit:03}-survey.md"
mutation = "read-only"
completion_criteria = ["Produce evidence."]
validator = "file"
approval_conditions = []
stop_conditions = ["no-evidence"]
max_visits = 1
[[phases.transitions]]
outcome = "continue"
target = "publish"
[[phases.transitions]]
outcome = "blocked"

[[phases]]
id = "publish"
skill = "publish"
inputs = ["request", "latest:survey"]
output_name = "{visit:03}-publish.md"
mutation = "repository-write"
completion_criteria = ["Publish the result."]
validator = "file"
approval_conditions = ["external-effect"]
stop_conditions = ["no-target"]
max_visits = 1
[[phases.transitions]]
outcome = "done"
"""


class EngineFixture:
    def __init__(self, *, approval_required: bool = False) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".git").mkdir()
        for name in ("survey", "publish"):
            path = self.root / ".agents" / "skills" / name / "SKILL.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f"---\nname: {name}\ndescription: Fixture.\n---\n", encoding="utf-8"
            )
        self.pipeline_path = self.root / "pipeline.toml"
        source = textwrap.dedent(PIPELINE)
        if approval_required:
            source = source.replace(
                'approval_conditions = ["external-effect"]',
                'approval_required = true\napproval_conditions = ["external-effect"]',
            )
        self.pipeline_path.write_text(source, encoding="utf-8")
        self.pipeline = load_pipeline(self.pipeline_path, self.root)
        self.store = RunStore(self.root)
        self.engine = Engine(self.pipeline, self.store)

    def close(self) -> None:
        self.temporary.cleanup()

    def output(self, run_id: str, content: str = "result\n") -> None:
        manifest = self.store.load(run_id)
        self.store.write_visit_output(run_id, manifest["current_visit"], content)


class EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = EngineFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_happy_path_is_generic_and_idempotent(self) -> None:
        initialized = self.fixture.engine.initialize("Do the work")
        run_id = initialized["action"]["run_id"]
        self.assertEqual(initialized["code"], ExitCode.AGENT_ACTION_REQUIRED)
        self.assertEqual(initialized["action"]["visit_status"], "pending")

        first = self.fixture.engine.start_phase(run_id, "survey")
        repeated = self.fixture.engine.start_phase(run_id, "survey")
        self.assertEqual(first["action"], repeated["action"])
        self.fixture.output(run_id, "evidence\n")
        advanced = self.fixture.engine.validate(run_id, "survey")
        self.assertEqual(advanced["action"]["phase"], "publish")
        self.assertEqual(advanced["action"]["visit_status"], "pending")
        retried = self.fixture.engine.validate(run_id, "survey")
        self.assertEqual(retried["action"]["visit_id"], 2)

        self.fixture.engine.start_phase(run_id, "publish")
        self.fixture.output(run_id, "published\n")
        completed = self.fixture.engine.validate(run_id, "publish")
        self.assertEqual(completed["code"], ExitCode.SUCCESS)
        self.assertEqual(completed["status"]["status"], "completed")
        self.assertEqual(
            self.fixture.engine.validate(run_id, "publish")["status"]["status"],
            "completed",
        )

    def test_run_activates_pending_visit_and_stops_for_agent(self) -> None:
        initialized = self.fixture.engine.initialize("Run deterministically")
        run_id = initialized["action"]["run_id"]
        result = self.fixture.engine.run(run_id)
        self.assertEqual(result["code"], ExitCode.AGENT_ACTION_REQUIRED)
        self.assertEqual(result["action"]["visit_status"], "active")

    def test_approval_binds_hash_and_advances_once(self) -> None:
        initialized = self.fixture.engine.initialize("Need approval")
        run_id = initialized["action"]["run_id"]
        self.fixture.engine.start_phase(run_id, "survey")
        self.fixture.output(run_id)
        self.fixture.engine.validate(run_id)
        self.fixture.engine.start_phase(run_id, "publish")
        self.fixture.output(run_id, "external change\n")

        pending = self.fixture.engine.request_approval(
            run_id, reason="external-effect", details="User must decide"
        )
        self.assertEqual(pending["code"], ExitCode.APPROVAL_REQUIRED)
        completed = self.fixture.engine.approve(run_id, "publish")
        self.assertEqual(completed["status"]["status"], "completed")
        repeated = self.fixture.engine.approve(run_id, "publish")
        self.assertEqual(repeated["status"]["status"], "completed")
        self.assertEqual(len(self.fixture.store.load(run_id)["approvals"]), 1)

    def test_required_approval_is_created_by_validate_and_cannot_be_bypassed(self) -> None:
        fixture = EngineFixture(approval_required=True)
        try:
            initialized = fixture.engine.initialize("Require a human review")
            run_id = initialized["action"]["run_id"]
            self.assertFalse(initialized["action"]["approval_required"])
            fixture.engine.start_phase(run_id, "survey")
            fixture.output(run_id)
            next_phase = fixture.engine.validate(run_id, "survey")
            self.assertTrue(next_phase["action"]["approval_required"])

            fixture.engine.start_phase(run_id, "publish")
            fixture.output(run_id, "review this output\n")
            gated = fixture.engine.validate(run_id, "publish")
            self.assertEqual(gated["code"], ExitCode.APPROVAL_REQUIRED)
            self.assertEqual(gated["approval"]["reason"], "human-review")
            self.assertEqual(gated["status"]["status"], "awaiting-approval")
            self.assertEqual(
                gated["status"]["next_command"],
                ["specromancy", "approve", run_id, "publish"],
            )
            manifest = fixture.store.load(run_id)
            self.assertEqual(manifest["visits"][-1]["status"], "awaiting-approval")
            self.assertIsNone(manifest["visits"][-1]["chosen_outcome"])

            completed = fixture.engine.approve(run_id, "publish")
            self.assertEqual(completed["status"]["status"], "completed")
            events = fixture.store.read_events(run_id)
            self.assertIn("approval-requested", [event["type"] for event in events])
            self.assertIn("approval-granted", [event["type"] for event in events])
        finally:
            fixture.close()

    def test_required_approval_never_hides_artifact_validation_failure(self) -> None:
        fixture = EngineFixture(approval_required=True)
        try:
            run_id = fixture.engine.initialize("Reject invalid review input")["action"][
                "run_id"
            ]
            fixture.engine.start_phase(run_id, "survey")
            fixture.output(run_id)
            fixture.engine.validate(run_id, "survey")
            fixture.engine.start_phase(run_id, "publish")
            fixture.output(run_id, " \n")
            with self.assertRaises(EngineError) as raised:
                fixture.engine.validate(run_id, "publish")
            self.assertEqual(raised.exception.code, ExitCode.VALIDATION_FAILED)
            self.assertEqual(fixture.store.load(run_id)["approvals"], [])
        finally:
            fixture.close()

    def test_illegal_phase_empty_output_and_declared_block_are_enforced(self) -> None:
        initialized = self.fixture.engine.initialize("Stop safely")
        run_id = initialized["action"]["run_id"]
        with self.assertRaises(EngineError) as wrong:
            self.fixture.engine.start_phase(run_id, "publish")
        self.assertEqual(wrong.exception.code, ExitCode.ILLEGAL_TRANSITION)
        self.fixture.engine.start_phase(run_id, "survey")
        self.fixture.output(run_id, " \n")
        with self.assertRaises(EngineError) as empty:
            self.fixture.engine.validate(run_id)
        self.assertEqual(empty.exception.code, ExitCode.VALIDATION_FAILED)
        blocked = self.fixture.engine.block(run_id, reason="no-evidence")
        self.assertEqual(blocked["code"], ExitCode.RUN_BLOCKED)
        self.assertIsNone(self.fixture.store.load(run_id)["visits"][0]["output"]["sha256"])


if __name__ == "__main__":
    unittest.main()
