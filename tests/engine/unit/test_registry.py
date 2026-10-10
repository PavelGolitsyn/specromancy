from __future__ import annotations

import json
import re
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from specromancy.config import PipelineConfigError
from specromancy.registry import load_registry
from tests.engine.support import MultiPipelineFixture


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = MultiPipelineFixture()
        self.root = self.fixture.root
        self.path = self.root / "workflow/pipelines.toml"
        self.valid = self.path.read_text(encoding="utf-8")

    def tearDown(self) -> None:
        self.fixture.close()

    def test_many_registrations_share_skills_and_templates(self) -> None:
        registry = load_registry(self.root)
        first, second = registry.load_all()
        self.assertEqual((first.id, second.id), ("alpha", "beta"))
        self.assertEqual(first.phases[0].skill_path, second.phases[0].skill_path)
        self.assertEqual(first.phases[0].output_template_path, second.phases[0].output_template_path)
        with self.assertRaises(FrozenInstanceError):
            registry.pipelines = ()
        with self.assertRaises(FrozenInstanceError):
            registry.pipelines[0].id = "changed"
        self.fixture.register("beta", "alpha")
        self.assertEqual(load_registry(self.root).canonical_json, registry.canonical_json)
        self.fixture.register("alpha")
        self.assertEqual(len(load_registry(self.root).load_all()), 1)

    def test_invalid_registry_diagnostics(self) -> None:
        cases = {
            "missing": None,
            "syntax": "[",
            "empty": "schema_version = 1\npipelines = []\n",
            "table": "schema_version = 1\n[pipelines]\nid = 'alpha'\n",
            "version": self.valid.replace("schema_version = 1", "schema_version = 2"),
            "boolean-version": self.valid.replace("schema_version = 1", "schema_version = true"),
            "unknown": self.valid + "extra = true\n",
            "unknown-top-level": "extra = true\n" + self.valid,
            "duplicate-id": self.valid.replace('id = "beta"', 'id = "alpha"'),
            "duplicate-path": self.valid.replace("pipelines/beta.toml", "pipelines/alpha.toml"),
            "invalid-id": self.valid.replace('id = "alpha"', 'id = "Alpha"'),
            "wrong-id-type": self.valid.replace('id = "alpha"', "id = 4"),
            "wrong-path-type": self.valid.replace('path = "pipelines/alpha.toml"', "path = 4"),
            "missing-file": self.valid.replace("pipelines/alpha.toml", "pipelines/absent.toml"),
        }
        for name, document in cases.items():
            with self.subTest(name=name):
                if document is None:
                    self.path.unlink()
                else:
                    self.path.write_text(document, encoding="utf-8")
                with self.assertRaises(PipelineConfigError) as caught:
                    load_registry(self.root)
                self.assertIn("error_code", caught.exception.details)
                self.assertIn("remediation", caught.exception.details)
                self.assertEqual(caught.exception.details["path"], str(self.path))
                self.path.write_text(self.valid, encoding="utf-8")

    def test_unsafe_registration_paths_are_rejected(self) -> None:
        for path in ("/tmp/alpha.toml", "../alpha.toml", "pipelines/../alpha.toml", "alpha.toml",
                     "pipelines\\alpha.toml", "pipelines/alpha.json", "pipelines//alpha.toml", "pipelines/./alpha.toml"):
            with self.subTest(path=path):
                self.path.write_text(self.valid.replace("pipelines/alpha.toml", path.replace("\\", "\\\\")), encoding="utf-8")
                with self.assertRaises(PipelineConfigError) as caught:
                    load_registry(self.root)
                self.assertEqual(caught.exception.diagnostic_code, "unsafe-pipeline-path")

    def test_symlinks_cannot_escape_or_duplicate_pipeline_paths(self) -> None:
        alpha = self.root / "workflow/pipelines/alpha.toml"
        alias = alpha.with_name("alias.toml")
        alias.symlink_to(alpha)
        self.path.write_text(self.valid.replace("pipelines/beta.toml", "pipelines/alias.toml"), encoding="utf-8")
        with self.assertRaises(PipelineConfigError) as caught:
            load_registry(self.root)
        self.assertEqual(caught.exception.diagnostic_code, "duplicate-pipeline-path")
        alias.unlink()
        with tempfile.TemporaryDirectory() as temporary:
            outside = Path(temporary) / "outside.toml"
            outside.write_bytes(alpha.read_bytes())
            alias.symlink_to(outside)
            self.path.write_text(self.valid.replace("pipelines/alpha.toml", "pipelines/alias.toml"), encoding="utf-8")
            with self.assertRaises(PipelineConfigError) as caught:
                load_registry(self.root)
            self.assertEqual(caught.exception.diagnostic_code, "unsafe-pipeline-path")

    def test_id_mismatch_and_unknown_id_are_diagnostics(self) -> None:
        registry = load_registry(self.root)
        with self.assertRaises(PipelineConfigError) as caught:
            registry.load("absent")
        self.assertEqual(caught.exception.diagnostic_code, "unknown-pipeline")
        path = self.root / "workflow/pipelines/alpha.toml"
        path.write_text(path.read_text().replace('id = "alpha"', 'id = "different"'), encoding="utf-8")
        with self.assertRaises(PipelineConfigError) as caught:
            registry.load("alpha")
        self.assertEqual(caught.exception.diagnostic_code, "pipeline-id-mismatch")

    def test_registry_can_be_loaded_without_parsing_unrelated_graphs(self) -> None:
        (self.root / "workflow/pipelines/beta.toml").write_text("broken [", encoding="utf-8")
        self.assertEqual(load_registry(self.root).load("alpha").id, "alpha")
        with self.assertRaises(PipelineConfigError):
            load_registry(self.root).load_all()

    def test_registry_schema_publishes_nonempty_registration_contract(self) -> None:
        schema = json.loads((Path(__file__).resolve().parents[3] / "specromancy/schemas/pipelines.schema.json").read_text())
        self.assertEqual(schema["properties"]["schema_version"], {"type": "integer", "const": 1})
        self.assertEqual(schema["properties"]["pipelines"]["minItems"], 1)
        self.assertFalse(schema["additionalProperties"])
        pattern = schema["properties"]["pipelines"]["items"]["properties"]["path"]["pattern"]
        self.assertIsNotNone(re.fullmatch(pattern, "pipelines/alpha.toml"))
        self.assertIsNone(re.fullmatch(pattern, "pipelines/../alpha.toml"))
