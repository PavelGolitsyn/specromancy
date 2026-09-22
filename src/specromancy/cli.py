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
from .paths import RepositoryPaths, discover_repository
from .phases.plan import (
    approve_plan,
    complete_plan,
    plan_artifact_path,
    revoke_plan_approval,
    start_plan,
    validate_plan_file,
)
from .phases.research import (
    complete_research,
    research_artifact_path,
    start_research,
    validate_research_file,
)


PLACEHOLDER_COMMANDS = (
    "init",
    "status",
    "next",
    "resume",
    "adapters",
)
COMMANDS = (
    "init",
    "status",
    "next",
    "phase",
    "artifact",
    "approve",
    "approval",
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
    def add_placeholder(command: str) -> None:
        subparsers.add_parser(
            command,
            parents=[common],
            add_help=False,
            help=f"{command} workflow operations (available in a later stage)",
            description=f"The {command} command is reserved by the public CLI.",
        )

    for command in ("init", "status", "next"):
        add_placeholder(command)

    phase = subparsers.add_parser(
        "phase",
        add_help=False,
        help="start or complete an implemented phase",
        description="Start or complete an implemented phase for an existing run.",
    )
    phase_actions = phase.add_subparsers(dest="phase_action", metavar="ACTION", required=True)
    for action in ("start", "complete"):
        action_parser = phase_actions.add_parser(action, parents=[common], add_help=False)
        action_parser.add_argument("run_id", metavar="RUN_ID")
        action_parser.add_argument(
            "phase_name", choices=("research", "plan"), metavar="PHASE"
        )

    artifact = subparsers.add_parser(
        "artifact",
        add_help=False,
        help="inspect managed artifact paths",
        description="Inspect managed artifact paths for an existing run.",
    )
    artifact_actions = artifact.add_subparsers(
        dest="artifact_action", metavar="ACTION", required=True
    )
    artifact_path_parser = artifact_actions.add_parser(
        "path", parents=[common], add_help=False
    )
    artifact_path_parser.add_argument("run_id", metavar="RUN_ID")
    artifact_path_parser.add_argument(
        "artifact_name", choices=("research", "plan"), metavar="ARTIFACT"
    )

    approve = subparsers.add_parser(
        "approve",
        parents=[common],
        add_help=False,
        help="record explicit approval for a completed plan",
        description="Approve the exact current validated plan digest.",
    )
    approve.add_argument("run_id", metavar="RUN_ID")
    approve.add_argument("artifact_name", choices=("plan",), metavar="ARTIFACT")
    approve.add_argument("--by", required=True, dest="approver", metavar="IDENTITY")
    approve.add_argument("--note", metavar="TEXT")

    approval = subparsers.add_parser(
        "approval",
        add_help=False,
        help="manage recorded plan approvals",
        description="Manage a recorded plan approval.",
    )
    approval_actions = approval.add_subparsers(
        dest="approval_action", metavar="ACTION", required=True
    )
    revoke = approval_actions.add_parser("revoke", parents=[common], add_help=False)
    revoke.add_argument("run_id", metavar="RUN_ID")
    revoke.add_argument("artifact_name", choices=("plan",), metavar="ARTIFACT")
    revoke.add_argument("--by", required=True, dest="revoked_by", metavar="IDENTITY")
    revoke.add_argument("--reason", required=True, metavar="TEXT")

    validate = subparsers.add_parser(
        "validate",
        parents=[common],
        add_help=False,
        help="validate an implemented phase artifact",
        description="Validate an implemented phase artifact for an existing run.",
    )
    validate.add_argument("run_id", metavar="RUN_ID")
    validate.add_argument("phase_name", choices=("research", "plan"), metavar="PHASE")
    for command in ("resume", "adapters"):
        add_placeholder(command)
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
        if value in COMMANDS:
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

    if args.command in {"phase", "artifact", "approve", "approval", "validate"}:
        root = discover_repository(args.repo)
        paths = RepositoryPaths(root)
        if args.command == "artifact":
            target = (
                research_artifact_path(root, args.run_id)
                if args.artifact_name == "research"
                else plan_artifact_path(root, args.run_id)
            )
            relative = paths.serialize(target)
            return Result.success(
                "artifact",
                str(target),
                {
                    "run_id": args.run_id,
                    "artifact": args.artifact_name,
                    "path": relative,
                    "absolute_path": str(target),
                },
            )
        if args.command == "validate":
            if args.phase_name == "research":
                artifact = validate_research_file(root, args.run_id)
                target = research_artifact_path(root, args.run_id)
                warnings = list(artifact.warnings)
            else:
                validate_plan_file(root, args.run_id)
                target = plan_artifact_path(root, args.run_id)
                warnings = []
            phase_label = args.phase_name.title()
            message = f"{phase_label} artifact is valid: {paths.serialize(target)}"
            if warnings:
                message += "\nWarnings:\n- " + "\n- ".join(artifact.warnings)
            return Result.success(
                "validate",
                message,
                {
                    "run_id": args.run_id,
                    "phase": args.phase_name,
                    "path": paths.serialize(target),
                    "warnings": warnings,
                },
            )
        if args.command == "approve":
            result = approve_plan(
                root,
                args.run_id,
                approver=args.approver,
                note=getattr(args, "note", None),
            )
            qualifier = " already" if result.replayed else ""
            return Result.success(
                "approve",
                f"Plan is{qualifier} approved for run {args.run_id} by {result.approver}.",
                {
                    "run_id": result.run_id,
                    "artifact": args.artifact_name,
                    "status": result.status,
                    "approver": result.approver,
                    "approved_at": result.approved_at,
                    "artifact_sha256": result.artifact_sha256,
                    "note": result.note,
                    "replayed": result.replayed,
                },
            )
        if args.command == "approval":
            result = revoke_plan_approval(
                root,
                args.run_id,
                revoked_by=args.revoked_by,
                reason=args.reason,
            )
            return Result.success(
                "approval",
                f"Plan approval revoked for run {args.run_id} by {result.revoked_by}.",
                {
                    "run_id": result.run_id,
                    "artifact": args.artifact_name,
                    "status": result.status,
                    "revoked_by": result.revoked_by,
                    "revoked_at": result.revoked_at,
                    "reason": result.reason,
                },
            )
        if args.phase_action == "start":
            result = (
                start_research(root, args.run_id)
                if args.phase_name == "research"
                else start_plan(root, args.run_id)
            )
            phase_label = args.phase_name.title()
            return Result.success(
                "phase",
                f"{phase_label} started for run {args.run_id}.",
                {
                    "run_id": result.run_id,
                    "phase": args.phase_name,
                    "status": result.status,
                    "artifact_path": result.artifact_path,
                },
            )
        result = (
            complete_research(root, args.run_id)
            if args.phase_name == "research"
            else complete_plan(root, args.run_id)
        )
        qualifier = " already" if result.replayed else ""
        phase_label = args.phase_name.title()
        message = f"{phase_label} is{qualifier} complete for run {args.run_id}."
        warnings = list(getattr(result, "warnings", ()))
        if warnings:
            message += "\nWarnings:\n- " + "\n- ".join(result.warnings)
        return Result.success(
            "phase",
            message,
            {
                "run_id": result.run_id,
                "phase": args.phase_name,
                "status": result.status,
                "artifact_path": result.artifact_path,
                "artifact_sha256": result.artifact_sha256,
                "warnings": warnings,
                "replayed": result.replayed,
            },
        )

    raise InvalidInputError(
        f"Command '{args.command}' is reserved but not implemented in this stage.",
        hint="Use --help to inspect the currently implemented interface.",
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
