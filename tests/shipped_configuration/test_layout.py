from __future__ import annotations

import unittest
from pathlib import Path

from specromancy.registry import REGISTRY_PATH, load_registry


ROOT = Path(__file__).resolve().parents[2]


class ShippedLayoutTests(unittest.TestCase):
    def test_registry_and_graphs_are_in_the_customization_directory(self) -> None:
        self.assertEqual(REGISTRY_PATH, "workflow/pipelines.toml")
        registry = load_registry(ROOT)
        self.assertTrue(registry.pipelines)
        for registration in registry.pipelines:
            self.assertTrue(registration.path.is_relative_to(ROOT / "workflow/pipelines"))

    def test_engine_package_contains_no_customizable_workflow_files(self) -> None:
        engine = ROOT / "specromancy"
        self.assertFalse((engine / "pipeline.toml").exists())
        self.assertFalse((engine / "templates").exists())
        self.assertEqual(list(engine.glob("*.md")), [])
        self.assertEqual(list(engine.glob("*.toml")), [])

    def test_customization_guide_names_every_authoritative_surface(self) -> None:
        guide = (ROOT / "workflow" / "README.md").read_text(encoding="utf-8")
        for path in (
            "workflow/pipelines.toml",
            "workflow/pipelines/",
            "workflow/templates/",
            ".agents/skills/",
            "AGENTS.md",
            "specromancy/",
        ):
            with self.subTest(path=path):
                self.assertIn(path, guide)


if __name__ == "__main__":
    unittest.main()
