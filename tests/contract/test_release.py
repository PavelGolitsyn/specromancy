from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ReleaseContractTests(unittest.TestCase):
    def test_fresh_source_export_runs_without_installation(self) -> None:
        self.assertGreaterEqual(sys.version_info, (3, 11))
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "specromancy"

            def ignore(_directory: str, names: list[str]) -> set[str]:
                return {
                    name
                    for name in names
                    if name in {".git", ".specromancy", "__pycache__"}
                    or name.endswith((".pyc", ".pyo"))
                }

            shutil.copytree(ROOT, checkout, ignore=ignore)
            subprocess.run(
                ["git", "-C", str(checkout), "init", "--quiet"],
                check=True,
                capture_output=True,
            )
            help_result = subprocess.run(
                [str(checkout / "bin" / "specromancy"), "--help"],
                cwd=checkout / "docs",
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            initialized = subprocess.run(
                [
                    str(checkout / "bin" / "specromancy"),
                    "--json",
                    "init",
                    "Fresh source test",
                ],
                cwd=checkout,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(initialized.returncode, 8, initialized.stderr)
            self.assertEqual(json.loads(initialized.stdout)["action"]["phase"], "research")

    def test_runtime_package_imports_only_standard_library_modules(self) -> None:
        imported: set[str] = set()
        for path in sorted((ROOT / "specromancy").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imported.add(node.module.split(".", 1)[0])
        non_standard = imported - sys.stdlib_module_names - {"specromancy"}
        self.assertEqual(non_standard, set())

    def test_runtime_data_is_ignored_and_license_metadata_is_consistent(self) -> None:
        ignored = subprocess.run(
            ["git", "check-ignore", ".specromancy/runs/example/run.json"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(ignored.returncode, 0)
        self.assertTrue((ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License"))
        for path in sorted((ROOT / ".agents" / "skills").glob("*/SKILL.md")):
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIn("\nlicense: MIT\n", path.read_text(encoding="utf-8"))
        for path in sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md")):
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIn("\nlicense: MIT\n", path.read_text(encoding="utf-8"))

    def test_generated_files_have_no_timestamp_or_absolute_path(self) -> None:
        manifest_path = ROOT / "adapters" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertNotIn("timestamp", manifest_path.read_text(encoding="utf-8").lower())
        absolute = re.compile(r"(?:^|[\s'\"`(])/(?:Users|home|private|tmp)/")
        timestamp = re.compile(r"\b20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}")
        for entry in manifest["generated"]:
            text = (ROOT / entry["path"]).read_text(encoding="utf-8")
            with self.subTest(path=entry["path"]):
                self.assertIsNone(absolute.search(text))
                self.assertIsNone(timestamp.search(text))

    def test_release_documents_cover_supported_contract_and_limitations(self) -> None:
        required = {
            "architecture.md": ("Responsibility split", "POC limitations"),
            "cli.md": ("Workflow commands", "exit codes"),
            "authoring-pipelines.md": ("bounded loops", "active runs"),
            "harnesses.md": ("Codex", "Claude Code", "GitHub Copilot", "OpenCode", "Hermes"),
        }
        for name, concepts in required.items():
            text = (ROOT / "docs" / "poc-v3" / name).read_text(encoding="utf-8")
            with self.subTest(path=name):
                for concept in concepts:
                    self.assertIn(concept.lower(), text.lower())


if __name__ == "__main__":
    unittest.main()
