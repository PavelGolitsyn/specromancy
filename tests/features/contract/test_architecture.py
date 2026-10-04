from __future__ import annotations

import ast
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from specromancy.config import load_pipeline
from tests.features.contract.source_scan import runtime_sources


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_FIXTURE = ROOT / "tests" / "features" / "fixtures" / "example-pipeline"
# Rendering harness commands may use vendor vocabulary. This exact-file
# exclusion does not exempt future extracted modules or any subprocess/import
# checks. Adapter policy separation is checked by test_adapter_drift.
HARNESS_BOUNDARIES = {Path("adapters.py")}
EXAMPLE_PHASES = ("research", "plan", "implement", "review")


class StaticArchitectureContractTests(unittest.TestCase):
    def test_leaf_modules_import_without_facade_initialization(self) -> None:
        # Bypass the eager package exports so they cannot mask import cycles.
        script = """
import importlib
import sys
import types

package = types.ModuleType('specromancy')
package.__path__ = [sys.argv[1]]
sys.modules['specromancy'] = package
importlib.import_module('specromancy.' + sys.argv[2])
unexpected = set(sys.argv[3:]) & set(sys.modules)
assert not unexpected, unexpected
"""
        for module in (
            "config_models", "config_errors", "config_serialization",
            "schema_validation", "config_loader", "validation",
            "run_records", "run_validation", "run_identity", "run_errors",
        ):
            forbidden = ["config", "cli", "engine", "registry"]
            if module != "config_loader":
                forbidden.append("config_loader")
            if module != "validation":
                forbidden.append("validation")
            if module.startswith("run_"):
                forbidden.extend(("run_store", "actions", "status", "artifacts"))
            with self.subTest(module=module):
                result = subprocess.run(
                    [sys.executable, "-c", script, str(ROOT / "specromancy"), module,
                     *(f"specromancy.{name}" for name in forbidden)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_generic_engine_modules_do_not_name_example_phases(self) -> None:
        pattern = re.compile(
            r"(?:'|\")(?:" + "|".join(EXAMPLE_PHASES) + r")(?:'|\")"
        )
        for path in runtime_sources(ROOT / "specromancy"):
            relative = path.relative_to(ROOT / "specromancy")
            if relative in HARNESS_BOUNDARIES:
                continue
            with self.subTest(path=relative):
                self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")))

    def test_source_discovery_includes_nested_modules_and_package_initializers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = ("__init__.py", "nested/__init__.py", "nested/deeper/decisions.py")
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
            self.assertEqual(
                [path.relative_to(root).as_posix() for path in runtime_sources(root)],
                sorted(names),
            )

    def test_canonical_skill_frontmatter_has_no_vendor_only_fields(self) -> None:
        forbidden = {
            "agent",
            "allowed-tools",
            "argument-hint",
            "disable-model-invocation",
            "model",
            "permission-mode",
            "tools",
        }
        for path in sorted(
            (WORKFLOW_FIXTURE / ".agents" / "skills").glob("*/SKILL.md")
        ):
            lines = path.read_text(encoding="utf-8").splitlines()
            closing = lines.index("---", 1)
            keys = {
                line.split(":", 1)[0].strip().lower()
                for line in lines[1:closing]
                if ":" in line
            }
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertFalse(keys & forbidden)

    def test_instructions_never_direct_agents_to_edit_runtime_state(self) -> None:
        paths = [
            *sorted((WORKFLOW_FIXTURE / ".agents" / "skills").glob("*/SKILL.md")),
            *sorted((ROOT / "docs" / "poc-v3").glob("*.md")),
        ]
        for path in paths:
            for line in path.read_text(encoding="utf-8").splitlines():
                lowered = line.lower()
                if "edit" in lowered and (
                    "run.json" in lowered or "events.jsonl" in lowered
                ):
                    with self.subTest(path=path.relative_to(ROOT), line=line):
                        self.assertTrue(
                            "never" in lowered or "do not" in lowered,
                            "runtime-state editing may only appear as a prohibition",
                        )

    def test_subprocess_calls_cannot_use_shell_strings(self) -> None:
        for path in runtime_sources(ROOT / "specromancy"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if not (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                    and node.func.attr in {"run", "Popen", "call", "check_call", "check_output"}
                ):
                    continue
                with self.subTest(path=path.relative_to(ROOT), line=node.lineno):
                    self.assertTrue(node.args)
                    self.assertFalse(
                        isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                    )
                    shell = next(
                        (keyword.value for keyword in node.keywords if keyword.arg == "shell"),
                        None,
                    )
                    if shell is not None:
                        self.assertIsInstance(shell, ast.Constant)
                        self.assertIs(shell.value, False)

    def test_every_pipeline_fixture_has_only_bounded_cycles(self) -> None:
        paths = sorted(
            (ROOT / "tests" / "features" / "fixtures").glob("**/*.toml")
        )
        for path in paths:
            if path.name == "pipelines.toml":
                continue
            with self.subTest(path=path.relative_to(ROOT)):
                pipeline = load_pipeline(path, path.parents[2] if path.parent.name == "pipelines" else path.parent)
                self.assertTrue(pipeline.phase_ids)


if __name__ == "__main__":
    unittest.main()
