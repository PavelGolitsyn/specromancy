from __future__ import annotations

import re
import unittest
from pathlib import Path

from specromancy.config import load_pipeline
from specromancy.contracts import RESERVED_COMMANDS
from specromancy.validation import markdown_heading_counts


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_FIXTURE = ROOT / "tests" / "features" / "fixtures" / "example-pipeline"
FIXTURE_SKILLS = WORKFLOW_FIXTURE / ".agents" / "skills"
ALLOWED_FRONTMATTER = {"name", "description", "license", "compatibility", "metadata"}


def parse_portable_frontmatter(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise AssertionError(f"{path} has no frontmatter opening delimiter")
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise AssertionError(f"{path} has no frontmatter closing delimiter") from exc

    fields: dict[str, str] = {}
    metadata: dict[str, str] = {}
    in_metadata = False
    for line in lines[1:closing]:
        if line.startswith("  "):
            if not in_metadata or ":" not in line:
                raise AssertionError(f"{path} has non-portable nested frontmatter")
            key, value = line.strip().split(":", 1)
            metadata[key] = value.strip()
            continue
        if ":" not in line:
            raise AssertionError(f"{path} has malformed frontmatter: {line!r}")
        key, value = line.split(":", 1)
        fields[key] = value.strip()
        in_metadata = key == "metadata"
    return fields, metadata


class SkillFileFixtureTests(unittest.TestCase):
    def skill_paths(self) -> list[Path]:
        return sorted(FIXTURE_SKILLS.glob("*/SKILL.md"))

    def test_frontmatter_is_portable_and_names_match_directories(self) -> None:
        paths = self.skill_paths()
        self.assertEqual(
            [path.parent.name for path in paths],
            ["implement", "pipeline", "plan", "research", "review"],
        )
        for path in paths:
            with self.subTest(skill=path.parent.name):
                fields, metadata = parse_portable_frontmatter(path)
                self.assertEqual(set(fields), ALLOWED_FRONTMATTER)
                self.assertEqual(fields["name"], path.parent.name)
                self.assertRegex(fields["name"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                self.assertIn("when", fields["description"].lower())
                self.assertTrue(fields["license"])
                self.assertTrue(fields["compatibility"])
                self.assertTrue(metadata)
                self.assertTrue(all(key and value for key, value in metadata.items()))

    def test_referenced_commands_and_templates_exist(self) -> None:
        for path in self.skill_paths():
            text = path.read_text(encoding="utf-8")
            with self.subTest(skill=path.parent.name):
                commands = re.findall(r"bin/specromancy\s+([a-z-]+)", text)
                self.assertTrue(commands)
                self.assertTrue(set(commands).issubset(RESERVED_COMMANDS))
                for relative in re.findall(
                    r"specromancy/templates/[a-z0-9-]+\.md", text
                ):
                    self.assertTrue((WORKFLOW_FIXTURE / relative).is_file(), relative)

    def test_skills_have_no_vendor_or_unsafe_execution_instructions(self) -> None:
        forbidden = (
            "http://",
            "https://",
            "curl ",
            "wget ",
            "git reset",
            "git clean",
            "git add",
            "git commit",
            "rm -",
            "api key",
            "access token",
            "codex",
            "claude",
            "cursor",
        )
        for path in self.skill_paths():
            text = path.read_text(encoding="utf-8").lower()
            with self.subTest(skill=path.parent.name):
                for value in forbidden:
                    self.assertNotIn(value, text)
        orchestrator = (FIXTURE_SKILLS / "pipeline" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("never edit `run.json`", orchestrator)

    def test_default_templates_satisfy_declared_contracts(self) -> None:
        pipeline = load_pipeline(
            WORKFLOW_FIXTURE / "pipeline.toml", WORKFLOW_FIXTURE
        )
        for phase in pipeline.phases:
            with self.subTest(phase=phase.id):
                self.assertIsNotNone(phase.output_template_path)
                headings = markdown_heading_counts(
                    phase.output_template_path.read_text(encoding="utf-8")
                )
                for heading in phase.validator.required_headings:
                    self.assertEqual(headings.get(heading), 1)
        request_headings = markdown_heading_counts(
            (WORKFLOW_FIXTURE / "templates" / "request.md").read_text(encoding="utf-8")
        )
        for heading in ("Requirements", "Constraints", "Acceptance Criteria"):
            self.assertEqual(request_headings.get(heading), 1)


if __name__ == "__main__":
    unittest.main()
