from __future__ import annotations

import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from specromancy.config import load_pipeline
from specromancy.engine import Engine
from specromancy.exit_codes import ExitCode
from specromancy.locking import LockHeldError
from specromancy.run_store import RunStore

from tests.features.contract.support import CliRepository


class InterruptionFixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".git").mkdir()
        skill = self.root / ".agents" / "skills" / "compose" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nname: compose\ndescription: Fixture.\n---\n", encoding="utf-8")
        self.pipeline_path = self.root / "pipeline.toml"
        command = json.dumps([sys.executable, "-c", "print('captured')"])
        self.pipeline_path.write_text(
            textwrap.dedent(
                f"""
                schema_version = 1
                id = "interruptions"
                version = 1
                start = "compose"
                terminal_outcomes = ["done"]
                artifact_pattern = "artifacts/{{visit:03}}-{{phase}}.md"
                allow_non_git = true
                [[phases]]
                id = "compose"
                skill = "compose"
                inputs = ["request"]
                output_name = "{{visit:03}}-result.md"
                mutation = "read-only"
                completion_criteria = ["Write a result."]
                validator = "file"
                approval_conditions = []
                stop_conditions = []
                max_visits = 1
                [[phases.commands]]
                argv = {command}
                timeout_seconds = 5
                required = true
                [[phases.transitions]]
                outcome = "done"
                """
            ),
            encoding="utf-8",
        )
        self.pipeline = load_pipeline(self.pipeline_path, self.root)
        self.store = RunStore(self.root)
        self.engine = Engine(self.pipeline, self.store)

    def close(self) -> None:
        self.temporary.cleanup()

    def initialize(self) -> str:
        return str(self.engine.initialize("Survive interruption")["action"]["run_id"])


class InterruptionContractTests(unittest.TestCase):
    def test_new_process_resumes_from_disk_only(self) -> None:
        repo = CliRepository()
        try:
            run_id = repo.initialize("Resume without conversation state")
            resumed = repo.command("resume", run_id)
            self.assertEqual(resumed.returncode, ExitCode.AGENT_ACTION_REQUIRED)
            action = repo.payload(resumed)["action"]
            self.assertEqual(action["run_id"], run_id)
            self.assertEqual(action["phase"], "research")
            self.assertEqual(action["visit_status"], "pending")
        finally:
            repo.close()

    def test_pipeline_change_during_run_is_rejected(self) -> None:
        repo = CliRepository()
        try:
            run_id = repo.initialize("Reject pipeline drift")
            repo.pipeline.write_text(
                repo.pipeline.read_text(encoding="utf-8").replace(
                    "Record repository evidence and unresolved questions.",
                    "Record repository evidence, risks, and unresolved questions.",
                ),
                encoding="utf-8",
            )
            resumed = repo.command("resume", run_id)
            self.assertEqual(resumed.returncode, ExitCode.INVALID_PIPELINE)
            self.assertEqual(
                repo.payload(resumed)["details"]["error_code"],
                "pipeline-hash-mismatch",
            )
        finally:
            repo.close()

    def test_manifest_faults_before_replace_preserve_previous_state(self) -> None:
        for point in (
            "before-manifest-temporary-write",
            "after-manifest-temporary-write",
        ):
            with self.subTest(point=point):
                fixture = InterruptionFixture()
                try:
                    run_id = fixture.initialize()
                    original = fixture.store.load(run_id)

                    def fail(candidate: str) -> None:
                        if candidate == point:
                            raise RuntimeError("injected")

                    fixture.store._fault_injector = fail
                    with self.assertRaisesRegex(RuntimeError, "injected"):
                        fixture.engine.start_phase(run_id, "compose")
                    fixture.store._fault_injector = None
                    restarted = Engine(fixture.pipeline, RunStore(fixture.root))
                    self.assertEqual(restarted.store.load(run_id), original)
                    self.assertEqual(
                        restarted.resume(run_id)["action"]["visit_status"], "pending"
                    )
                    self.assertEqual(
                        list(fixture.store.run_directory(run_id).glob(".run.json.*.tmp")),
                        [],
                    )
                finally:
                    fixture.close()

    def test_fault_after_replace_is_recovered_without_losing_transition(self) -> None:
        fixture = InterruptionFixture()
        try:
            run_id = fixture.initialize()

            def fail(point: str) -> None:
                if point == "after-manifest-replace":
                    raise RuntimeError("injected")

            fixture.store._fault_injector = fail
            with self.assertRaisesRegex(RuntimeError, "injected"):
                fixture.engine.start_phase(run_id, "compose")

            restarted_store = RunStore(fixture.root)
            restarted = Engine(fixture.pipeline, restarted_store)
            status = restarted.status(run_id)["status"]
            self.assertEqual(status["status"], "active")
            self.assertEqual(status["current"]["status"], "active")
            self.assertEqual(restarted_store.read_events(run_id)[-1]["type"], "recovery")
        finally:
            fixture.close()

    def test_command_capture_fault_leaves_visit_retriable(self) -> None:
        fixture = InterruptionFixture()
        try:
            run_id = fixture.initialize()
            fixture.engine.start_phase(run_id, "compose")
            fixture.store.write_visit_output(run_id, 1, "complete\n")

            def fail(point: str) -> None:
                if point == "after-command-stdout-write":
                    raise RuntimeError("capture interrupted")

            interrupted = Engine(
                fixture.pipeline,
                fixture.store,
                command_fault_injector=fail,
            )
            with self.assertRaisesRegex(RuntimeError, "capture interrupted"):
                interrupted.validate(run_id, "compose")

            restarted = Engine(fixture.pipeline, RunStore(fixture.root))
            self.assertEqual(restarted.status(run_id)["status"]["status"], "active")
            completed = restarted.validate(run_id, "compose")
            self.assertEqual(completed["status"]["status"], "completed")
        finally:
            fixture.close()

    def test_lock_contention_never_reads_or_changes_state(self) -> None:
        fixture = InterruptionFixture()
        try:
            run_id = fixture.initialize()
            with fixture.store.lock(run_id):
                with self.assertRaises(LockHeldError):
                    Engine(fixture.pipeline, RunStore(fixture.root)).status(run_id)
            status = Engine(fixture.pipeline, RunStore(fixture.root)).status(run_id)
            self.assertEqual(status["status"]["status"], "awaiting-agent")
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
