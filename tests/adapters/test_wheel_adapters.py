import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).parents[2]

try:
    importlib.metadata.version("build")
except importlib.metadata.PackageNotFoundError:
    BUILD_AVAILABLE = False
else:
    BUILD_AVAILABLE = True


@unittest.skipUnless(BUILD_AVAILABLE, "development dependency 'build' is unavailable")
class WheelAdapterTests(unittest.TestCase):
    def test_built_wheel_generates_and_checks_adapters_outside_source_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            output = base / "dist"
            repository = base / "fixture"
            repository.mkdir()
            subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
            (repository / "AGENTS.md").write_text("# Fixture instructions\n", encoding="utf-8")
            for name in ("pipeline", "research", "plan", "implement", "review"):
                skill = repository / ".agents" / "skills" / name
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(
                    f"---\nname: {name}\ndescription: Fixture {name}.\n---\n\n# {name}\n",
                    encoding="utf-8",
                )
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "build",
                    "--wheel",
                    "--no-isolation",
                    "--outdir",
                    str(output),
                    str(ROOT),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            wheel = next(output.glob("specromancy-*.whl"))
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(wheel)
            for action in ("generate", "check"):
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "specromancy",
                        "adapters",
                        action,
                        "--repo",
                        str(repository),
                        "--format",
                        "json",
                    ],
                    cwd=base,
                    env=environment,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertTrue(json.loads(completed.stdout)["ok"])
            self.assertTrue((repository / "CLAUDE.md").is_file())
            self.assertTrue((repository / ".opencode" / "commands" / "review.md").is_file())


if __name__ == "__main__":
    unittest.main()
