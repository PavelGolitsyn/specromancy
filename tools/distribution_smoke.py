"""Copied into a runtime-free bundle and executed by a fresh wheel environment."""
from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import sysconfig
import unittest
from importlib.resources import files


def main() -> int:
    bundle = Path(__file__).resolve().parent
    expected = json.loads((bundle / "expected.json").read_text())
    installed = Path(sysconfig.get_path("purelib")).resolve()
    assert installed.is_relative_to(Path(sys.prefix).resolve()), installed
    package = importlib.import_module("specromancy_engine")
    assert Path(package.__file__).resolve().is_relative_to(installed), package.__file__
    assert package.__version__ == expected["version"]
    assert importlib.metadata.version("specromancy-engine") == expected["version"]
    assert importlib.util.find_spec("specromancy") is None, "stale legacy import namespace"
    for relative in expected["runtime"]:
        if relative.endswith(".py"):
            name = relative[:-3].replace("/", ".").removesuffix(".__init__")
            module = importlib.import_module(name)
            assert Path(module.__file__).resolve() == installed / relative, module.__file__
        else:
            resource = files(package).joinpath(relative.split("/", 1)[1])
            assert json.loads(resource.read_text(encoding="utf-8"))["$schema"]
    console = Path(sys.executable).with_name("specromancy")
    help_text = []
    for command in ([sys.executable, "-I", "-m", "specromancy_engine"], [str(console)]):
        result = subprocess.run([*command, "--help"], check=True, capture_output=True, text=True)
        assert "request-approval" in result.stdout
        help_text.append(result.stdout)
    assert help_text[0] == help_text[1]
    print(f"Installed origin: {package.__file__}", flush=True)
    print(f"Verified {len(expected['runtime'])} runtime files and both entry points", flush=True)
    # Only test code/fixtures are exposed. This directory has no engine source,
    # launcher, editable metadata, or producer configuration.
    sys.path.insert(0, str(bundle))
    suite = unittest.defaultTestLoader.loadTestsFromNames(expected["tests"])
    assert suite.countTestCases() > 0
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    sys.exit(main())
