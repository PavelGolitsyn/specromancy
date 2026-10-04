from __future__ import annotations

import hashlib
import unittest

import specromancy
from specromancy import artifacts, config, git, hashing, run_store
from specromancy import config_errors, config_models, schema_validation, validation
from specromancy import engine, engine_errors
from specromancy.engine import Engine
from tests.features.contract.compatibility_support import (
    RUN_ID, CompatibilityFixture, capture_canonical, capture_diagnostics,
    capture_lifecycle, normalize_response, read_record,
)
from tests.features.unit.test_adapters import AdapterFixture


class CompatibilityContractTests(unittest.TestCase):
    def test_configuration_and_schema_reexports_share_the_defining_objects(self) -> None:
        for name in (
            "PhaseConfig", "PipelineConfig", "TransitionConfig",
            "ValidationCommand", "ValidatorConfig",
        ):
            with self.subTest(name=name):
                self.assertIs(getattr(config, name), getattr(config_models, name))
        self.assertIs(config.PipelineConfigError, config_errors.PipelineConfigError)
        self.assertIs(config._MISSING, config_errors._MISSING)
        for name in (
            "SchemaDefinitionError", "load_json_schema", "validate_schema_definition",
        ):
            with self.subTest(name=name):
                self.assertIs(getattr(validation, name), getattr(schema_validation, name))

    def test_public_imports_and_compatibility_aliases_remain_available(self) -> None:
        self.assertIs(engine.EngineError, engine_errors.EngineError)
        self.assertIs(specromancy.EngineError, engine_errors.EngineError)
        exports = {
            "ExitCode", "Engine", "EngineError", "PipelineConfig", "PipelineConfigError",
            "PipelineRegistry", "PipelineRegistration", "RunCorruptionError",
            "RunNotFoundError", "RunStore", "generate_run_id", "load_pipeline",
            "load_registry", "validate_run_id",
        }
        self.assertLessEqual(exports, set(specromancy.__all__))
        for name in exports:
            self.assertTrue(callable(getattr(specromancy, name)), name)
        for module, aliases in (
            (hashing, {"hash_bytes": "sha256_bytes", "hash_text": "sha256_text",
                       "hash_json": "sha256_json", "hash_file": "sha256_file"}),
            (artifacts, {"resolve_artifact_reference": "resolve_input_reference",
                         "verify_artifacts": "verify_manifest_artifacts"}),
            (run_store, {"new_run_id": "generate_run_id", "CorruptRunError": "RunCorruptionError"}),
            (run_store.RunStore, {"create_run": "create", "load_run": "load",
                                  "create_visit": "start_visit", "update": "mutate"}),
            (git, {"snapshot_repository": "capture_repository_snapshot"}),
        ):
            for alias, target in aliases.items():
                with self.subTest(alias=alias):
                    self.assertIs(getattr(module, alias), getattr(module, target))
        fixture = CompatibilityFixture()
        try:
            self.assertEqual(config.load_config(fixture.path, fixture.root), fixture.pipeline)
            self.assertEqual(config.hash_pipeline(fixture.pipeline), fixture.pipeline.hash)
            phase = fixture.pipeline.phase("compose")
            self.assertEqual(phase.validation_commands, phase.commands)
        finally:
            fixture.close()

    def test_canonical_pipeline_bytes_and_hashes_match_baseline(self) -> None:
        expected = read_record("canonical.json")
        self.assertEqual(capture_canonical(), expected)
        self.assertEqual(expected["absent"], expected["false"])
        self.assertNotEqual(expected["absent"]["sha256"], expected["true"]["sha256"])
        for record in expected.values():
            self.assertEqual(
                hashlib.sha256(record["canonical"].encode("utf-8")).hexdigest(),
                record["sha256"],
            )
            self.assertIn(r"\u00c9", record["canonical"])
        # The generic hash serializer deliberately has a different Unicode contract.
        self.assertEqual(hashing.canonical_json_bytes({"text": "café 日本語"}),
                         '{"text":"café 日本語"}'.encode("utf-8"))

    def test_response_envelopes_and_persisted_bytes_match_baseline(self) -> None:
        states, responses = capture_lifecycle()
        self.assertEqual(responses, read_record("responses.json"))
        expected = read_record("states.json")
        self.assertEqual(set(states), set(expected))
        for state, files in states.items():
            with self.subTest(state=state):
                self.assertEqual(files, expected[state])

    def test_version_one_records_replay_and_recovery_is_exactly_once(self) -> None:
        states = read_record("states.json")
        responses = read_record("responses.json")
        for name, files in states.items():
            with self.subTest(state=name):
                fixture = CompatibilityFixture(pause=True)
                try:
                    fixture.restore(files)
                    manifest = fixture.store.load(RUN_ID)
                    self.assertEqual(manifest["schema_version"], 1)
                    expected = states["recovered"] if name == "recoverable" else files
                    self.assertEqual(fixture.snapshot(), expected)
                    fixture.store.load(RUN_ID)
                    fixture.store.read_events(RUN_ID)
                    self.assertEqual(fixture.snapshot(), expected)
                    engine = Engine(fixture.pipeline, fixture.new_store())
                    if name == "approved":
                        self.assertEqual(manifest["approvals"][0]["outcome"], "z-next")
                        self.assertEqual(manifest["approvals"][0]["status"], "approved")
                        self.assertEqual(normalize_response(engine.approve(RUN_ID, "compose"), fixture.root),
                                         responses["paused"])
                        self.assertEqual(fixture.snapshot(), states["paused"])
                    elif name == "paused":
                        self.assertEqual(normalize_response(engine.resume(RUN_ID), fixture.root),
                                         responses["resumed"])
                    elif name == "completed":
                        before = fixture.snapshot()
                        self.assertEqual(engine.run(RUN_ID)["status"]["status"], "completed")
                        self.assertEqual(fixture.snapshot(), before)
                finally:
                    fixture.close()

    def test_exact_error_envelopes_locations_and_cli_streams(self) -> None:
        self.assertEqual(capture_diagnostics(), read_record("diagnostics.json"))

    def test_generated_adapter_bytes_and_hashes_match_baseline(self) -> None:
        fixture = AdapterFixture()
        try:
            fixture.generate()
            expected = read_record("adapters.json")
            actual = fixture.snapshot()
            self.assertEqual(set(actual), set(expected))
            for path, content in actual.items():
                with self.subTest(path=path):
                    self.assertEqual(content, expected[path]["text"].encode("utf-8"))
                    self.assertEqual(hashlib.sha256(content).hexdigest(), expected[path]["sha256"])
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
