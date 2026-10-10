from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from specromancy.cli import (
    RESERVED_COMMANDS, adapter_command_metadata, build_parser,
    discover_repository_root, main,
)
from specromancy._cli.cli_commands import COMMANDS
from specromancy.exit_codes import ExitCode


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_FIXTURE = ROOT / "tests" / "engine" / "fixtures" / "example-pipeline"


def fixture_arguments(*arguments: str) -> list[str]:
    return [
        "--root",
        str(WORKFLOW_FIXTURE),
        "--pipeline",
        "engine-example",
        *arguments,
    ]


class RootDiscoveryTests(unittest.TestCase):
    def test_discovers_worktree_marker_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
            nested = root / "one" / "two"
            nested.mkdir(parents=True)
            self.assertEqual(discover_repository_root(nested), root.resolve())

    def test_explicit_fixture_root_does_not_require_git(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(
                discover_repository_root(explicit_root=temporary),
                Path(temporary).resolve(),
            )


class ParserTests(unittest.TestCase):
    def test_metadata_uses_definitions_without_constructing_a_parser(self) -> None:
        self.assertEqual({command.name for command in COMMANDS}, RESERVED_COMMANDS)
        with patch("specromancy.cli.CommandParser", side_effect=AssertionError("parser access")):
            metadata = adapter_command_metadata(["survey", "status"])["commands"]
        names = [item["name"] for item in metadata]
        self.assertEqual(names, sorted(RESERVED_COMMANDS | {"survey"}))
        self.assertEqual(
            next(item["help"] for item in metadata if item["name"] == "status"),
            "show run status",
        )
        self.assertNotIn("survey", {item["name"] for item in adapter_command_metadata()["commands"]})

    def test_builtins_are_reserved_before_dynamic_aliases(self) -> None:
        parser = build_parser(["status", "survey"])
        status = parser.parse_args(["status", "run-1"])
        survey = parser.parse_args(["survey", "run-1"])
        self.assertEqual(status.command, "status")
        self.assertEqual(survey.command, "dynamic-phase")
        self.assertEqual(survey.phase, "survey")
        self.assertIn("status", RESERVED_COMMANDS)

    def test_unknown_command_is_usage_error(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = main(fixture_arguments("unknown"), stdout=stdout, stderr=stderr)
        self.assertEqual(code, ExitCode.USAGE_ERROR)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("invalid choice", stderr.getvalue())

    def test_json_error_has_stable_shape(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = main(
            fixture_arguments("--json", "unknown"), stdout=stdout, stderr=stderr
        )
        self.assertEqual(code, ExitCode.USAGE_ERROR)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["code"], ExitCode.USAGE_ERROR)
        self.assertIsInstance(payload["message"], str)
        self.assertIn("details", payload)

    def test_json_help_is_exactly_one_object(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = main(["--json", "--help"], stdout=stdout, stderr=stderr)
        self.assertEqual(code, ExitCode.SUCCESS)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["code"], ExitCode.SUCCESS)
        self.assertIn("request-approval", payload["message"])
