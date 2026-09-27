from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_FIXTURE = ROOT / "tests" / "features" / "fixtures" / "example-pipeline"


class LauncherContractTests(unittest.TestCase):
    def test_launcher_imports_local_package_from_nested_directory(self) -> None:
        result = subprocess.run(
            [str(ROOT / "bin" / "specromancy"), "--help"],
            cwd=ROOT / "docs" / "poc-v3",
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("request-approval", result.stdout)
        self.assertIn("12  Internal or corrupt-state error", result.stdout)

    def test_module_entry_point_uses_the_same_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "specromancy", "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("adapters", result.stdout)

    def test_adapter_entry_point_imports_local_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            shutil.copytree(WORKFLOW_FIXTURE, fixture, dirs_exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "adapters" / "generate.py"),
                    "--root",
                    str(fixture),
                    "--pipeline",
                    str(fixture / "pipeline.toml"),
                ],
                cwd=ROOT / "docs" / "poc-v3",
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("generated", result.stdout)


if __name__ == "__main__":
    unittest.main()
