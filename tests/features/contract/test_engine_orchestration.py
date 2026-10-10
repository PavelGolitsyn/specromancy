from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from specromancy.config import load_pipeline
from specromancy.engine import Engine, EngineError
from specromancy.exit_codes import ExitCode
from specromancy.run_store import RunStore
from tests.features.contract.compatibility_support import (
    NOW, RUN_ID, CompatibilityFixture, read_record,
)
from tests.features.contract.test_safety import SafetyFixture, phase


class EngineOrchestrationContractTests(unittest.TestCase):
    def test_approval_command_order_and_interrupted_grant_retries(self) -> None:
        command = json.dumps([
            sys.executable, "-c",
            "import json, os; from pathlib import Path; "
            "m = json.loads(Path(os.environ['APPROVAL_MANIFEST']).read_text()); "
            "p = Path(os.environ['APPROVAL_TRACE']); "
            "entry = [m['status'], [a['status'] for a in m['approvals']]]; "
            "p.write_text(p.read_text() + json.dumps(entry) + '\\n')",
        ])
        configured = phase("publish", extra=f"[[phases.commands]]\nargv = {command}\n")
        configured = configured.replace(
            "approval_conditions = []", 'approval_conditions = ["accept"]'
        )
        for continuation in ("approve", "run", "request"):
            with self.subTest(continuation=continuation):
                fixture = SafetyFixture(configured)
                self.addCleanup(fixture.close)
                temporary = tempfile.TemporaryDirectory()
                self.addCleanup(temporary.cleanup)
                trace = Path(temporary.name) / "commands.jsonl"
                trace.write_text("")
                run_id = fixture.start()
                fixture.output(run_id)
                before = fixture.store.load(run_id)
                directory = fixture.store.run_directory(run_id)
                with patch.dict(os.environ, {
                    "APPROVAL_MANIFEST": str(directory / "run.json"),
                    "APPROVAL_TRACE": str(trace),
                }):
                    fixture.engine.request_approval(run_id, reason="accept")
                    pending = fixture.store.load(run_id)
                    pending_events = fixture.store.read_events(run_id)
                    self.assertEqual(pending["revision"], before["revision"] + 1)
                    repeated = fixture.engine.request_approval(run_id, reason="accept")
                    self.assertEqual(repeated["message"], "approval is already pending")
                    with self.assertRaises(EngineError) as wrong_phase:
                        fixture.engine.approve(run_id, "absent")
                    self.assertEqual(wrong_phase.exception.diagnostic_code, "illegal-transition")
                    self.assertEqual(fixture.store.load(run_id), pending)
                    self.assertEqual(fixture.store.read_events(run_id), pending_events)

                    def interrupt(point: str) -> None:
                        if point == "after-command-stdout-write":
                            raise RuntimeError("approval validation interrupted")

                    interrupted = Engine(
                        fixture.pipeline, fixture.store, command_fault_injector=interrupt
                    )
                    with self.assertRaisesRegex(RuntimeError, "approval validation interrupted"):
                        interrupted.approve(run_id, "publish")
                    granted = fixture.store.load(run_id)
                    self.assertEqual(granted["revision"], pending["revision"] + 1)
                    self.assertEqual(granted["approvals"][0]["status"], "approved")
                    self.assertEqual(granted["visits"], pending["visits"])
                    events = fixture.store.read_events(run_id)
                    self.assertEqual(events[:-1], pending_events)
                    self.assertEqual(events[-1]["type"], "approval-granted")

                    if continuation == "approve":
                        result = fixture.engine.approve(run_id, "publish")
                    elif continuation == "run":
                        result = fixture.engine.run(run_id)
                    else:
                        result = fixture.engine.request_approval(run_id, reason="accept")
                    self.assertEqual(result["status"]["status"], "completed")
                    completed = fixture.store.load(run_id)
                    self.assertEqual(completed["revision"], granted["revision"] + 1)
                    self.assertEqual(completed["approvals"], granted["approvals"])
                    repeated = fixture.engine.approve(run_id, "publish")
                    self.assertEqual(repeated["message"], "approval was already recorded")
                    self.assertEqual(fixture.store.load(run_id), completed)
                observed = [json.loads(line) for line in trace.read_text().splitlines()]
                # Request-after-grant historically validates before selecting the
                # grant and again on continuation. Other retries validate once.
                self.assertEqual(observed, [
                    ["active", []],
                    ["awaiting-approval", ["pending"]],
                    *([["awaiting-approval", ["approved"]]] * (
                        3 if continuation == "request" else 2
                    )),
                ])

    def test_validation_hook_replaced_after_grant_is_resolved_at_revalidation(self) -> None:
        fixture = CompatibilityFixture(pause=True)
        self.addCleanup(fixture.close)
        fixture.restore(read_record("states.json")["awaiting-approval"])
        before = fixture.store.load(RUN_ID)
        original_decide = fixture.store.decide_approval

        def interrupted_validation(*args):
            raise RuntimeError("new validation hook interrupted")

        def grant_then_replace(*args, **kwargs):
            result = original_decide(*args, **kwargs)
            if result.event_type == "approval-granted":
                fixture.engine._perform_validation = interrupted_validation
            return result

        decision_time = NOW.replace(hour=13)
        with patch.object(fixture.store, "decide_approval", side_effect=grant_then_replace):
            with patch("specromancy.engine.utc_now", return_value=decision_time):
                with self.assertRaisesRegex(RuntimeError, "new validation hook interrupted"):
                    fixture.engine.approve(RUN_ID, "compose")
        granted = fixture.store.load(RUN_ID)
        self.assertEqual(granted["revision"], before["revision"] + 1)
        self.assertEqual(granted["visits"], before["visits"])
        self.assertEqual(granted["approvals"][0]["status"], "approved")
        self.assertEqual(granted["approvals"][0]["decided_at"], "2026-10-03T13:00:00.000000Z")
        self.assertEqual(fixture.store.read_events(RUN_ID)[-1]["type"], "approval-granted")

    def test_approval_gate_precedence_with_multiple_failures(self) -> None:
        states = read_record("states.json")
        fixture = CompatibilityFixture(pause=True)
        self.addCleanup(fixture.close)
        fixture.restore(states["awaiting-approval"])
        before = fixture.store.load(RUN_ID)
        visit = before["visits"][0]
        output = fixture.store.run_directory(RUN_ID) / visit["output"]["path"]
        output.unlink()
        # Reason and outcome selection precede validation; validation precedes
        # even the duplicate-pending decision and records its failure once.
        for reason, outcome, diagnostic in (
            ("undeclared", "undeclared", "undeclared-approval-reason"),
            (before["approvals"][0]["reason"], "undeclared", "undeclared-outcome"),
        ):
            with self.subTest(diagnostic=diagnostic):
                snapshot = fixture.snapshot()
                with self.assertRaises(EngineError) as raised:
                    fixture.engine.request_approval(RUN_ID, reason=reason, outcome=outcome)
                self.assertEqual(raised.exception.diagnostic_code, diagnostic)
                self.assertEqual(fixture.snapshot(), snapshot)
        with self.assertRaises(EngineError):
            fixture.engine.request_approval(RUN_ID, reason=before["approvals"][0]["reason"],
                                            outcome=before["approvals"][0]["outcome"])
        after = fixture.store.load(RUN_ID)
        self.assertEqual(after["revision"], before["revision"] + 1)
        self.assertEqual(after["approvals"], before["approvals"])
        self.assertEqual(fixture.store.read_events(RUN_ID)[-1]["type"], "validation-failed")

        # approve must audit artifact/pipeline staleness before skill provenance
        # rejection, even when all three fail simultaneously.
        fixture.path.write_text(fixture.path.read_text().replace("Seal the result.", "Seal carefully."))
        pipeline = load_pipeline(fixture.path, fixture.root)
        (fixture.root / visit["skill"]["path"]).unlink()
        with self.assertRaises(EngineError) as raised:
            Engine(pipeline, fixture.new_store()).approve(RUN_ID, "compose")
        self.assertEqual(raised.exception.diagnostic_code, "stale-approval")
        self.assertEqual(raised.exception.code, ExitCode.APPROVAL_REQUIRED)
        self.assertEqual(raised.exception.details["mismatches"], ["artifact", "pipeline"])
        final = fixture.store.load(RUN_ID)
        self.assertEqual(final["revision"], after["revision"] + 1)
        self.assertEqual(final["approvals"][0]["status"], "stale")
        self.assertEqual(fixture.store.read_events(RUN_ID)[-1]["type"], "approval-invalidated")

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

    def test_overtaken_grant_failure_retains_winner_and_retries_saved_outcome(self):
        fixture = CompatibilityFixture(pause=True)
        self.addCleanup(fixture.close)
        fixture.restore(read_record("states.json")["awaiting-approval"])
        winner = Engine(fixture.pipeline, fixture.new_store())
        original = fixture.store.decide_approval
        granted = []

        def overlap(*args, **kwargs):
            if not granted:
                with patch.object(winner, "_perform_validation", side_effect=RuntimeError("stop")):
                    with self.assertRaisesRegex(RuntimeError, "stop"):
                        winner.approve(RUN_ID, "compose")
                granted.append(fixture.store.load(RUN_ID))
            return original(*args, **kwargs)

        def fail_validation(manifest, visit, phase):
            fixture.store.record_validation_attempt(RUN_ID, visit["ordinal"],
                validation_checks=[{"status": "passed"}],
                command_results=[{"exit_code": 1}],
                diagnostic={"error_code": "validation-command-failed"})
            raise EngineError(ExitCode.VALIDATION_FAILED, "required command failed",
                              "validation-command-failed")

        before = fixture.store.load(RUN_ID)
        with patch.object(fixture.store, "decide_approval", side_effect=overlap):
            with patch.object(fixture.engine, "_perform_validation", side_effect=fail_validation):
                for attempt in (1, 2):
                    with self.assertRaises(EngineError) as raised:
                        fixture.engine.approve(RUN_ID, "compose")
                    self.assertEqual(raised.exception.diagnostic_code, "validation-command-failed")
                    after = fixture.store.load(RUN_ID)
                    self.assertEqual(after["revision"], before["revision"] + 1 + attempt)
                    self.assertEqual(after["approvals"], granted[0]["approvals"])
        result = fixture.engine.approve(RUN_ID, "compose")
        self.assertEqual(result["status"]["status"], "paused")
        events = fixture.store.read_events(RUN_ID)
        self.assertEqual([e["type"] for e in events][-4:], [
            "approval-granted", "validation-failed", "validation-failed", "visit-transitioned",
        ])
        self.assertEqual(fixture.store.load(RUN_ID)["visits"][0]["chosen_outcome"], "z-next")

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
