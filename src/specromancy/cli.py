"""Command-line entry point and stable result rendering."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Sequence, TextIO

from . import __version__
from .contracts import ContractVersions, validate_contracts
from .errors import ExitCode, InvalidInputError, SpecromancyError, normalize_exception


PLACEHOLDER_COMMANDS = (
    "init",
    "status",
    "next",
    "phase",
    "artifact",
    "approve",
    "validate",
    "resume",
    "adapters",
)


@dataclass(frozen=True)
class Result:
    ok: bool
    command: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def success(
        cls, command: str, message: str, data: dict[str, Any] | None = None
    ) -> "Result":
        return cls(True, command, message, data or {}, [])

    @classmethod
    def failure(cls, command: str, error: SpecromancyError) -> "Result":
        return cls(False, command, error.message, {}, [error.as_dict()])

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "command": self.command,
            "message": self.message,
            "data": self.data,
            "errors": self.errors,
        }


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InvalidInputError(message, hint="Run specromancy --help for usage.")


def _common_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False, argument_default=argparse.SUPPRESS)
    common.add_argument(
        "-h",
        "--help",
        action="store_true",
        help="show this help message and exit",
    )
    common.add_argument(
        "--format",
        choices=("text", "json"),
        help="output format (default: text)",
    )
    common.add_argument(
        "--repo",
        metavar="PATH",
        help="repository path (default: discover from the current directory)",
    )
    return common


def build_parser() -> Parser:
    common = _common_parser()
    parser = Parser(
        prog="specromancy",
        description="Coordinate artifact-driven, spec-driven development runs.",
        parents=[common],
        add_help=False,
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="show package and contract versions",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    for command in PLACEHOLDER_COMMANDS:
        subparsers.add_parser(
            command,
            parents=[common],
            add_help=False,
            help=f"{command} workflow operations (available in a later stage)",
            description=f"The {command} command is reserved by the public CLI.",
        )
    parser.set_defaults(format="text", repo=None, version=False, help=False)
    return parser


def _requested_format(argv: Sequence[str]) -> str:
    for index, value in enumerate(argv):
        if value == "--format" and index + 1 < len(argv):
            return argv[index + 1]
        if value.startswith("--format="):
            return value.partition("=")[2]
    return "text"


def _command_name(argv: Sequence[str]) -> str:
    for value in argv:
        if value in PLACEHOLDER_COMMANDS:
            return value
    return "root"


def _render(result: Result, output_format: str, stream: TextIO) -> None:
    if output_format == "json":
        json.dump(result.as_dict(), stream, ensure_ascii=False, sort_keys=True)
        stream.write("\n")
        return
    stream.write(result.message + "\n")
    if result.errors:
        hint = result.errors[0].get("hint")
        if hint:
            stream.write(f"Hint: {hint}\n")


def _version_result(versions: ContractVersions) -> Result:
    return Result.success(
        "version",
        (
            f"specromancy {__version__} "
            f"(pipeline {versions.pipeline}, schema {versions.schema})"
        ),
        {
            "version": __version__,
            "pipeline_version": versions.pipeline,
            "schema_version": versions.schema,
        },
    )


def _run(args: argparse.Namespace, versions: ContractVersions, parser: Parser) -> Result:
    if args.help:
        if args.version:
            raise InvalidInputError("--help cannot be combined with --version.")
        return Result.success("help", parser.format_help().rstrip())
    if args.version:
        if args.command is not None:
            raise InvalidInputError("--version cannot be combined with a subcommand.")
        return _version_result(versions)
    if args.command is None:
        return Result.success("help", parser.format_help().rstrip())

    raise InvalidInputError(
        f"Command '{args.command}' is reserved but not implemented in this stage.",
        hint="Use --help to inspect the current repository-foundation interface.",
        details={"command": args.command},
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    output_format = _requested_format(arguments)
    command = _command_name(arguments)
    parser = build_parser()
    try:
        args = parser.parse_args(arguments)
        output_format = args.format
        command = args.command or ("version" if args.version else "help")
        versions = validate_contracts()
        result = _run(args, versions, parser)
        if result.command == "help" and output_format == "text":
            print(result.message)
        else:
            _render(result, output_format, sys.stdout)
        return int(ExitCode.SUCCESS)
    except SpecromancyError as exc:
        result = Result.failure(command, exc)
        _render(result, output_format if output_format in {"text", "json"} else "text", sys.stdout)
        return int(exc.exit_code)
    except Exception as exc:  # defensive CLI boundary; expected failures use typed errors
        error = normalize_exception(exc)
        result = Result.failure(command, error)
        _render(result, output_format if output_format in {"text", "json"} else "text", sys.stdout)
        return int(error.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
