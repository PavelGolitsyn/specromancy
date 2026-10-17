"""Keep user-facing example procedures portable and the orchestrator in sync."""

from pathlib import Path
import unittest

from tests.shipped_configuration.test_skills import ALLOWED_FRONTMATTER, parse_frontmatter


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/release-documentation"


class ConsumerExampleSourcesTests(unittest.TestCase):
    def test_generic_orchestrator_matches_canonical_procedure(self) -> None:
        relative = ".agents/skills/pipeline/SKILL.md"
        self.assertEqual((EXAMPLE / relative).read_bytes(), (ROOT / relative).read_bytes())

    def test_example_skills_have_portable_frontmatter(self) -> None:
        skills = sorted((EXAMPLE / ".agents/skills").glob("*/SKILL.md"))
        self.assertEqual(len(skills), 3)
        for path in skills:
            with self.subTest(skill=path.parent.name):
                fields, metadata = parse_frontmatter(path)
                self.assertEqual(set(fields), ALLOWED_FRONTMATTER)
                self.assertEqual(fields["name"], path.parent.name)
                self.assertTrue(metadata)
                self.assertNotIn("bin/specromancy", path.read_text())
