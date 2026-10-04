from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import patch

from specromancy.config import load_pipeline
from specromancy.engine import Engine, EngineError
from specromancy.run_store import RunStore
from tests.features.contract.compatibility_support import (
    RUN_ID, CompatibilityFixture, read_record,
)
from tests.features.contract.test_safety import SafetyFixture, phase


class EngineOrchestrationContractTests(unittest.TestCase):
    def test_blocked_and_terminal_repeats_do_not_change_persisted_state(self) -> None:
        states = read_record("states.json")
        for boundary in ("blocked", "completed"):
            with self.subTest(boundary=boundary):
                fixture = CompatibilityFixture(pause=True)
                self.addCleanup(fixture.close)
                fixture.restore(states["active" if boundary == "blocked" else "completed"])
                if boundary == "blocked":
                    fixture.engine.block(RUN_ID, reason="no-evidence", details="No source.")
                before = fixture.snapshot()
                restarted = Engine(fixture.pipeline, fixture.new_store())
                if boundary == "blocked":
                    response = restarted.block(RUN_ID, reason="no-evidence", details="No source.")
                    self.assertEqual(response["message"], "run is already blocked")
                else:
                    response = restarted.validate(RUN_ID)
                    self.assertEqual(response["message"], "run is already completed")
                self.assertEqual(response["status"]["status"], boundary)
                self.assertEqual(restarted.run(RUN_ID)["status"]["status"], boundary)
                self.assertEqual(fixture.snapshot(), before)

    def test_pending_and_granted_drift_is_durable_before_error(self) -> None:
        states = read_record("states.json")
        for state in ("awaiting-approval", "approved"):
            for drift in ("artifact", "missing-output", "pipeline"):
                with self.subTest(state=state, drift=drift):
                    fixture = CompatibilityFixture(pause=True)
                    self.addCleanup(fixture.close)
                    fixture.restore(states[state])
                    before = fixture.store.load(RUN_ID)
                    output = fixture.store.run_directory(RUN_ID) / before["visits"][0]["output"]["path"]
                    pipeline = fixture.pipeline
                    if drift == "artifact":
                        output.write_text("Changed evidence.\n")
                    elif drift == "missing-output":
                        output.unlink()
                    else:
                        fixture.path.write_text(fixture.path.read_text().replace(
                            "Seal the result.", "Seal carefully."
                        ))
                        pipeline = load_pipeline(fixture.path, fixture.root)
                    restarted = Engine(pipeline, fixture.new_store())
                    with self.assertRaises(EngineError) as raised:
                        restarted.approve(RUN_ID, "compose")
                    self.assertEqual(raised.exception.diagnostic_code, "stale-approval")
                    mismatches = ["pipeline" if drift == "pipeline" else "artifact"]
                    self.assertEqual(raised.exception.details["mismatches"], mismatches)
                    after = fixture.new_store().load(RUN_ID)
                    self.assertEqual(after["revision"], before["revision"] + 1)
                    self.assertEqual(after["status"], "awaiting-approval")
                    self.assertEqual(after["approvals"][0]["status"], "stale")
                    for key in ("run_id", "phase_id", "visit_number", "artifact_sha256",
                                "pipeline_sha256", "outcome", "requested_at"):
                        self.assertEqual(after["approvals"][0][key], before["approvals"][0][key])
                    events = fixture.store.read_events(RUN_ID)
                    self.assertEqual(events[-1]["type"], "approval-invalidated")
                    self.assertEqual(events[-1]["payload"], {"mismatches": mismatches})
                    with self.assertRaises(EngineError):
                        restarted.approve(RUN_ID, "compose")
                    self.assertEqual(fixture.store.load(RUN_ID), after)
                    self.assertEqual(fixture.store.read_events(RUN_ID), events)

    def test_failed_revalidation_keeps_grant_and_can_resume(self) -> None:
        command = json.dumps([
            sys.executable, "-c",
            "import os; raise SystemExit(int(os.environ.get('REVALIDATE_FAIL', '0')))",
        ])
        configured = phase("publish", extra=f"[[phases.commands]]\nargv = {command}\n")
        configured = configured.replace(
            "approval_conditions = []", 'approval_conditions = ["accept"]'
        )
        fixture = SafetyFixture(configured)
        self.addCleanup(fixture.close)
        with patch.dict(os.environ, {"REVALIDATE_FAIL": "0"}):
            run_id = fixture.start()
            fixture.output(run_id)
            fixture.engine.request_approval(run_id, reason="accept")
            before = fixture.store.load(run_id)
            with patch.dict(os.environ, {"REVALIDATE_FAIL": "1"}):
                for attempt in (1, 2):
                    restarted = Engine(fixture.pipeline, RunStore(fixture.root))
                    with self.assertRaises(EngineError) as raised:
                        restarted.approve(run_id, "publish")
                    self.assertEqual(raised.exception.diagnostic_code, "validation-command-failed")
                    after = fixture.store.load(run_id)
                    self.assertEqual(after["revision"], before["revision"] + 1 + attempt)
                    self.assertEqual(after["status"], "awaiting-approval")
                    self.assertEqual(after["approvals"][0]["status"], "approved")
                    visit = after["visits"][0]
                    self.assertEqual(visit["command_results"][0]["exit_code"], 1)
                    self.assertEqual(visit["validation_checks"][0]["status"], "passed")
                    self.assertIsNotNone(visit["mutation_result"])
                    events = fixture.store.read_events(run_id)
                    self.assertEqual(sum(e["type"] == "approval-granted" for e in events), 1)
                    self.assertEqual(sum(e["type"] == "validation-failed" for e in events), attempt)
                    self.assertEqual(events[-1]["type"], "validation-failed")
                    if attempt == 1:
                        granted = after["approvals"]
                    else:
                        self.assertEqual(after["approvals"], granted)
            completed = Engine(fixture.pipeline, RunStore(fixture.root)).run(run_id)
            self.assertEqual(completed["status"]["status"], "completed")
            self.assertEqual(fixture.store.load(run_id)["approvals"], granted)

    def test_provenance_observations_warn_on_status_and_reject_commands(self) -> None:
        states = read_record("states.json")
        for drift in ("changed", "missing"):
            with self.subTest(drift=drift):
                fixture = CompatibilityFixture(pause=True)
                self.addCleanup(fixture.close)
                fixture.restore(states["awaiting-approval"])
                before = fixture.store.load(RUN_ID)
                skill = fixture.root / before["visits"][0]["skill"]["path"]
                if drift == "changed":
                    skill.write_text(skill.read_text() + "\nUpdated procedure.\n")
                else:
                    skill.unlink()
                expected = "provenance-hash-mismatch" if drift == "changed" else "provenance-missing"
                status = fixture.engine.status(RUN_ID)["status"]
                self.assertEqual([w["code"] for w in status["warnings"]], [expected])
                for operation in (lambda: fixture.engine.run(RUN_ID),
                                  lambda: fixture.engine.approve(RUN_ID, "compose")):
                    with self.assertRaises(EngineError) as raised:
                        operation()
                    self.assertEqual(raised.exception.diagnostic_code, expected)
                self.assertEqual(fixture.store.load(RUN_ID), before)
                request = fixture.store.run_directory(RUN_ID) / before["request"]["path"]
                request.write_text("Changed immutable input.\n")
                status = fixture.engine.status(RUN_ID)["status"]
                self.assertEqual(len(status["warnings"]), 2)
                self.assertEqual(status["warnings"][-1]["code"], expected)
                self.assertEqual(fixture.store.load(RUN_ID, verify_artifacts=False), before)

    def test_missing_artifact_failure_is_recorded_once_and_retriable(self) -> None:
        fixture = SafetyFixture(phase("inspect"))
        self.addCleanup(fixture.close)
        run_id = fixture.start()
        before = fixture.store.load(run_id)
        with self.assertRaises(EngineError):
            fixture.engine.validate(run_id)
        after = fixture.store.load(run_id)
        self.assertEqual(after["revision"], before["revision"] + 1)
        self.assertEqual(after["status"], "active")
        self.assertEqual(after["visits"][0]["validation_checks"][0]["status"], "failed")
        self.assertEqual(after["visits"][0]["command_results"], [])
        self.assertIsNone(after["visits"][0]["mutation_result"])
        self.assertEqual(fixture.store.read_events(run_id)[-1]["type"], "validation-failed")
        fixture.output(run_id)
        self.assertEqual(fixture.engine.validate(run_id)["status"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
