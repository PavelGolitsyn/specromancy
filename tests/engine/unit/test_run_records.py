from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone

from specromancy._runs import run_errors, run_identity, run_records
from specromancy import run_store
from specromancy._runs import run_validation
from specromancy.engine import Engine
from specromancy.status import build_status, next_command
from tests.engine.contract.compatibility_support import RUN_ID, read_record


def manifest_at(state: str = "active") -> dict:
    return json.loads(read_record("states.json")[state]["run.json"])


class RecordValidationTests(unittest.TestCase):
    def test_invalid_status_shapes_raise_corruption_without_mutation(self) -> None:
        # No status value in this table is accepted version-1 data.
        for path, message in ((("status",), "manifest status is invalid"),
                              (("visits", 0, "status"), "visit identity or status is invalid")):
            for invalid in (None, False, True, 0, 1, 1.5, "unknown", [], {}):
                with self.subTest(path=path, invalid=invalid):
                    value = manifest_at()
                    target = value
                    for key in path[:-1]:
                        target = target[key]
                    target[path[-1]] = invalid
                    original = copy.deepcopy(value)
                    with self.assertRaises(run_store.RunCorruptionError) as raised:
                        run_validation.validate_manifest(value, RUN_ID)
                    self.assertEqual(str(raised.exception), message)
                    self.assertEqual(raised.exception.code, 12)
                    self.assertEqual(raised.exception.details,
                                     {"error_code": "corrupt-run", "run_id": RUN_ID})
                    self.assertEqual(value, original)

    def test_baseline_records_validate_without_mutation(self) -> None:
        for state, files in read_record("states.json").items():
            with self.subTest(state=state):
                manifest = json.loads(files["run.json"])
                original = copy.deepcopy(manifest)
                run_validation.validate_manifest(manifest, RUN_ID)
                self.assertEqual(manifest, original)
                for line in files["events.jsonl"].splitlines():
                    event = json.loads(line)
                    original_event = copy.deepcopy(event)
                    run_validation.validate_event(event, RUN_ID)
                    self.assertEqual(event, original_event)

    def test_required_and_extra_keys_are_rejected_at_closed_boundaries(self) -> None:
        paths = ((), ("pipeline",), ("git",), ("request",), ("visits", 0),
                 ("visits", 0, "inputs", 0), ("visits", 0, "output"),
                 ("visits", 0, "skill"))
        for path in paths:
            original = manifest_at()
            record = original
            for key in path:
                record = record[key]
            for missing in [*record, None]:
                value = copy.deepcopy(original)
                target = value
                for key in path:
                    target = target[key]
                if missing is None:
                    target["extra"] = None
                else:
                    del target[missing]
                with self.subTest(path=path, missing=missing):
                    with self.assertRaises(run_store.RunCorruptionError) as raised:
                        run_validation.validate_manifest(value, RUN_ID)
                    self.assertEqual(raised.exception.diagnostic_code, "corrupt-run")

    def test_invalid_records_keep_diagnostics(self) -> None:
        cases = [
            (("run_id",), "20261340T999999Z-01020304", "manifest run ID is invalid"),
            (("pipeline", "sha256"), "bad", "pipeline provenance is invalid"),
            (("request", "path"), "../request.md", "persisted path is unsafe"),
            (("request", "path"), "/absolute", "persisted path is unsafe"),
            (("request", "path"), "C:/drive", "persisted path is unsafe"),
            (("request", "path"), "a//b", "persisted path is unsafe"),
            (("request", "path"), "a/./b", "persisted path is unsafe"),
            (("request", "path"), "a\\b", "persisted path is unsafe"),
            (("request", "path"), None, "persisted path is invalid"),
            (("current_visit",), 2, "current visit is invalid"),
            (("visits", 0, "ordinal"), 2, "visit identity or status is invalid"),
            (("visits", 0, "attempt"), 2, "visit attempt is not ordered"),
            (("visits", 0, "output", "sha256"), "0" * 64, "artifact hash must be null until sealed"),
            (("visits", 0, "started_at"), None, "started visit lacks a start timestamp"),
            (("visits", 0, "skill", "sha256"), "bad", "provenance hash is invalid"),
            (("visits", 0, "template"), {}, "provenance record is invalid"),
            (("created_at",), "not-a-dateZ", "timestamp is invalid"),
            (("updated_at",), "2026-10-04T00:00:00+00:00", "timestamp is invalid"),
            (("approvals",), [None], "approvals must be an ordered object list"),
        ]
        for path, invalid, message in cases:
            value = manifest_at()
            target = value
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = invalid
            with self.subTest(path=path, invalid=invalid):
                with self.assertRaises(run_store.RunCorruptionError) as raised:
                    run_validation.validate_manifest(value, RUN_ID)
                self.assertEqual(str(raised.exception), message)
                self.assertEqual(raised.exception.details, {"error_code": "corrupt-run", "run_id": RUN_ID})
        completed = manifest_at("completed")
        completed["visits"][-1]["completed_at"] = None
        with self.assertRaisesRegex(run_store.RunCorruptionError, "completion timestamp"):
            run_validation.validate_manifest(completed, RUN_ID)
        completed["visits"][-1]["output"]["sha256"] = None
        with self.assertRaisesRegex(run_store.RunCorruptionError, "artifact hash is invalid"):
            run_validation.validate_manifest(completed, RUN_ID)

    def test_event_fields_identity_and_hash_are_checked(self) -> None:
        event = json.loads(read_record("states.json")["active"]["events.jsonl"].splitlines()[-1])
        invalid_fields = {"run_id": "20261004T000000Z-01020304", "sequence": 0,
                          "manifest_revision": 0, "manifest_hash": "bad",
                          "payload": [], "visit_number": 0, "type": "Bad_type",
                          "schema_version": 2, "timestamp": "badZ"}
        cases = []
        for key in event:
            value = dict(event)
            del value[key]
            cases.append(value)
        cases.append({**event, "extra": None})
        cases.extend({**event, key: value} for key, value in invalid_fields.items())
        for value in cases:
            with self.subTest(value=value), self.assertRaises(run_store.RunCorruptionError) as raised:
                run_validation.validate_event(value, RUN_ID)
            self.assertEqual(raised.exception.diagnostic_code, "corrupt-run")

    def test_legacy_weak_validation_is_not_silently_tightened(self) -> None:
        # These are follow-up candidates documented in Stage 03, not guarantees
        # that malformed nested records are safe to consume in the engine.
        value = manifest_at()
        value["revision"] = True
        value["schema_version"] = 1.0
        value["pipeline"]["id"] = ""
        value["pipeline"]["version"] = True
        value["current_visit"] = True
        value["approvals"] = [{}, {"status": 42, "unknown": [None]}]
        visit = value["visits"][0]
        visit["phase_id"] = ""
        visit["ordinal"] = 1.0
        visit["attempt"] = True
        visit["inputs"][0]["reference"] = ""
        visit["mutation_policy"] = {"unexpected": True}
        visit["chosen_outcome"] = []
        visit["transition_target"] = 7
        visit["validation_checks"] = [None, 42]
        visit["command_results"] = ["unstructured"]
        visit["completed_at"] = visit["started_at"]
        run_validation.validate_manifest(value, RUN_ID)
        value["terminal_result"] = float("nan")
        with self.assertRaisesRegex(run_store.RunCorruptionError, "not JSON serializable"):
            run_validation.validate_manifest(value, RUN_ID)

    def test_nested_compatibility_matrix_remains_accepted_without_mutation(self) -> None:
        cases = [
            (("approvals",), [{"visit_number": 999, "status": "pending"}]),
            (("git",), {"base": [], "head": 42}),
            (("visits", 0, "mutation_baseline"), {"files": []}),
            (("visits", 0, "mutation_result"), [None, 42]),
            (("visits", 0, "deviations"), [None, "unstructured"]),
            (("status",), "completed"),  # Current visit remains active.
            (("terminal_result",), ["unstructured"]),
            (("block_reason",), ["unstructured"]),
        ]
        for path, accepted in cases:
            with self.subTest(path=path):
                value = manifest_at()
                target = value
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = accepted
                original = copy.deepcopy(value)
                run_validation.validate_manifest(value, RUN_ID)
                self.assertEqual(value, original)

    def test_record_field_vocabulary_matches_schema_without_inserting_defaults(self) -> None:
        from pathlib import Path
        schemas = Path(run_store.__file__).parent / "schemas"
        run = json.loads((schemas / "run.schema.json").read_text())
        event = json.loads((schemas / "event.schema.json").read_text())
        for record, schema in (
            (run_records.RunRecord, run), (run_records.EventRecord, event),
            (run_records.VisitRecord, run["$defs"]["visit"]),
            (run_records.ArtifactRecord, run["$defs"]["outputArtifact"]),
            (run_records.InputArtifactRecord, run["$defs"]["inputArtifact"]),
        ):
            self.assertEqual(record.__required_keys__, set(schema["required"]))
            self.assertEqual(record(), {})
        self.assertEqual(run_records.ApprovalRecord.__required_keys__, set())


class IdentityCompatibilityTests(unittest.TestCase):
    def test_facade_reexports_the_original_objects(self) -> None:
        for module, names in (
            (run_errors, ("RunStoreError", "RunNotFoundError", "RunCorruptionError")),
            (run_identity, ("RUN_ID_PATTERN", "utc_now", "format_timestamp", "validate_run_id",
                            "is_valid_run_id", "generate_run_id")),
            (run_records, ("RUN_SCHEMA_VERSION", "EVENT_SCHEMA_VERSION", "EVENT_TYPE_PATTERN",
                           "RUN_STATUSES", "VISIT_STATUSES")),
        ):
            for name in names:
                self.assertIs(getattr(run_store, name), getattr(module, name))

    def test_utc_formatting_and_random_source_injection(self) -> None:
        for value in (datetime(2026, 10, 4, 12, 30, 1, 123456),
                      datetime(2026, 10, 4, 14, 30, 1, 123456,
                               tzinfo=timezone(timedelta(hours=2)))):
            self.assertEqual(run_store.format_timestamp(value), "2026-10-04T12:30:01.123456Z")
            calls = []
            def random_source(size):
                calls.append(size)
                return bytes.fromhex("01020304")
            self.assertEqual(run_store.generate_run_id(clock=lambda: value, random_source=random_source),
                             "20261004T123001Z-01020304")
            self.assertEqual(calls, [4])
            self.assertEqual(run_store.generate_run_id(clock=lambda: value, random_source=lambda: "01020304"),
                             "20261004T123001Z-01020304")
        def broken(size):
            raise TypeError("source failed")
        with self.assertRaisesRegex(TypeError, "source failed"):
            run_store.generate_run_id(random_source=broken)


class SelectionOutcomeTests(unittest.TestCase):
    def test_status_tolerates_absent_current_and_keeps_completed_current(self) -> None:
        value = manifest_at()
        for ordinal in (None, 999):
            value["current_visit"] = ordinal
            status = build_status(value, None)
            self.assertIsNone(status["current"])
            self.assertIsNone(status["next_command"])
            self.assertIsNone(Engine._current_visit(value))
        with self.assertRaises(run_store.RunStoreError) as raised:
            run_store.RunStore._visit(value, 999)
        self.assertEqual(raised.exception.diagnostic_code, "visit-not-found")
        value = manifest_at("completed")
        self.assertEqual(build_status(value, None)["current"]["status"], "completed")
        self.assertEqual(Engine._current_visit(value)["status"], "completed")

    def test_approval_status_is_global_but_next_command_and_engine_are_per_visit(self) -> None:
        value = manifest_at("awaiting-approval")
        current = value["current_visit"]
        first = {"status": "pending", "visit_number": current, "reason": "first"}
        second = {"status": "pending", "visit_number": current, "reason": "second"}
        approved = {"status": "approved", "visit_number": current}
        other = {"status": "pending", "visit_number": current + 1}
        value["approvals"] = [{}, first, second, approved, other]
        self.assertIs(build_status(value, None)["pending_approval"], other)
        self.assertIs(Engine._pending_approval(value, current), second)
        self.assertIs(Engine._approved_record(value, current), approved)
        self.assertEqual(next_command(value)[1], "approve")
        value["approvals"] = [approved, other]
        self.assertEqual(next_command(value)[1], "request-approval")
        self.assertIsNone(Engine._pending_approval(value, current))


if __name__ == "__main__":
    unittest.main()
