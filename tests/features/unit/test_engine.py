from __future__ import annotations

import sys
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
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".git").mkdir()
        for name in ("survey", "publish"):
            path = self.root / "skills" / name / "SKILL.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f"---\nname: {name}\ndescription: Fixture.\n---\n", encoding="utf-8"
            )
        self.pipeline_path = self.root / "pipeline.toml"
        self.pipeline_path.write_text(textwrap.dedent(PIPELINE), encoding="utf-8")
        self.pipeline = load_pipeline(self.pipeline_path, self.root)
        self.store = RunStore(self.root)
        self.engine = Engine(self.pipeline, self.store)

    def enable_pause(self) -> None:
        content = textwrap.dedent(PIPELINE).replace(
            'outcome = "continue"\ntarget = "publish"',
            'outcome = "continue"\ntarget = "publish"\npause = true',
        )
        self.pipeline_path.write_text(content, encoding="utf-8")
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

    def test_paused_transition_requires_atomic_explicit_resume(self) -> None:
        self.fixture.enable_pause()
        initialized = self.fixture.engine.initialize("Pause between phases")
        run_id = initialized["action"]["run_id"]
        self.fixture.engine.start_phase(run_id, "survey")
        self.fixture.output(run_id, "evidence\n")

        paused = self.fixture.engine.validate(run_id, "survey")
        self.assertEqual(paused["code"], ExitCode.RUN_PAUSED)
        self.assertEqual(paused["status"]["status"], "paused")
        self.assertEqual(
            paused["status"]["next_command"], ["specromancy", "resume", run_id]
        )
        manifest = self.fixture.store.load(run_id)
        self.assertEqual(manifest["visits"][0]["status"], "completed")
        self.assertEqual(manifest["visits"][1]["status"], "pending")
        self.assertEqual(manifest["visits"][1]["phase_id"], "publish")
        self.assertTrue(
            self.fixture.store.read_events(run_id)[-1]["payload"]["paused"]
        )

        revision = manifest["revision"]
        event_count = len(self.fixture.store.read_events(run_id))
        self.assertEqual(self.fixture.engine.run(run_id)["code"], ExitCode.RUN_PAUSED)
        self.assertEqual(
            self.fixture.engine.start_phase(run_id, "publish")["code"],
            ExitCode.RUN_PAUSED,
        )
        self.assertEqual(
            self.fixture.engine.validate(run_id, "survey")["code"],
            ExitCode.RUN_PAUSED,
        )
        self.assertEqual(self.fixture.store.load(run_id)["revision"], revision)
        self.assertEqual(len(self.fixture.store.read_events(run_id)), event_count)

        resumed = self.fixture.engine.resume(run_id)
        self.assertEqual(resumed["code"], ExitCode.AGENT_ACTION_REQUIRED)
        self.assertEqual(resumed["action"]["phase"], "publish")
        self.assertEqual(resumed["action"]["visit_status"], "pending")
        self.assertEqual(self.fixture.store.load(run_id)["status"], "awaiting-agent")
        self.assertEqual(
            self.fixture.store.read_events(run_id)[-1]["type"], "run-resumed"
        )
        resumed_revision = self.fixture.store.load(run_id)["revision"]
        resumed_event_count = len(self.fixture.store.read_events(run_id))
        repeated = self.fixture.engine.resume(run_id)
        self.assertEqual(repeated["action"], resumed["action"])
        self.assertEqual(self.fixture.store.load(run_id)["revision"], resumed_revision)
        self.assertEqual(
            len(self.fixture.store.read_events(run_id)), resumed_event_count
        )

    def test_paused_resume_recovers_around_atomic_manifest_replacement(self) -> None:
        self.fixture.enable_pause()
        run_id = self.fixture.engine.initialize("Recover checkpoint resume")["action"][
            "run_id"
        ]
        self.fixture.engine.start_phase(run_id, "survey")
        self.fixture.output(run_id, "evidence\n")
        self.fixture.engine.validate(run_id, "survey")

        def fail_before(point: str) -> None:
            if point == "before-manifest-replace":
                raise RuntimeError("before replace")

        self.fixture.store._fault_injector = fail_before
        with self.assertRaisesRegex(RuntimeError, "before replace"):
            self.fixture.engine.resume(run_id)
        self.fixture.store._fault_injector = None
        self.assertEqual(self.fixture.store.load(run_id)["status"], "paused")

        def fail_after(point: str) -> None:
            if point == "after-manifest-replace":
                raise RuntimeError("after replace")

        self.fixture.store._fault_injector = fail_after
        with self.assertRaisesRegex(RuntimeError, "after replace"):
            self.fixture.engine.resume(run_id)
        restarted = RunStore(self.fixture.root)
        recovered = restarted.load(run_id)
        self.assertEqual(recovered["status"], "awaiting-agent")
        self.assertEqual(restarted.read_events(run_id)[-1]["type"], "recovery")

    def test_action_packets_preserve_the_complete_harness_contract(self) -> None:
        initialized = self.fixture.engine.initialize("Inspect action packets")
        self.assertEqual(
            set(initialized), {"schema_version", "kind", "code", "message", "action"}
        )
        first = initialized["action"]
        expected_keys = {
            "schema_version",
            "run_id",
            "visit_id",
            "visit_attempt",
            "visit_status",
            "phase",
            "skill",
            "inputs",
            "output",
            "template",
            "mutation",
            "completion_criteria",
            "validation",
            "approval_conditions",
            "stop_conditions",
            "outcomes",
            "final_validation_command",
        }
        self.assertEqual(set(first), expected_keys)
        self.assertEqual(
            set(first["skill"]), {"path", "sha256", "absolute_path"}
        )
        self.assertEqual(
            set(first["inputs"][0]),
            {"reference", "path", "sha256", "absolute_path"},
        )
        self.assertEqual(
            set(first["output"]), {"path", "sha256", "absolute_path"}
        )
        self.assertEqual(
            set(first["validation"]),
            {
                "type",
                "required_headings",
                "heading_occurrence",
                "schema",
                "commands",
            },
        )
        self.assertEqual(first["inputs"][0]["reference"], "request")
        self.assertEqual(
            first["final_validation_command"][:3],
            [sys.executable, "-m", "specromancy"],
        )
        self.assertEqual(
            first["final_validation_command"][-2:],
            [first["run_id"], "survey"],
        )

        run_id = first["run_id"]
        self.fixture.engine.start_phase(run_id, "survey")
        self.fixture.output(run_id, "evidence\n")
        second = self.fixture.engine.validate(run_id, "survey")["action"]
        self.assertEqual(set(second), expected_keys)
        self.assertEqual(second["phase"], "publish")
        self.assertEqual(
            [record["reference"] for record in second["inputs"]],
            ["request", "latest:survey"],
        )
        self.assertTrue(all(record["sha256"] for record in second["inputs"]))
        self.assertTrue(
            all(
                Path(record["absolute_path"]).is_absolute()
                for record in second["inputs"]
            )
        )

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
