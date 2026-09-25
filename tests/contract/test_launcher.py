from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


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
        result = subprocess.run(
            [sys.executable, str(ROOT / "adapters" / "generate.py")],
            cwd=ROOT / "docs" / "poc-v3",
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 8, result.stderr)
        self.assertIn("adapters generate", result.stdout)


if __name__ == "__main__":
    unittest.main()
