"""Persistence and interleaving characterizations for the visit boundary."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from specromancy.artifacts import ArtifactError
from specromancy.config import load_pipeline
from specromancy.engine import Engine
from specromancy.hashing import sha256_file, sha256_json
from specromancy.locking import LockHeldError
from specromancy.run_store import RunCorruptionError, RunStore, RunStoreError
from tests.features.unit.test_engine import EngineFixture
from tests.features.unit.test_run_store import PIPELINE, RUN_ID, StoreFixture


class VisitStoreBoundaryTests(unittest.TestCase):
    def test_output_collision_precedes_resource_reads_and_preserves_files(self):
        for reserved in (False, True):
            with self.subTest(reserved=reserved):
                fixture = StoreFixture()
                self.addCleanup(fixture.close)
                fixture.pipeline_path.write_text(PIPELINE.replace(
                    'artifacts/{visit:03}-{phase}.md', 'artifacts/result.md',
                ))
                pipeline = load_pipeline(fixture.pipeline_path, fixture.root)
                store = RunStore(fixture.root)
                store.create(pipeline, "collision", run_id=RUN_ID)
                directory = store.run_directory(RUN_ID)
                output = directory / "artifacts/result.md"
                if reserved:
                    store.start_visit(RUN_ID, pipeline, "compose")
                    store.write_visit_output(RUN_ID, 1, "reserved output")
                    store.complete_visit(RUN_ID, 1)
                    output.unlink()  # The manifest reservation alone must suffice.
                else:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_text("pre-existing output")
                pipeline.phase("compose").skill_path.unlink()
                before = {p.relative_to(directory): p.read_bytes()
                          for p in directory.rglob("*") if p.is_file()}
                with self.assertRaises(ArtifactError) as raised:
                    store.prepare_visit(RUN_ID, pipeline, "compose")
                self.assertEqual(raised.exception.diagnostic_code, "artifact-path-collision")
                self.assertEqual({p.relative_to(directory): p.read_bytes()
                                  for p in directory.rglob("*") if p.is_file()}, before)

    def test_preparation_reads_resources_under_lock_before_active_timestamp(self):
        for active in (False, True):
            with self.subTest(active=active):
                fixture = StoreFixture()
                self.addCleanup(fixture.close)
                template = fixture.root / "template.md"
                template.write_text("template at preparation")
                fixture.pipeline_path.write_text(PIPELINE.replace(
                    'mutation = "read-only"', 'output_template = "template.md"\nmutation = "read-only"',
                ))
                pipeline = load_pipeline(fixture.pipeline_path, fixture.root)
                skill = pipeline.phase("compose").skill_path
                original_skill_hash = sha256_file(skill)
                now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
                observed_at = datetime(2026, 9, 25, 13, tzinfo=timezone.utc)
                store = RunStore(fixture.root, clock=lambda: now)
                store.create(pipeline, "capture", run_id=RUN_ID)
                other = RunStore(fixture.root)
                original_open = Path.open

                def observe(path, *args, **kwargs):
                    nonlocal now
                    if path == template.resolve() and args == ("rb",):
                        with self.assertRaises(LockHeldError):
                            other.load(RUN_ID)
                        # A filesystem edit is not prevented by the run lock.
                        # Skill capture precedes template capture; start follows it.
                        skill.write_text("skill changed during template capture")
                        now = observed_at
                    return original_open(path, *args, **kwargs)

                with patch.object(Path, "open", observe):
                    if active:
                        visit = store.start_visit(RUN_ID, pipeline, "compose", mutation_baseline={"marker": 1})
                    else:
                        visit = store.prepare_visit(RUN_ID, pipeline, "compose")
                self.assertEqual(visit["skill"]["sha256"], original_skill_hash)
                self.assertNotEqual(visit["skill"]["sha256"], sha256_file(skill))
                self.assertEqual(visit["template"]["sha256"], sha256_file(template))
                self.assertEqual(visit["started_at"], "2026-09-25T13:00:00.000000Z" if active else None)
                self.assertEqual(visit["mutation_baseline"], {"marker": 1} if active else None)
                self.assertEqual(store.load(RUN_ID)["visits"], [visit])

    def test_successor_resource_failure_does_not_seal_or_commit(self):
        fixture = EngineFixture()
        self.addCleanup(fixture.close)
        run_id = fixture.engine.initialize("resource failure")["action"]["run_id"]
        fixture.engine.start_phase(run_id, "survey")
        fixture.output(run_id)
        directory = fixture.store.run_directory(run_id)
        before = tuple((directory / name).read_bytes() for name in ("run.json", "events.jsonl"))
        fixture.pipeline.phase("publish").skill_path.unlink()
        with self.assertRaises(FileNotFoundError):
            fixture.store.transition_visit(run_id, fixture.pipeline, 1,
                                           outcome="continue", transition_target="publish")
        self.assertEqual(before, tuple((directory / name).read_bytes()
                                      for name in ("run.json", "events.jsonl")))
        visit = fixture.store.load(run_id)["visits"][0]
        self.assertIsNone(visit["output"]["sha256"])
        self.assertIsNone(visit["completed_at"])

    def test_exact_loop_limits_commit_block_without_sealing_or_successor(self):
        for kind in ("phase", "transition"):
            with self.subTest(kind=kind):
                fixture = StoreFixture()
                self.addCleanup(fixture.close)
                content = PIPELINE + '\n[[phases.transitions]]\noutcome = "again"\ntarget = "compose"\n'
                if kind == "transition":
                    content = content.replace("max_visits = 2", "max_visits = 10")
                    content += "max_traversals = 1\n"
                fixture.pipeline_path.write_text(content)
                pipeline = load_pipeline(fixture.pipeline_path, fixture.root)
                store = RunStore(fixture.root, clock=lambda: datetime(2026, 9, 25, 12, tzinfo=timezone.utc))
                store.create(pipeline, "loop", run_id=RUN_ID)
                store.prepare_visit(RUN_ID, pipeline, "compose")
                expected_events = ["run-created", "visit-prepared"]
                for ordinal in (1, 2):
                    store.activate_visit(RUN_ID, pipeline, ordinal)
                    store.write_visit_output(RUN_ID, ordinal, f"output {ordinal}\n")
                    before = store.load(RUN_ID)
                    result = store.transition_visit(
                        RUN_ID, pipeline, ordinal, outcome="again", transition_target="compose",
                        mutation_result={"head": {"oid": str(ordinal)}},
                        validation_checks=[{"passed": True}], command_results=[{"exit_code": 0}],
                    )
                    expected_events.extend(["visit-activated", "visit-transitioned" if ordinal == 1
                                            else "loop-limit-exceeded"])
                    directory = store.run_directory(RUN_ID)
                    self.assertEqual(json.loads((directory / "run.json").read_text()), result)
                    self.assertEqual(result["revision"], before["revision"] + 1)
                    events = store.read_events(RUN_ID)
                    self.assertEqual([event["type"] for event in events], expected_events)
                    self.assertEqual([event["manifest_revision"] for event in events],
                                     list(range(1, result["revision"] + 1)))
                    self.assertEqual(events[-1]["manifest_hash"], sha256_json(result))
                    self.assertEqual(result["git"]["head"], {"oid": str(ordinal)})
                    self.assertEqual(len(result["visits"]), 2)
                    if ordinal == 1:
                        self.assertEqual(result["status"], "awaiting-agent")
                        self.assertEqual(events[-1]["payload"], {"phase_id": "compose", "outcome": "again",
                                         "target": "compose", "paused": False, "next_visit": 2})
                        snapshot = [(directory / name).read_bytes() for name in ("run.json", "events.jsonl")]
                        store.transition_visit(RUN_ID, pipeline, 1, outcome="again", transition_target="compose")
                        self.assertEqual(snapshot, [(directory / name).read_bytes()
                                                   for name in ("run.json", "events.jsonl")])
                    else:
                        reason = result["block_reason"]
                        self.assertEqual(reason["reason"], "phase-visit-limit" if kind == "phase"
                                         else "transition-traversal-limit")
                        self.assertEqual(reason["limit"], 2 if kind == "phase" else 1)
                        self.assertEqual(events[-1]["payload"], reason)
                        self.assertEqual(result["visits"][0], before["visits"][0])
                        blocked = result["visits"][1]
                        self.assertIsNone(blocked["output"]["sha256"])
                        self.assertIsNone(blocked["completed_at"])
                        self.assertIsNone(blocked["chosen_outcome"])
                        with self.assertRaises(RunStoreError):
                            store.transition_visit(RUN_ID, pipeline, 2, outcome="again", transition_target="compose")
                        self.assertEqual(store.load(RUN_ID), result)

    def test_pending_captures_provenance_once_and_complete_retains_its_guard(self):
        fixture = StoreFixture()
        self.addCleanup(fixture.close)
        template = fixture.root / "template.md"
        template.write_text("original template")
        fixture.pipeline_path.write_text(PIPELINE.replace('mutation = "read-only"',
                                                          'output_template = "template.md"\nmutation = "read-only"'))
        pipeline = load_pipeline(fixture.pipeline_path, fixture.root)
        store = RunStore(fixture.root)
        store.create(pipeline, "capture", run_id=RUN_ID)
        pending = store.prepare_visit(RUN_ID, pipeline, "compose")
        store.write_visit_output(RUN_ID, 1, "result")
        before = store.load(RUN_ID)
        # Low-level completion has no pending guard, but record validation still
        # rejects completing a visit that has never acquired a start timestamp.
        with self.assertRaises(RunCorruptionError):
            store.complete_visit(RUN_ID, 1)
        self.assertEqual(store.load(RUN_ID), before)
        template.write_text("changed template")
        pipeline.phase("compose").skill_path.write_text("changed skill")
        (store.run_directory(RUN_ID) / pending["inputs"][0]["path"]).write_text("changed request")
        active = store.activate_visit(RUN_ID, pipeline, 1)
        for key in ("inputs", "skill", "template"):
            self.assertEqual(active[key], pending[key])
        self.assertNotEqual(active["template"]["sha256"], sha256_file(template))
        # Store activation itself does not refresh inputs/provenance. Engine
        # integrity checks remain a separate command boundary.
        self.assertEqual(store.load(RUN_ID, verify_artifacts=False)["visits"][0], active)


class OverlappingAttemptTests(unittest.TestCase):
    def setUp(self):
        self.fixture = EngineFixture()
        self.addCleanup(self.fixture.close)
        self.engine = self.fixture.engine
        self.store = self.fixture.store
        self.other = Engine(self.fixture.pipeline, RunStore(self.fixture.root))
        self.run_id = self.engine.initialize("Interleaved attempts")["action"]["run_id"]
        self.engine.start_phase(self.run_id, "survey")
        self.fixture.output(self.run_id)

    def snapshot(self):
        directory = self.store.run_directory(self.run_id)
        return tuple((directory / name).read_bytes() for name in ("run.json", "events.jsonl"))

    def test_overlapping_validations_reload_and_do_not_duplicate_transition(self):
        original = self.engine._perform_validation
        committed = []

        def overlap(*args):
            evidence = original(*args)
            self.other.validate(self.run_id, "survey")
            committed.append(self.snapshot())
            return evidence

        with patch.object(self.engine, "_perform_validation", side_effect=overlap):
            self.engine.validate(self.run_id, "survey")
        self.assertEqual(self.snapshot(), committed[0])
        self.assertEqual(len(self.store.load(self.run_id)["visits"]), 2)

    def test_overlapping_different_outcomes_keep_the_first_commit(self):
        original = self.engine._perform_validation
        committed = []

        def overlap(*args):
            evidence = original(*args)
            self.other.store.transition_visit(
                self.run_id, self.fixture.pipeline, 1, outcome="blocked", transition_target=None,
            )
            committed.append(self.snapshot())
            return evidence

        with patch.object(self.engine, "_perform_validation", side_effect=overlap):
            with self.assertRaises(RunStoreError) as raised:
                self.engine.validate(self.run_id, "survey")
        self.assertEqual(raised.exception.diagnostic_code, "visit-already-completed")
        self.assertEqual(self.snapshot(), committed[0])

    def prepare_approval(self):
        self.engine.validate(self.run_id, "survey")
        self.engine.start_phase(self.run_id, "publish")
        self.fixture.output(self.run_id)
        self.engine.request_approval(self.run_id, reason="external-effect")

    def test_overlap_after_approval_grant_transitions_once(self):
        self.prepare_approval()
        original = self.engine._perform_validation
        committed = []

        def overlap(*args):
            evidence = original(*args)
            self.other.approve(self.run_id, "publish")
            committed.append(self.snapshot())
            return evidence

        with patch.object(self.engine, "_perform_validation", side_effect=overlap):
            self.engine.approve(self.run_id, "publish")
        self.assertEqual(self.snapshot(), committed[0])
        events = self.store.read_events(self.run_id)
        self.assertEqual(sum(event["type"] == "approval-granted" for event in events), 1)

    def test_overlap_before_approval_grant_exposes_existing_assertion(self):
        # Characterization of a pre-existing engine race, not a supported error
        # contract. A separate behavior change should replace this assertion.
        self.prepare_approval()
        original = self.store.mutate
        committed = []

        def overlap(*args, **kwargs):
            if args[1] == "approval-granted":
                self.other.approve(self.run_id, "publish")
                committed.append(self.snapshot())
            return original(*args, **kwargs)

        with patch.object(self.store, "mutate", side_effect=overlap):
            with self.assertRaises(AssertionError):
                self.engine.approve(self.run_id, "publish")
        self.assertEqual(self.snapshot(), committed[0])
        self.assertEqual(self.store.load(self.run_id)["status"], "completed")
