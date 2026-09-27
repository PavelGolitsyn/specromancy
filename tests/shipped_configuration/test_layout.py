from __future__ import annotations

import unittest
from pathlib import Path

from specromancy.config import (
    DEFAULT_PIPELINE_PATH,
    DEFAULT_PIPELINE_RELATIVE_PATH,
)


ROOT = Path(__file__).resolve().parents[2]


class ShippedLayoutTests(unittest.TestCase):
    def test_default_pipeline_is_in_the_customization_directory(self) -> None:
        self.assertEqual(
            DEFAULT_PIPELINE_RELATIVE_PATH,
            Path("workflow/pipeline.toml"),
        )
        self.assertEqual(DEFAULT_PIPELINE_PATH, ROOT / DEFAULT_PIPELINE_RELATIVE_PATH)
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
            ".agents/skills/",
            "AGENTS.md",
            "specromancy/",
        ):
            with self.subTest(path=path):
                self.assertIn(path, guide)


if __name__ == "__main__":
    unittest.main()
