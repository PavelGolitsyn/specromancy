"""Pure decision tables: all evidence is literal, with no store or disk IO."""
from __future__ import annotations

import copy
import unittest
from pathlib import Path

from specromancy._runs import visit_transitions as decisions
from specromancy._config.config_models import (
    PhaseConfig, PipelineConfig, TransitionConfig, ValidatorConfig,
)
from specromancy._runs.run_errors import RunCorruptionError, RunStoreError
from specromancy._runs.run_validation import validate_manifest


STAMP = "2026-09-25T12:00:00Z"
HASH = "a" * 64


def visit(status="pending", *, ordinal=1, phase="compose"):
    value = decisions.new_visit(
        phase_id=phase, ordinal=ordinal, attempt=ordinal, status="pending",
        inputs=[{"reference": "request", "path": "artifacts/request.md", "sha256": HASH}],
        output_path=f"artifacts/{ordinal}.md", mutation_policy="read-only",
        mutation_baseline=None, skill={"path": "skills/compose.md", "sha256": HASH},
        template=None, started_at=None,
    )
    value["status"] = status
    if status != "pending":
        value["started_at"] = STAMP
    if status == "completed":
        value["output"]["sha256"] = HASH
        value["completed_at"] = STAMP
        value["chosen_outcome"] = "again"
        value["transition_target"] = "compose"
    return value


def manifest(status="pending", *, run_status="active"):
    value = {
        "schema_version": 1, "revision": 7, "run_id": "20260925T120000Z-01020304",
        "pipeline": {"id": "fixture", "version": 1, "path": "pipeline.toml", "sha256": HASH},
        "status": run_status, "current_visit": 1,
        "request": {"path": "artifacts/request.md", "sha256": HASH},
        "git": {"base": None, "head": None}, "created_at": STAMP, "updated_at": STAMP,
        "visits": [visit(status)], "approvals": [], "terminal_result": None,
        "block_reason": None,
    }
    validate_manifest(value, value["run_id"])
    return value


def pipeline(*, max_visits=None, max_traversals=None):
    phase = PhaseConfig(
        id="compose", skill="compose", skill_path=Path("/unused/skill.md"),
        inputs=("request",), output_name="output.md", output_template=None,
        output_template_path=None, mutation="read-only", allowlist=(),
        completion_criteria=("Write.",), validator=ValidatorConfig("file"),
        commands=(), approval_conditions=(), stop_conditions=(),
        transitions=(TransitionConfig("again", "compose", max_traversals),),
        max_visits=max_visits,
    )
    return PipelineConfig(
        schema_version=1, id="fixture", version=1, start="compose",
        terminal_outcomes=("done",), artifact_pattern="artifacts/{visit}.md",
        allow_non_git=True, phases=(phase,), path=Path("/unused/pipeline.toml"),
        repository_root=Path("/unused"), canonical_json="{}", config_hash=HASH,
    )


class VisitDecisionTests(unittest.TestCase):
    def test_activation_table_and_paused_guard_priority(self):
        for status in ("pending", "active", "awaiting-approval", "completed", "blocked", "failed"):
            for paused in (False, True):
                with self.subTest(status=status, paused=paused):
                    source = manifest(status, run_status="paused" if paused else "active")
                    before = copy.deepcopy(source)
                    if paused or status not in {"pending", "active"}:
                        with self.assertRaises(RunStoreError) as raised:
                            decisions.activate_visit(source, 1, mutation_baseline={}, started_at=STAMP)
                        self.assertEqual(raised.exception.diagnostic_code,
                                         "run-paused" if paused else "illegal-visit-status")
                    else:
                        result = decisions.activate_visit(source, 1, mutation_baseline={}, started_at=STAMP)
                        self.assertEqual(result.event_type, "visit-activated" if status == "pending" else None)
                        self.assertEqual(result.manifest["revision"], 7)
                        self.assertEqual(result.manifest["updated_at"], STAMP)
                    self.assertEqual(source, before)

    def test_completion_and_transition_have_different_guards(self):
        for status in ("pending", "active", "awaiting-approval", "completed", "blocked", "failed"):
            with self.subTest(status=status):
                source = manifest(status)
                if status == "completed":
                    with self.assertRaises(RunStoreError):
                        decisions.require_incomplete(source, 1)
                    self.assertFalse(decisions.transition_needed(source, 1, "again", "compose"))
                    for outcome, target in (("done", "compose"), ("again", None)):
                        with self.assertRaises(RunStoreError) as raised:
                            decisions.transition_needed(source, 1, outcome, target)
                        self.assertEqual(raised.exception.diagnostic_code, "visit-already-completed")
                else:
                    decisions.require_incomplete(source, 1)
                    sealed = decisions.seal_visit(
                        source, 1, output_sha256=HASH, outcome="done",
                        transition_target=None, completed_at=STAMP,
                    )
                    self.assertEqual(sealed["visits"][0]["status"], "completed")
                    self.assertEqual(sealed["status"], source["status"])
                    if status in {"active", "awaiting-approval"}:
                        self.assertTrue(decisions.transition_needed(source, 1, "again", "compose"))
                    else:
                        with self.assertRaises(RunStoreError):
                            decisions.transition_needed(source, 1, "again", "compose")

    def test_limit_boundary_counts_and_precedence(self):
        for kind in ("phase", "transition"):
            for count in (1, 2, 3):
                with self.subTest(kind=kind, count=count):
                    source = manifest("active")
                    # Counting is by phase/outcome, without filtering visit status.
                    source["visits"] = [visit("blocked", ordinal=i + 1) for i in range(count)]
                    for item in source["visits"]:
                        item["chosen_outcome"] = "again"
                    source["visits"].append(visit("completed", ordinal=count + 1, phase="other"))
                    config = pipeline(max_visits=2 if kind == "phase" else None,
                                      max_traversals=2 if kind == "transition" else None)
                    reason = decisions.transition_limit_block(
                        source, config, source["visits"][0], "again", "compose", timestamp=STAMP,
                    )
                    if count < 2:
                        self.assertIsNone(reason)
                    else:
                        self.assertEqual(reason["reason"], "phase-visit-limit" if kind == "phase"
                                         else "transition-traversal-limit")
                        self.assertEqual(reason["limit"], 2)
                        self.assertEqual(reason["recorded_at"], STAMP)
        source = manifest("completed")
        reason = decisions.transition_limit_block(
            source, pipeline(max_visits=1, max_traversals=1), source["visits"][0],
            "again", "compose", timestamp=STAMP,
        )
        self.assertEqual(reason["reason"], "transition-traversal-limit")
        self.assertIsNone(decisions.transition_limit_block(
            source, pipeline(max_visits=1), source["visits"][0], "again", None, timestamp=STAMP,
        ))

    def test_successor_terminal_and_block_decisions_preserve_evidence(self):
        source = manifest("awaiting-approval")
        evidence = {"head": {"oid": "new"}}
        sealed = decisions.seal_visit(
            source, 1, output_sha256=HASH, outcome="again", transition_target="compose",
            completed_at=STAMP, mutation_result=evidence, validation_checks=[{"passed": True}],
            command_results=[{"exit_code": 0}],
        )
        successor = visit(ordinal=2)
        for pause in (False, True):
            result = decisions.finish_transition(sealed, 1, next_visit=successor, pause=pause)
            self.assertEqual(result.manifest["status"], "paused" if pause else "awaiting-agent")
            self.assertEqual(result.manifest["visits"][1]["status"], "pending")
            self.assertIsNone(result.manifest["visits"][1]["started_at"])
            self.assertEqual(result.manifest["git"]["head"], {"oid": "new"})
            self.assertEqual(result.payload, {"phase_id": "compose", "outcome": "again",
                                             "target": "compose", "paused": pause, "next_visit": 2})
        for terminal in (None, {}, {"custom": [1]}):
            result = decisions.finish_transition(sealed, 1, next_visit=None, pause=False,
                                                 terminal_result=terminal)
            self.assertEqual(result.manifest["terminal_result"], terminal if terminal is not None
                             else {"outcome": "again", "visit_number": 1})
        blocked = decisions.blocked_transition(source, 1, {"reason": "limit"}, mutation_result=evidence)
        self.assertEqual(len(blocked.manifest["visits"]), 1)
        self.assertIsNone(blocked.manifest["visits"][0]["output"]["sha256"])
        self.assertIsNone(blocked.manifest["visits"][0]["completed_at"])
        self.assertIsNone(blocked.manifest["visits"][0]["chosen_outcome"])
        evidence["head"]["oid"] = "changed"
        successor["inputs"].clear()
        self.assertEqual(sealed["git"]["head"], {"oid": "new"})
        self.assertEqual(source, manifest("awaiting-approval"))

    def test_resume_table_releases_only_a_pending_checkpoint(self):
        for status in ("active", "awaiting-agent", "awaiting-approval", "completed", "blocked", "failed"):
            source = manifest(run_status=status)
            result = decisions.resume_paused(source)
            self.assertIsNone(result.event_type)
            self.assertEqual(result.manifest, source)
        source = manifest(run_status="paused")
        result = decisions.resume_paused(source)
        self.assertEqual(result.manifest["status"], "awaiting-agent")
        self.assertEqual(result.manifest["visits"], source["visits"])
        self.assertIsNone(decisions.resume_paused(result.manifest).event_type)
        for status in ("active", "awaiting-approval", "completed", "blocked", "failed"):
            with self.assertRaises(RunCorruptionError):
                decisions.resume_paused(manifest(status, run_status="paused"))
        source["current_visit"] = None
        with self.assertRaises(RunCorruptionError):
            decisions.resume_paused(source)
