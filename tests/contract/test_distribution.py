import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import venv
import zipfile


ROOT = Path(__file__).parents[2]

try:
    importlib.metadata.version("build")
except importlib.metadata.PackageNotFoundError:
    BUILD_AVAILABLE = False
else:
    BUILD_AVAILABLE = True


@unittest.skipUnless(BUILD_AVAILABLE, "development dependency 'build' is unavailable")
class DistributionTests(unittest.TestCase):
    def _build(self, directory: Path) -> tuple[Path, Path]:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--no-isolation",
                "--outdir",
                str(directory),
                str(ROOT),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return next(directory.glob("*.tar.gz")), next(directory.glob("*.whl"))

    def test_sdist_and_wheel_contain_intended_release_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sdist, wheel = self._build(Path(directory))
            with tarfile.open(sdist, "r:gz") as archive:
                sdist_names = {name.partition("/")[2] for name in archive.getnames()}
            for path in (
                "CHANGELOG.md",
                "docs/getting-started.md",
                "docs/release-checklist.md",
                "examples/minimal/greeting.py",
                "examples/minimal/fixtures/flawed.patch",
                ".agents/skills/implement/SKILL.md",
                "tests/unit/test_documentation.py",
            ):
                self.assertIn(path, sdist_names)
            with zipfile.ZipFile(wheel) as archive:
                wheel_names = set(archive.namelist())
            for path in (
                "specromancy/compatibility.py",
                "specromancy/resources/contracts/pipeline.json",
                "specromancy/templates/implementation.md",
            ):
                self.assertIn(path, wheel_names)
            self.assertFalse(any(name.startswith("docs/") for name in wheel_names))
            self.assertFalse(any(name.startswith("examples/") for name in wheel_names))
            for names in (sdist_names, wheel_names):
                self.assertFalse(any(".specromancy/runs" in name for name in names))
                self.assertFalse(any("__pycache__" in name for name in names))
                self.assertFalse(any(name.endswith((".pyc", ".tmp")) for name in names))
                self.assertFalse(any("adapters/backups" in name for name in names))
                secret_names = {".env", "id_rsa", "id_ed25519", "credentials.json"}
                self.assertFalse(
                    any(
                        Path(name).name in secret_names
                        or Path(name).suffix.lower() in {".key", ".pem", ".p12"}
                        for name in names
                    )
                )

    def test_installed_wheel_runs_outside_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            _sdist, wheel = self._build(base / "dist")
            environment = base / "venv"
            venv.EnvBuilder(with_pip=True).create(environment)
            bindir = "Scripts" if os.name == "nt" else "bin"
            python = environment / bindir / ("python.exe" if os.name == "nt" else "python")
            command = environment / bindir / ("specromancy.exe" if os.name == "nt" else "specromancy")
            installed_environment = os.environ.copy()
            installed_environment.pop("PYTHONPATH", None)
            subprocess.run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--force-reinstall",
                    "--no-index",
                    "--no-deps",
                    str(wheel),
                ],
                check=True,
                capture_output=True,
                text=True,
                env=installed_environment,
            )
            repository = base / "fixture"
            repository.mkdir()
            subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
            shutil.copy2(ROOT / "AGENTS.md", repository / "AGENTS.md")
            shutil.copytree(ROOT / ".agents", repository / ".agents")
            version = subprocess.run(
                [str(command), "--version", "--format", "json"],
                cwd=base,
                check=True,
                capture_output=True,
                text=True,
                env=installed_environment,
            )
            self.assertEqual(json.loads(version.stdout)["data"]["version"], "0.1.0")
            for action in ("generate", "check"):
                subprocess.run(
                    [str(command), "adapters", action, "--repo", str(repository)],
                    cwd=base,
                    check=True,
                    capture_output=True,
                    text=True,
                    env=installed_environment,
                )
            doctor = subprocess.run(
                [str(command), "doctor", "--repo", str(repository), "--format", "json"],
                cwd=base,
                check=True,
                capture_output=True,
                text=True,
                env=installed_environment,
            )
            self.assertTrue(json.loads(doctor.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
