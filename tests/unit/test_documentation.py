from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from specromancy.cli import COMMANDS
from specromancy.security import validate_documentation


ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples" / "minimal"


class DocumentationTests(unittest.TestCase):
    def test_links_and_documented_command_names_are_valid(self) -> None:
        documents = validate_documentation(ROOT)
        self.assertIn(ROOT / "docs" / "cli.md", documents)

    def test_cli_reference_covers_every_top_level_command(self) -> None:
        reference = (ROOT / "docs" / "cli.md").read_text(encoding="utf-8")
        for command in COMMANDS:
            with self.subTest(command=command):
                self.assertIn(f"specromancy {command}", reference)

    def test_harness_guides_share_release_and_example_context(self) -> None:
        for guide in sorted((ROOT / "docs" / "harnesses").glob("*.md")):
            if guide.name == "smoke-observations.md":
                continue
            text = guide.read_text(encoding="utf-8")
            with self.subTest(guide=guide.name):
                self.assertIn("Specromancy 0.1.0", text)
                self.assertIn("2026-09-23", text)
                self.assertIn("minimal-greeting", text)
                self.assertIn("Known limitations", text)

    def test_minimal_example_passes_and_repair_fixture_recovers(self) -> None:
        baseline = subprocess.run(
            [sys.executable, "-m", "unittest", "-v"],
            cwd=EXAMPLE,
            capture_output=True,
            text=True,
        )
        self.assertEqual(baseline.returncode, 0, baseline.stdout + baseline.stderr)
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "minimal"
            shutil.copytree(EXAMPLE, fixture)
            subprocess.run(
                ["git", "apply", "fixtures/flawed.patch"], cwd=fixture, check=True
            )
            flawed = subprocess.run(
                [sys.executable, "-m", "unittest", "-v"],
                cwd=fixture,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(flawed.returncode, 0)
            self.assertIn("test_trims_surrounding_whitespace", flawed.stderr)
            subprocess.run(
                ["git", "apply", "fixtures/repair.patch"], cwd=fixture, check=True
            )
            repaired = subprocess.run(
                [sys.executable, "-m", "unittest", "-v"],
                cwd=fixture,
                capture_output=True,
                text=True,
            )
            self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)

    def test_example_contains_no_live_run_output(self) -> None:
        self.assertFalse((EXAMPLE / ".specromancy").exists())
        for expected in ("research.md", "plan.md", "review.md"):
            self.assertTrue((EXAMPLE / "expected" / expected).is_file())


if __name__ == "__main__":
    unittest.main()
