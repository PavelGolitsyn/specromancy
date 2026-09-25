from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from datetime import datetime, timezone
from pathlib import Path

from specromancy.artifacts import ArtifactError, resolve_input_reference
from specromancy.config import load_pipeline
from specromancy.hashing import sha256_json
from specromancy.locking import LockHeldError
from specromancy.run_store import (
    RunCorruptionError,
    RunStore,
    generate_run_id,
    is_valid_run_id,
    validate_run_id,
)


RUN_ID = "20260925T120000Z-01020304"


PIPELINE = """
schema_version = 1
id = "fixture"
version = 1
start = "compose"
terminal_outcomes = ["done"]
artifact_pattern = "artifacts/{visit:03}-{phase}.md"

[[phases]]
id = "compose"
skill = "compose"
inputs = ["request"]
output_name = "{visit:03}-result.md"
mutation = "read-only"
completion_criteria = ["Write a result."]
validator = "file"
approval_conditions = []
stop_conditions = []
max_visits = 2

[[phases.transitions]]
outcome = "done"
"""


class StoreFixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".git").mkdir()
        skill = self.root / ".agents" / "skills" / "compose" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\nname: compose\ndescription: Test skill.\n---\n",
            encoding="utf-8",
        )
        self.pipeline_path = self.root / "pipeline.toml"
        self.pipeline_path.write_text(textwrap.dedent(PIPELINE), encoding="utf-8")
        self.pipeline = load_pipeline(self.pipeline_path, self.root)

    def close(self) -> None:
        self.temporary.cleanup()


class RunIdTests(unittest.TestCase):
    def test_generation_is_deterministic_with_injected_sources(self) -> None:
        run_id = generate_run_id(
            clock=lambda: datetime(2026, 9, 25, 14, 30, 1, tzinfo=timezone.utc),
            random_source=lambda count: bytes.fromhex("a1b2c3d4"),
        )
        self.assertEqual(run_id, "20260925T143001Z-a1b2c3d4")
        self.assertTrue(is_valid_run_id(run_id))
        without_argument = generate_run_id(
            clock=lambda: datetime(2026, 9, 25, 14, 30, 1, tzinfo=timezone.utc),
            random_source=lambda: "01020304",
        )
        self.assertEqual(without_argument, "20260925T143001Z-01020304")

    def test_distinct_random_values_produce_distinct_ids(self) -> None:
        values = iter((bytes.fromhex("00000001"), bytes.fromhex("00000002")))
        clock = lambda: datetime(2026, 9, 25, 14, 30, 1, tzinfo=timezone.utc)
        first = generate_run_id(clock=clock, random_source=lambda count: next(values))
        second = generate_run_id(clock=clock, random_source=lambda count: next(values))
        self.assertNotEqual(first, second)

    def test_rejects_separators_dot_segments_bad_dates_and_uppercase_hex(self) -> None:
        for value in (
            "../20260925T143001Z-a1b2c3d4",
            "20260925T143001Z/a1b2c3d4",
            ".",
            "20261340T999999Z-a1b2c3d4",
            "20260925T143001Z-A1B2C3D4",
            "run-1",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_run_id(value)


class RunStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = StoreFixture()
        self.store = RunStore(self.fixture.root)

    def tearDown(self) -> None:
        self.fixture.close()

    def create(self) -> dict[str, object]:
        return self.store.create(
            self.fixture.pipeline,
            "Build the feature",
            run_id=RUN_ID,
            git_base={"head": "base"},
            git_head={"head": "current"},
        )

    def test_creation_writes_valid_request_manifest_and_first_event(self) -> None:
        manifest = self.create()
        directory = self.store.run_directory(RUN_ID)
        self.assertEqual(
            (directory / "artifacts" / "000-request.md").read_text(encoding="utf-8"),
            "Build the feature\n",
        )
        self.assertEqual(json.loads((directory / "run.json").read_text()), manifest)
        events = self.store.read_events(RUN_ID)
        self.assertEqual([event["type"] for event in events], ["run-created"])
        self.assertEqual(events[0]["sequence"], 1)
        self.assertEqual(events[0]["manifest_hash"], sha256_json(manifest))
        self.assertFalse((directory / ".lock").exists())

    def test_two_writers_cannot_lock_one_run(self) -> None:
        self.create()
        with self.store.lock(RUN_ID):
            with self.assertRaises(LockHeldError) as raised:
                RunStore(self.fixture.root).load(RUN_ID)
        self.assertIn("remove the lock file manually", raised.exception.details["remediation"])

    def test_completed_artifact_hash_detects_edits(self) -> None:
        self.create()
        visit = self.store.start_visit(RUN_ID, self.fixture.pipeline, "compose")
        self.store.write_visit_output(RUN_ID, visit["ordinal"], "# Result\n")
        sealed = self.store.complete_visit(RUN_ID, visit["ordinal"], outcome="done")
        output = self.store.run_directory(RUN_ID) / sealed["output"]["path"]
        output.write_text("changed\n", encoding="utf-8")
        with self.assertRaises(ArtifactError) as raised:
            self.store.load(RUN_ID)
        self.assertEqual(raised.exception.diagnostic_code, "artifact-hash-mismatch")

    def test_repeated_phase_visits_have_distinct_ordinals_paths_and_attempts(self) -> None:
        self.create()
        first = self.store.start_visit(RUN_ID, self.fixture.pipeline, "compose")
        self.store.write_visit_output(RUN_ID, 1, "first\n")
        self.store.complete_visit(RUN_ID, 1)
        resolved = resolve_input_reference(
            "visit:1", self.store.load(RUN_ID), self.store.run_directory(RUN_ID)
        )
        self.assertEqual(resolved["path"], first["output"]["path"])
        second = self.store.start_visit(RUN_ID, self.fixture.pipeline, "compose")
        self.assertEqual((first["ordinal"], second["ordinal"]), (1, 2))
        self.assertEqual((first["attempt"], second["attempt"]), (1, 2))
        self.assertNotEqual(first["output"]["path"], second["output"]["path"])
        self.assertTrue((self.store.run_directory(RUN_ID) / first["output"]["path"]).is_file())

    def test_symbolic_inputs_fail_safely_and_resolve_only_completed_outputs(self) -> None:
        manifest = self.create()
        directory = self.store.run_directory(RUN_ID)
        request = resolve_input_reference("request", manifest, directory)
        self.assertEqual(request["path"], "artifacts/000-request.md")
        for reference in ("latest:compose", "visit:1", "visit:0", "../request"):
            with self.subTest(reference=reference), self.assertRaises(ArtifactError):
                resolve_input_reference(reference, manifest, directory)

    def test_before_replace_fault_preserves_the_previous_complete_manifest(self) -> None:
        original = self.create()

        def fail(point: str) -> None:
            if point == "before-manifest-replace":
                raise RuntimeError("injected")

        self.store._fault_injector = fail
        with self.assertRaises(RuntimeError):
            self.store.block(RUN_ID, "test")
        raw = (self.store.run_directory(RUN_ID) / "run.json").read_text(encoding="utf-8")
        self.assertEqual(json.loads(raw), original)
        self.assertEqual(RunStore(self.fixture.root).load(RUN_ID), original)

    def test_after_replace_fault_is_recovered_with_an_audit_event(self) -> None:
        self.create()

        def fail(point: str) -> None:
            if point == "after-manifest-replace":
                raise RuntimeError("injected")

        self.store._fault_injector = fail
        with self.assertRaises(RuntimeError):
            self.store.block(RUN_ID, "interrupted")
        restarted = RunStore(self.fixture.root)
        recovered = restarted.load(RUN_ID)
        self.assertEqual(recovered["status"], "blocked")
        events = restarted.read_events(RUN_ID)
        self.assertEqual([event["type"] for event in events], ["run-created", "recovery"])
        self.assertEqual(events[-1]["manifest_hash"], sha256_json(recovered))

    def test_valid_but_unaudited_manifest_edit_is_detected_as_corruption(self) -> None:
        manifest = self.create()
        manifest["status"] = "failed"
        path = self.store.run_directory(RUN_ID) / "run.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(RunCorruptionError):
            self.store.load(RUN_ID)

    def test_path_escaping_manifest_reference_is_corruption(self) -> None:
        manifest = self.create()
        manifest["request"]["path"] = "../request.md"
        manifest["revision"] += 1
        path = self.store.run_directory(RUN_ID) / "run.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(RunCorruptionError):
            self.store.load(RUN_ID)

    def test_malformed_manifest_is_never_guessed_back_into_shape(self) -> None:
        self.create()
        path = self.store.run_directory(RUN_ID) / "run.json"
        path.write_text('{"status":', encoding="utf-8")
        with self.assertRaises(RunCorruptionError):
            self.store.load(RUN_ID)

    def test_schema_documents_are_valid_json(self) -> None:
        schemas = Path(__file__).resolve().parents[2] / "specromancy" / "schemas"
        run_schema = json.loads((schemas / "run.schema.json").read_text())
        event_schema = json.loads((schemas / "event.schema.json").read_text())
        self.assertEqual(run_schema["properties"]["schema_version"]["const"], 1)
        self.assertEqual(event_schema["properties"]["schema_version"]["const"], 1)


if __name__ == "__main__":
    unittest.main()
