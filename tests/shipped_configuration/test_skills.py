from __future__ import annotations

import re
import unittest
from pathlib import Path

from specromancy.config import DEFAULT_PIPELINE_PATH, load_pipeline
from specromancy.contracts import RESERVED_COMMANDS


ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / ".agents" / "skills"
ALLOWED_FRONTMATTER = {"name", "description", "license", "compatibility", "metadata"}


def parse_frontmatter(path: Path) -> tuple[dict[str, str], dict[str, str]]:
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


class ShippedSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pipeline = load_pipeline(DEFAULT_PIPELINE_PATH, ROOT)
        cls.paths = sorted(SKILLS.glob("*/SKILL.md"))

    def test_pipeline_skills_exist_and_all_shipped_skills_are_portable(self) -> None:
        available = {path.resolve() for path in self.paths}
        for phase in self.pipeline.phases:
            with self.subTest(phase=phase.id):
                self.assertIn(phase.skill_path.resolve(), available)
        for path in self.paths:
            with self.subTest(skill=path.parent.name):
                fields, metadata = parse_frontmatter(path)
                self.assertEqual(set(fields), ALLOWED_FRONTMATTER)
                self.assertEqual(fields["name"], path.parent.name)
                self.assertRegex(fields["name"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                self.assertIn("when", fields["description"].lower())
                self.assertEqual(fields["license"], "MIT")
                self.assertTrue(fields["compatibility"])
                self.assertTrue(metadata)
                self.assertTrue(all(key and value for key, value in metadata.items()))

    def test_skill_references_resolve_to_supported_commands_and_files(self) -> None:
        for path in self.paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(skill=path.parent.name):
                commands = re.findall(r"bin/specromancy\s+([a-z-]+)", text)
                self.assertTrue(commands)
                self.assertTrue(set(commands).issubset(RESERVED_COMMANDS))
                for relative in re.findall(
                    r"specromancy/templates/[a-z0-9-]+\.md", text
                ):
                    self.assertTrue((ROOT / relative).is_file(), relative)

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
        for path in self.paths:
            text = path.read_text(encoding="utf-8").lower()
            with self.subTest(skill=path.parent.name):
                for value in forbidden:
                    self.assertNotIn(value, text)

    def test_skills_never_direct_agents_to_edit_runtime_state(self) -> None:
        for path in self.paths:
            for line in path.read_text(encoding="utf-8").splitlines():
                lowered = line.lower()
                if "edit" in lowered and (
                    "run.json" in lowered or "events.jsonl" in lowered
                ):
                    with self.subTest(skill=path.parent.name, line=line):
                        self.assertTrue("never" in lowered or "do not" in lowered)
        orchestrator = (SKILLS / "pipeline" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("never edit `run.json`", orchestrator)


if __name__ == "__main__":
    unittest.main()
