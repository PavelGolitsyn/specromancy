from __future__ import annotations

import ast
import json
import re
import unittest
from pathlib import Path

from specromancy.config import load_pipeline


ROOT = Path(__file__).resolve().parents[2]
GENERIC_MODULES = (
    "actions.py",
    "approvals.py",
    "artifacts.py",
    "commands.py",
    "config.py",
    "engine.py",
    "git.py",
    "graph.py",
    "hashing.py",
    "locking.py",
    "run_store.py",
    "status.py",
    "validation.py",
)
EXAMPLE_PHASES = ("research", "plan", "implement", "review")


class StaticArchitectureContractTests(unittest.TestCase):
    def test_generic_engine_modules_do_not_name_example_phases(self) -> None:
        pattern = re.compile(
            r"(?:'|\")(?:" + "|".join(EXAMPLE_PHASES) + r")(?:'|\")"
        )
        for name in GENERIC_MODULES:
            path = ROOT / "specromancy" / name
            with self.subTest(path=name):
                self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")))

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
        for path in sorted((ROOT / ".agents" / "skills").glob("*/SKILL.md")):
            lines = path.read_text(encoding="utf-8").splitlines()
            closing = lines.index("---", 1)
            keys = {
                line.split(":", 1)[0].strip().lower()
                for line in lines[1:closing]
                if ":" in line
            }
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertFalse(keys & forbidden)

    def test_generated_adapters_have_no_unique_rules_or_machine_paths(self) -> None:
        manifest = json.loads(
            (ROOT / "adapters" / "manifest.json").read_text(encoding="utf-8")
        )
        workflow_markers = (
            "[[phases.transitions]]",
            "approval_conditions =",
            "max_traversals =",
            "stop_conditions =",
            "terminal_outcomes =",
            "validator =",
        )
        machine_path = re.compile(r"(?:^|[\s'\"`(])/(?:Users|home|private|tmp)/")
        for entry in manifest["generated"]:
            path = ROOT / entry["path"]
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=entry["path"]):
                self.assertFalse(any(marker in text for marker in workflow_markers))
                self.assertIsNone(machine_path.search(text))
        self.assertIsNone(
            machine_path.search(
                (ROOT / "adapters" / "manifest.json").read_text(encoding="utf-8")
            )
        )

    def test_instructions_never_direct_agents_to_edit_runtime_state(self) -> None:
        paths = [
            *sorted((ROOT / ".agents" / "skills").glob("*/SKILL.md")),
            *sorted((ROOT / ".claude").rglob("*.md")),
            *sorted((ROOT / ".github").rglob("*.md")),
            *sorted((ROOT / ".opencode").rglob("*.md")),
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
        for path in sorted((ROOT / "specromancy").glob("*.py")):
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
                with self.subTest(path=path.name, line=node.lineno):
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

    def test_every_shipped_pipeline_has_only_bounded_cycles(self) -> None:
        paths = [
            ROOT / "specromancy" / "pipeline.toml",
            *sorted((ROOT / "tests" / "fixtures").glob("**/pipeline.toml")),
        ]
        for path in paths:
            with self.subTest(path=path.relative_to(ROOT)):
                repository_root = (
                    path.parent if path.parent.name == "replacement-pipeline" else None
                )
                pipeline = load_pipeline(path, repository_root)
                self.assertTrue(pipeline.phase_ids)


if __name__ == "__main__":
    unittest.main()
