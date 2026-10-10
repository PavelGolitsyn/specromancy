from __future__ import annotations

import ast
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from specromancy.config import load_pipeline
from tests.engine.contract.source_scan import runtime_sources


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_FIXTURE = ROOT / "tests" / "engine" / "fixtures" / "example-pipeline"
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
        module_paths = (
            "_config.config_models", "_config.config_errors", "_config.config_serialization",
            "schema_validation", "_config.config_fields", "_config.config_phase_parser",
            "_config.config_loader", "validation",
            "_runs.run_records", "_runs.run_validation", "_runs.run_identity", "_runs.run_errors",
            "_runs.run_persistence", "_runs.visit_transitions", "_runs.visit_preparation",
            "_engine.engine_errors", "_engine.provenance", "_engine.validation_service", "_engine.responses",
            "_engine.approvals", "_engine.command_decisions", "_engine.approval_service",
            "_cli.cli_commands", "_adapters.adapter_contracts", "_adapters.adapter_sources",
            "_adapters.adapter_rendering", "_adapters.adapter_ownership",
        )
        qualified = {path.rsplit(".", 1)[-1]: path for path in module_paths}
        for module_path in module_paths:
            module = module_path.rsplit(".", 1)[-1]
            forbidden = ["config", "cli", "engine", "registry"]
            if module != "config_loader":
                forbidden.append("config_loader")
            if module not in {"validation", "validation_service", "approval_service"}:
                forbidden.append("validation")
            if module in {"config_fields", "config_phase_parser"}:
                forbidden.extend(("run_store", "run_persistence", "graph", "config_serialization"))
            if module == "config_fields":
                forbidden.extend(("config_phase_parser", "config_models", "schema_validation"))
            if module in {"engine_errors", "provenance", "validation_service", "responses", "approvals"}:
                forbidden.append("run_store")
            if module in {"approvals", "command_decisions"}:
                forbidden.extend(("run_store", "run_persistence", "run_identity",
                                  "approval_service", "validation_service",
                                  "responses", "provenance", "commands"))
            if module.startswith("run_") or module == "visit_transitions":
                forbidden.extend(("run_store", "actions", "status", "artifacts"))
            if module == "visit_preparation":
                forbidden.extend(("run_store", "run_persistence", "locking",
                                  "run_identity", "visit_transitions", "responses",
                                  "actions", "status"))
            if module.startswith("adapter_") or module == "cli_commands":
                forbidden.extend(("adapters", "run_store"))
            if module in {"adapter_rendering", "adapter_ownership"}:
                forbidden.append("adapter_sources")
            with self.subTest(module=module):
                result = subprocess.run(
                    [sys.executable, "-c", script, str(ROOT / "specromancy"), module_path,
                     *(f"specromancy.{qualified.get(name, name)}" for name in forbidden)],
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
            *sorted((ROOT / "docs" / "reference").glob("*.md")),
            *sorted((ROOT / "docs" / "guides").glob("*.md")),
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
            (ROOT / "tests" / "engine" / "fixtures").glob("**/*.toml")
        )
        for path in paths:
            if path.name == "pipelines.toml":
                continue
            with self.subTest(path=path.relative_to(ROOT)):
                pipeline = load_pipeline(path, path.parents[2] if path.parent.name == "pipelines" else path.parent)
                self.assertTrue(pipeline.phase_ids)


if __name__ == "__main__":
    unittest.main()
