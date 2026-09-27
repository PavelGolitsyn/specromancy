from __future__ import annotations

import tempfile
import textwrap
import threading
import unittest
from pathlib import Path

from specromancy.config import load_pipeline
from specromancy.engine import Engine, EngineError
from specromancy.exit_codes import ExitCode
from specromancy.run_store import RunStore, RunStoreError


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
        before_approval = self.fixture.store.load(run_id)
        completed = self.fixture.engine.approve(run_id, "publish")
        self.assertEqual(completed["status"]["status"], "completed")
        after_approval = self.fixture.store.load(run_id)
        self.assertEqual(after_approval["revision"], before_approval["revision"] + 1)
        self.assertEqual(after_approval["approvals"][0]["status"], "approved")
        self.assertEqual(
            self.fixture.store.read_events(run_id)[-1]["type"], "approval-granted"
        )
        repeated = self.fixture.engine.approve(run_id, "publish")
        self.assertEqual(repeated["status"]["status"], "completed")
        self.assertEqual(len(self.fixture.store.load(run_id)["approvals"]), 1)

    def test_interrupted_approval_validation_leaves_request_pending(self) -> None:
        initialized = self.fixture.engine.initialize("Keep approval transactional")
        run_id = initialized["action"]["run_id"]
        self.fixture.engine.start_phase(run_id, "survey")
        self.fixture.output(run_id)
        self.fixture.engine.validate(run_id, "survey")
        self.fixture.engine.start_phase(run_id, "publish")
        self.fixture.output(run_id, "review me\n")
        self.fixture.engine.request_approval(run_id, reason="external-effect")
        original = self.fixture.engine._perform_validation

        def interrupt(*args: object, **kwargs: object) -> object:
            original(*args, **kwargs)
            raise RuntimeError("approval validation interrupted")

        self.fixture.engine._perform_validation = interrupt  # type: ignore[method-assign]
        with self.assertRaisesRegex(RuntimeError, "approval validation interrupted"):
            self.fixture.engine.approve(run_id, "publish")

        manifest = self.fixture.store.load(run_id)
        self.assertEqual(manifest["status"], "awaiting-approval")
        self.assertEqual(manifest["approvals"][0]["status"], "pending")
        self.assertNotIn(
            "approval-granted",
            [event["type"] for event in self.fixture.store.read_events(run_id)],
        )

    def test_status_sees_pending_request_during_approval_validation(self) -> None:
        initialized = self.fixture.engine.initialize("Observe approval atomically")
        run_id = initialized["action"]["run_id"]
        self.fixture.engine.start_phase(run_id, "survey")
        self.fixture.output(run_id)
        self.fixture.engine.validate(run_id, "survey")
        self.fixture.engine.start_phase(run_id, "publish")
        self.fixture.output(run_id, "review me\n")
        self.fixture.engine.request_approval(run_id, reason="external-effect")
        original = self.fixture.engine._perform_validation
        validation_started = threading.Event()
        allow_validation = threading.Event()
        results: list[dict[str, object]] = []
        failures: list[BaseException] = []

        def pause_validation(*args: object, **kwargs: object) -> object:
            validation_started.set()
            if not allow_validation.wait(timeout=5):
                raise RuntimeError("timed out waiting to finish approval validation")
            return original(*args, **kwargs)

        def approve() -> None:
            try:
                results.append(self.fixture.engine.approve(run_id, "publish"))
            except BaseException as exc:  # pragma: no cover - asserted below
                failures.append(exc)

        self.fixture.engine._perform_validation = pause_validation  # type: ignore[method-assign]
        worker = threading.Thread(target=approve)
        worker.start()
        try:
            self.assertTrue(validation_started.wait(timeout=5))
            status = self.fixture.engine.status(run_id)["status"]
            self.assertEqual(status["status"], "awaiting-approval")
            self.assertEqual(status["pending_approval"]["status"], "pending")
            self.assertEqual(
                status["next_command"],
                ["specromancy", "approve", run_id, "publish"],
            )
        finally:
            allow_validation.set()
            worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(results[0]["status"]["status"], "completed")

    def test_artifact_change_after_approval_validation_invalidates_request(self) -> None:
        initialized = self.fixture.engine.initialize("Reject a finalization race")
        run_id = initialized["action"]["run_id"]
        self.fixture.engine.start_phase(run_id, "survey")
        self.fixture.output(run_id)
        self.fixture.engine.validate(run_id, "survey")
        self.fixture.engine.start_phase(run_id, "publish")
        self.fixture.output(run_id, "review me\n")
        self.fixture.engine.request_approval(run_id, reason="external-effect")
        original = self.fixture.engine._perform_validation

        def change_after_validation(*args: object, **kwargs: object) -> object:
            result = original(*args, **kwargs)
            self.fixture.output(run_id, "changed after validation\n")
            return result

        self.fixture.engine._perform_validation = change_after_validation  # type: ignore[method-assign]
        with self.assertRaisesRegex(RunStoreError, "became stale"):
            self.fixture.engine.approve(run_id, "publish")

        manifest = self.fixture.store.load(run_id)
        self.assertEqual(manifest["status"], "awaiting-approval")
        self.assertEqual(manifest["approvals"][0]["status"], "stale")
        self.assertEqual(
            self.fixture.store.read_events(run_id)[-1]["type"],
            "approval-invalidated",
        )

    def test_status_recovers_legacy_granted_untransitioned_approval(self) -> None:
        initialized = self.fixture.engine.initialize("Resume a legacy approval")
        run_id = initialized["action"]["run_id"]
        self.fixture.engine.start_phase(run_id, "survey")
        self.fixture.output(run_id)
        self.fixture.engine.validate(run_id, "survey")
        self.fixture.engine.start_phase(run_id, "publish")
        self.fixture.output(run_id, "review me\n")
        self.fixture.engine.request_approval(run_id, reason="external-effect")

        def grant_without_transition(manifest: dict[str, object]) -> None:
            approval = manifest["approvals"][0]  # type: ignore[index]
            approval["status"] = "approved"
            approval["decision"] = "approved"
            approval["actor"] = "user"
            approval["decided_at"] = "2026-09-27T12:00:00.000000Z"

        self.fixture.store.mutate(
            run_id,
            "approval-granted",
            grant_without_transition,
            visit_number=2,
            payload={"phase_id": "publish", "actor": "user"},
        )
        status = self.fixture.engine.status(run_id)["status"]
        self.assertEqual(status["pending_approval"], None)
        self.assertEqual(status["next_command"], ["specromancy", "run", run_id])

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
