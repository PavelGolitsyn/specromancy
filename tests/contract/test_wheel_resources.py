import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).parents[2]


class WheelResourceTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("build"), "development dependency 'build' is unavailable")
    def test_built_wheel_contains_and_loads_contract_resources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "dist")
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
            with zipfile.ZipFile(wheel) as archive:
                names = set(archive.namelist())
            for name in (
                "artifact.schema.json",
                "exit-codes.json",
                "pipeline.json",
                "run.schema.json",
            ):
                self.assertIn(f"specromancy/resources/contracts/{name}", names)

            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(wheel)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import json; from specromancy.contracts import validate_contracts; "
                        "v=validate_contracts(); print(json.dumps([v.pipeline,v.schema]))"
                    ),
                ],
                cwd=directory,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(completed.stdout), ["1", "1"])


if __name__ == "__main__":
    unittest.main()

