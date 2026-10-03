from __future__ import annotations

import unittest
from pathlib import Path

from specromancy.config import DEFAULT_PIPELINE_PATH


ROOT = Path(__file__).resolve().parents[2]


class ShippedLayoutTests(unittest.TestCase):
    def test_default_pipeline_is_in_the_customization_directory(self) -> None:
        self.assertEqual(DEFAULT_PIPELINE_PATH, ROOT / "workflow" / "pipeline.toml")
        self.assertTrue(DEFAULT_PIPELINE_PATH.is_file())

    def test_engine_package_contains_no_customizable_workflow_files(self) -> None:
        engine = ROOT / "specromancy"
        self.assertFalse((engine / "pipeline.toml").exists())
        self.assertFalse((engine / "templates").exists())
        self.assertEqual(list(engine.glob("*.md")), [])
        self.assertEqual(list(engine.glob("*.toml")), [])

    def test_customization_guide_names_every_authoritative_surface(self) -> None:
        guide = (ROOT / "workflow" / "README.md").read_text(encoding="utf-8")
        for path in (
            "workflow/pipeline.toml",
            "workflow/templates/",
            "workflow/skills/",
            "specromancy/artifacts/",
            "AGENTS.md",
            "specromancy/",
        ):
            with self.subTest(path=path):
                self.assertIn(path, guide)

    def test_engine_artifacts_have_sources_outside_the_workflow(self) -> None:
        artifacts = ROOT / "specromancy" / "artifacts"
        self.assertTrue((artifacts / "AGENTS.md").is_file())
        self.assertTrue((artifacts / "skills" / "pipeline" / "SKILL.md").is_file())
        self.assertFalse((ROOT / "workflow" / "skills" / "pipeline" / "SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
