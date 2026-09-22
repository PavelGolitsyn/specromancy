import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest import mock

from specromancy.cli import build_parser, main
from specromancy.errors import ExitCode, ValidationError


SNAPSHOTS = Path(__file__).parents[1] / "snapshots"


def invoke(*arguments: str) -> tuple[int, str]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = main(arguments)
    return code, output.getvalue()


class CliTests(unittest.TestCase):
    def test_help_snapshot(self) -> None:
        expected = (SNAPSHOTS / "cli_help.txt").read_text(encoding="utf-8")
        self.assertEqual(build_parser().format_help(), expected)

    def test_version_text_snapshot(self) -> None:
        expected = (SNAPSHOTS / "cli_version.txt").read_text(encoding="utf-8")
        code, output = invoke("--version")
        self.assertEqual(code, ExitCode.SUCCESS)
        self.assertEqual(output, expected)

    def test_version_json_exposes_package_and_contract_versions(self) -> None:
        code, output = invoke("--version", "--format", "json")
        envelope = json.loads(output)
        self.assertEqual(code, ExitCode.SUCCESS)
        self.assertTrue(envelope["ok"])
        self.assertEqual(envelope["command"], "version")
        self.assertEqual(
            set(envelope["data"]), {"version", "pipeline_version", "schema_version"}
        )

    def test_help_json_uses_result_envelope(self) -> None:
        code, output = invoke("--help", "--format", "json")
        envelope = json.loads(output)
        self.assertEqual(code, ExitCode.SUCCESS)
        self.assertTrue(envelope["ok"])
        self.assertEqual(envelope["command"], "help")
        self.assertIn("usage: specromancy", envelope["message"])

    def test_placeholder_returns_documented_structured_error(self) -> None:
        code, output = invoke("status", "--format", "json")
        envelope = json.loads(output)
        self.assertEqual(code, ExitCode.INVALID_INPUT)
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["command"], "status")
        self.assertEqual(envelope["errors"][0]["code"], "INVALID_INPUT")

    def test_invalid_arguments_are_a_json_envelope_when_requested(self) -> None:
        code, output = invoke("--format", "json", "--unknown")
        envelope = json.loads(output)
        self.assertEqual(code, ExitCode.INVALID_INPUT)
        self.assertFalse(envelope["ok"])
        self.assertEqual(set(envelope), {"ok", "command", "message", "data", "errors"})

    def test_verify_parser_keeps_options_out_of_recorded_argv(self) -> None:
        args = build_parser().parse_args(
            ["verify", "run-1", "--nonblocking", "--reason", "optional", "--", "python3", "-V"]
        )
        self.assertTrue(args.nonblocking)
        self.assertEqual(args.failure_reason, "optional")
        self.assertEqual(args.argv, ["python3", "-V"])

    def test_invalid_packaged_contract_fails_startup_with_exit_four(self) -> None:
        with mock.patch(
            "specromancy.cli.validate_contracts",
            side_effect=ValidationError("Packaged contract is invalid."),
        ):
            code, output = invoke("--version", "--format", "json")
        envelope = json.loads(output)
        self.assertEqual(code, ExitCode.VALIDATION_FAILED)
        self.assertEqual(envelope["errors"][0]["code"], "VALIDATION_FAILED")


if __name__ == "__main__":
    unittest.main()
