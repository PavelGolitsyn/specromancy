"""Public-store characterization of the durable protocol and clock ordering."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from specromancy.artifacts import ArtifactError
from specromancy.hashing import sha256_json
from specromancy.locking import LockHeldError
from specromancy.run_store import RunCorruptionError, RunStore, RunStoreError
from tests.features.unit.test_run_store import RUN_ID, StoreFixture


FAULT_POINTS = (
    "before-manifest-temporary-write",
    "after-manifest-temporary-write",
    "before-manifest-replace",
    "after-manifest-replace",
    "before-event-append",
    "after-event-append",
)


class PersistenceProtocolTests(unittest.TestCase):
    def fixture(self):
        fixture = StoreFixture()
        self.addCleanup(fixture.close)
        return fixture

    def files(self, directory):
        return {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}

    def test_every_fault_boundary_preserves_commit_or_recovers_once(self):
        for index, point in enumerate(FAULT_POINTS):
            with self.subTest(point=point):
                fixture = self.fixture()
                store = RunStore(fixture.root)
                original = store.create(fixture.pipeline, "café 日本語", run_id=RUN_ID)
                directory = store.run_directory(RUN_ID)
                before = self.files(directory)
                reached = []

                def fail(candidate):
                    reached.append(candidate)
                    self.assertTrue((directory / ".lock").exists())
                    if candidate == point:
                        if index in (1, 2):
                            temporary, = directory.glob(".run.json.*.tmp")
                            self.assertEqual(json.loads(temporary.read_bytes())["revision"], 2)
                        raise RuntimeError("injected")

                # Reassignment after construction is an existing injection seam.
                store._fault_injector = fail
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    store.block(RUN_ID, "interrupted")
                self.assertEqual(reached, list(FAULT_POINTS[:index + 1]))
                interrupted = self.files(directory)
                self.assertEqual(set(interrupted), {"run.json", "events.jsonl"})
                self.assertEqual((directory / "run.json").stat().st_mode & 0o777, 0o600)
                self.assertEqual((directory / "events.jsonl").stat().st_mode & 0o777, 0o600)
                if index < 3:
                    self.assertEqual(interrupted, before)
                else:
                    self.assertEqual(json.loads(interrupted["run.json"])["revision"], 2)
                    self.assertEqual(len(interrupted["events.jsonl"].splitlines()),
                                     2 if index == 5 else 1)

                restarted = RunStore(fixture.root)
                recovered = restarted.load(RUN_ID)
                events = restarted.read_events(RUN_ID)
                if index < 3:
                    self.assertEqual(recovered, original)
                    self.assertEqual(self.files(directory), before)
                else:
                    self.assertEqual(recovered["status"], "blocked")
                    self.assertEqual([e["type"] for e in events],
                                     ["run-created", "run-blocked" if index == 5 else "recovery"])
                    self.assertEqual(events[-1]["manifest_hash"], sha256_json(recovered))
                    self.assertEqual(events[-1]["manifest_revision"], 2)
                    self.assertEqual(events[-1]["sequence"], 2)
                    self.assertEqual(self.files(directory)["run.json"], interrupted["run.json"])
                after = self.files(directory)
                RunStore(fixture.root).load(RUN_ID)
                self.assertEqual(self.files(directory), after)

    def test_create_faults_leave_request_and_do_not_clean_up_partial_run(self):
        for index, point in enumerate(FAULT_POINTS):
            with self.subTest(point=point):
                fixture = self.fixture()

                def fail(candidate):
                    if candidate == point:
                        raise RuntimeError("injected")

                store = RunStore(fixture.root, fault_injector=fail)
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    store.create(fixture.pipeline, "request", run_id=RUN_ID)
                directory = store.run_directory(RUN_ID)
                self.assertEqual((directory / "artifacts/000-request.md").read_bytes(), b"request\n")
                self.assertTrue((directory / "commands").is_dir())
                self.assertFalse((directory / ".lock").exists())
                self.assertEqual(list(directory.glob(".run.json.*.tmp")), [])
                restarted = RunStore(fixture.root)
                if index < 3:
                    before = self.files(directory)
                    self.assertNotIn("run.json", before)
                    self.assertEqual(before["events.jsonl"], b"")
                    with self.assertRaises(RunCorruptionError):
                        restarted.load(RUN_ID)
                    self.assertEqual(self.files(directory), before)
                else:
                    manifest = restarted.load(RUN_ID)
                    self.assertEqual(manifest["revision"], 1)
                    self.assertEqual(manifest["visits"], [])
                    self.assertIsNone(manifest["current_visit"])
                    self.assertEqual([e["type"] for e in restarted.read_events(RUN_ID)],
                                     ["run-created" if index == 5 else "recovery"])
                with self.assertRaises(RunStoreError) as raised:
                    restarted.create(fixture.pipeline, "retry", run_id=RUN_ID)
                self.assertEqual(raised.exception.diagnostic_code, "run-already-exists")

    def test_load_options_separate_recovery_from_artifact_verification(self):
        for verify in (False, True):
            with self.subTest(verify=verify):
                fixture = self.fixture()
                store = RunStore(fixture.root)
                store.create(fixture.pipeline, "request", run_id=RUN_ID)

                def fail(point):
                    if point == "after-manifest-replace":
                        raise RuntimeError("injected")

                store._fault_injector = fail
                with self.assertRaises(RuntimeError):
                    store.block(RUN_ID, "interrupted")
                directory = store.run_directory(RUN_ID)
                (directory / "artifacts/000-request.md").write_text("changed")
                before = self.files(directory)
                restarted = RunStore(fixture.root)
                with self.assertRaises(RunCorruptionError):
                    restarted.load(RUN_ID, recover=False, verify_artifacts=verify)
                with self.assertRaises(RunCorruptionError):
                    restarted.read_events(RUN_ID, recover=False)
                self.assertEqual(self.files(directory), before)
                if verify:
                    with self.assertRaises(ArtifactError):
                        restarted.load(RUN_ID)
                else:
                    self.assertEqual(restarted.load(RUN_ID, verify_artifacts=False)["revision"], 2)
                events = restarted.read_events(RUN_ID, recover=False)
                self.assertEqual([e["type"] for e in events], ["run-created", "recovery"])
                self.assertEqual(self.files(directory)["run.json"], before["run.json"])

    def test_disagreement_outside_one_revision_gap_never_changes_files(self):
        for revision in (1, 4):
            with self.subTest(revision=revision):
                fixture = self.fixture()
                store = RunStore(fixture.root)
                store.create(fixture.pipeline, "request", run_id=RUN_ID)
                manifest = store.block(RUN_ID, "blocked")
                directory = store.run_directory(RUN_ID)
                manifest["revision"] = revision
                (directory / "run.json").write_text(json.dumps(manifest))
                before = self.files(directory)
                for recover in (False, True):
                    with self.assertRaises(RunCorruptionError):
                        RunStore(fixture.root).load(RUN_ID, recover=recover)
                    self.assertEqual(self.files(directory), before)

    def test_lock_contention_blocks_reads_and_mutations_without_changes(self):
        fixture = self.fixture()
        store = RunStore(fixture.root)
        store.create(fixture.pipeline, "request", run_id=RUN_ID)
        directory = store.run_directory(RUN_ID)
        with store.lock(RUN_ID):
            before = self.files(directory)
            restarted = RunStore(fixture.root)
            for operation in (lambda: restarted.load(RUN_ID),
                              lambda: restarted.block(RUN_ID, "blocked")):
                with self.assertRaises(LockHeldError):
                    operation()
                self.assertEqual(self.files(directory), before)

    def test_invalid_or_raising_mutations_leave_both_files_unchanged(self):
        fixture = self.fixture()
        store = RunStore(fixture.root)
        store.create(fixture.pipeline, "request", run_id=RUN_ID)
        directory = store.run_directory(RUN_ID)
        before = self.files(directory)

        def fail(manifest):
            manifest["status"] = "blocked"
            raise RuntimeError("mutator failed")

        for mutator, error in ((fail, RuntimeError),
                               (lambda m: m.update(status="invalid"), RunCorruptionError)):
            with self.assertRaises(error):
                store.mutate(RUN_ID, "test-mutation", mutator)
            self.assertEqual(self.files(directory), before)
            self.assertEqual(RunStore(fixture.root).load(RUN_ID)["revision"], 1)

    def test_advancing_clock_and_idempotent_operations_preserve_timing(self):
        fixture = self.fixture()
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        ticks = []

        def clock():
            ticks.append(now + timedelta(seconds=len(ticks)))
            return ticks[-1]

        store = RunStore(fixture.root, clock=clock)
        directory = store.runs_root / RUN_ID

        def check(operation, calls, revision, *, updated_offset=None, visit_time=None):
            start = len(ticks)
            before = self.files(directory) if directory.exists() else None
            operation()
            self.assertEqual(len(ticks) - start, calls)
            files = self.files(directory)
            manifest = json.loads(files["run.json"])
            events = [json.loads(line) for line in files["events.jsonl"].splitlines()]
            self.assertEqual(manifest["revision"], revision)
            self.assertEqual(len(events), revision)
            if updated_offset is None:
                self.assertEqual(files, before)
            else:
                def timestamp(offset):
                    return ticks[start + offset].isoformat(timespec="microseconds").replace("+00:00", "Z")
                self.assertEqual(manifest["updated_at"], timestamp(updated_offset))
                self.assertEqual(events[-1]["timestamp"], timestamp(calls - 1))
                self.assertEqual(events[-1]["manifest_hash"], sha256_json(manifest))
                if visit_time is not None:
                    field, offset = visit_time
                    self.assertEqual(manifest["visits"][-1][field], timestamp(offset))

        check(lambda: store.create(fixture.pipeline, "request", run_id=RUN_ID), 3, 1, updated_offset=1)
        check(lambda: store.prepare_visit(RUN_ID, fixture.pipeline, "compose"), 3, 2, updated_offset=1)
        check(lambda: store.activate_visit(RUN_ID, fixture.pipeline, 1), 4, 3,
              updated_offset=2, visit_time=("started_at", 1))
        check(lambda: store.activate_visit(RUN_ID, fixture.pipeline, 1), 1, 3)
        check(lambda: store.write_visit_output(RUN_ID, 1, "result"), 1, 3)
        check(lambda: store.record_validation_attempt(RUN_ID, 1), 3, 4, updated_offset=1)
        check(lambda: store.complete_visit(RUN_ID, 1), 4, 5,
              updated_offset=2, visit_time=("completed_at", 1))
        check(lambda: store.start_visit(RUN_ID, fixture.pipeline, "compose"), 4, 6,
              updated_offset=2, visit_time=("started_at", 1))
        check(lambda: store.write_visit_output(RUN_ID, 2, "result"), 1, 6)
        check(lambda: store.transition_visit(RUN_ID, fixture.pipeline, 2, outcome="done", transition_target=None),
              5, 7, updated_offset=3, visit_time=("completed_at", 2))
        check(lambda: store.transition_visit(RUN_ID, fixture.pipeline, 2, outcome="done", transition_target=None), 1, 7)
        check(lambda: store.resume_paused(RUN_ID, fixture.pipeline), 1, 7)
        # mutate always commits, even for a no-op; it resets caller-supplied revisions.
        check(lambda: store.mutate(RUN_ID, "test-mutation", lambda m: m.update(revision=100)),
              3, 8, updated_offset=1)
        check(lambda: store.mutate(RUN_ID, "test-mutation", lambda m: None), 3, 9, updated_offset=1)
