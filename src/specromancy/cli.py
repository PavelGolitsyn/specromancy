"""Command-line entry point and stable result rendering."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Sequence, TextIO

from . import __version__
from .adapters import (
    ADAPTER_NAMES,
    check as check_harness_adapters,
    clean as clean_harness_adapters,
    generate as generate_harness_adapters,
    list_adapters,
)
from .contracts import ContractVersions, validate_contracts
from .errors import ExitCode, InvalidInputError, SpecromancyError, normalize_exception
from .locking import inspect_run_lock
from .orchestrator import (
    cancel_run,
    exhaust_review_cycles,
    fail_phase,
    next_action,
    recover_lock,
    resume_run,
    status_run,
    verify_artifacts,
)
from .paths import RepositoryPaths, discover_repository
from .run import initialize_run, validate_manifest
from .phases.plan import (
    approve_plan,
    complete_plan,
    plan_artifact_path,
    revoke_plan_approval,
    start_plan,
    validate_plan_file,
)
from .phases.implement import (
    abort_implementation,
    complete_implementation,
    execute_verification,
    implementation_artifact_path,
    start_implementation,
    start_repair,
    validate_implementation_file,
)
from .phases.research import (
    complete_research,
    research_artifact_path,
    start_research,
    validate_research_file,
)
from .phases.review import (
    complete_review,
    review_artifact_path,
    start_review,
    validate_review_file,
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
    "verify",
    "lock",
    "resume",
    "cancel",
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
    init = subparsers.add_parser(
        "init",
        parents=[common],
        add_help=False,
        help="initialize a durable run",
        description="Initialize a durable run from a request artifact.",
    )
    init.add_argument("--title", metavar="TEXT")
    init.add_argument("--request", metavar="FILE")
    init.add_argument("--id", dest="run_id", metavar="RUN_ID")

    for command, help_text in (
        ("status", "inspect durable run status"),
        ("next", "report the next permitted action"),
    ):
        command_parser = subparsers.add_parser(
            command,
            parents=[common],
            add_help=False,
            help=help_text,
        )
        command_parser.add_argument("run_id", metavar="RUN_ID")

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
            "phase_name",
            choices=("research", "plan", "implementation", "review"),
            metavar="PHASE",
        )
    fail_parser = phase_actions.add_parser("fail", parents=[common], add_help=False)
    fail_parser.add_argument("run_id", metavar="RUN_ID")
    fail_parser.add_argument(
        "phase_name",
        choices=("research", "plan", "implementation", "review"),
        metavar="PHASE",
    )
    fail_parser.add_argument("--reason", required=True, metavar="TEXT")
    repair_parser = phase_actions.add_parser("repair", parents=[common], add_help=False)
    repair_parser.add_argument("run_id", metavar="RUN_ID")
    repair_parser.add_argument("phase_name", choices=("implementation",), metavar="PHASE")
    abort_parser = phase_actions.add_parser("abort", parents=[common], add_help=False)
    abort_parser.add_argument("run_id", metavar="RUN_ID")
    abort_parser.add_argument("phase_name", choices=("implementation",), metavar="PHASE")
    abort_parser.add_argument("--reason", required=True, metavar="TEXT")

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
        "artifact_name",
        choices=("request", "research", "plan", "implementation", "review"),
        metavar="ARTIFACT",
    )
    artifact_verify_parser = artifact_actions.add_parser(
        "verify", parents=[common], add_help=False
    )
    artifact_verify_parser.add_argument("run_id", metavar="RUN_ID")
    artifact_verify_parser.add_argument(
        "artifact_name",
        nargs="?",
        choices=("request", "research", "plan", "implementation", "review"),
        metavar="ARTIFACT",
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
    validate.add_argument(
        "phase_name",
        nargs="?",
        choices=("research", "plan", "implementation", "review"),
        metavar="PHASE",
    )

    verify = subparsers.add_parser(
        "verify",
        parents=[common],
        add_help=False,
        help="run and record one implementation verification command",
    )
    verify.add_argument("run_id", metavar="RUN_ID")
    verify.add_argument("--cwd", default=".", metavar="PATH")
    verify.add_argument("--nonblocking", action="store_true")
    verify.add_argument("--reason", dest="failure_reason", metavar="TEXT")
    verify.add_argument("argv", nargs="+", metavar="COMMAND")

    lock = subparsers.add_parser("lock", add_help=False, help="inspect run-lock ownership")
    lock_actions = lock.add_subparsers(dest="lock_action", metavar="ACTION", required=True)
    lock_inspect = lock_actions.add_parser("inspect", parents=[common], add_help=False)
    lock_inspect.add_argument("run_id", metavar="RUN_ID")
    lock_recover = lock_actions.add_parser("recover", parents=[common], add_help=False)
    lock_recover.add_argument("run_id", metavar="RUN_ID")

    resume = subparsers.add_parser(
        "resume", parents=[common], add_help=False, help="validate and resume a run"
    )
    resume.add_argument("run_id", metavar="RUN_ID")
    cancel = subparsers.add_parser(
        "cancel", parents=[common], add_help=False, help="cancel a nonterminal run"
    )
    cancel.add_argument("run_id", metavar="RUN_ID")
    cancel.add_argument("--reason", required=True, metavar="TEXT")
    adapters = subparsers.add_parser(
        "adapters",
        add_help=False,
        help="generate and verify harness discovery adapters",
        description="Generate, check, clean, or list deterministic harness adapters.",
    )
    adapter_actions = adapters.add_subparsers(
        dest="adapter_action", metavar="ACTION", required=True
    )
    for action in ("generate", "check", "clean"):
        action_parser = adapter_actions.add_parser(
            action, parents=[common], add_help=False
        )
        action_parser.add_argument("--harness", choices=ADAPTER_NAMES, metavar="NAME")
        if action == "generate":
            action_parser.add_argument(
                "--force",
                action="store_true",
                help="back up and replace colliding user-authored files",
            )
    adapter_actions.add_parser("list", parents=[common], add_help=False)
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

    if args.command == "adapters":
        if args.adapter_action == "list":
            rows = list_adapters()
            labels = [
                f"{row['name']} v{row['version']} ({'native' if row['native'] else 'generated'})"
                for row in rows
            ]
            return Result.success(
                "adapters", "Harness adapters:\n- " + "\n- ".join(labels), {"adapters": rows}
            )
        root = discover_repository(args.repo)
        harness = getattr(args, "harness", None)
        if args.adapter_action == "generate":
            data = generate_harness_adapters(
                root, harness=harness, force=getattr(args, "force", False)
            )
            return Result.success(
                "adapters",
                f"Generated {len(data['generated'])} harness adapter files.",
                data,
            )
        if args.adapter_action == "check":
            data = check_harness_adapters(root, harness=harness)
            return Result.success(
                "adapters",
                f"Checked {len(data['checked'])} harness adapter files; all are current.",
                data,
            )
        data = clean_harness_adapters(root, harness=harness)
        return Result.success(
            "adapters", f"Removed {len(data['removed'])} generated adapter files.", data
        )

    root = discover_repository(args.repo)
    paths = RepositoryPaths(root)
    if args.command != "adapters":
        if args.command == "init":
            result = initialize_run(
                root,
                title=getattr(args, "title", None),
                request_path=getattr(args, "request", None),
                run_id=getattr(args, "run_id", None),
            )
            return Result.success(
                "init",
                (
                    f"Initialized run {result.run_id}.\n"
                    f"Request: {result.request_path}\n"
                    f"Next: {result.next_command}"
                ),
                {
                    "run_id": result.run_id,
                    "title": result.title,
                    "status": result.status,
                    "run_path": result.run_path,
                    "request_path": result.request_path,
                    "manifest_path": result.manifest_path,
                    "next_command": result.next_command,
                },
            )
        if args.command == "status":
            data = status_run(root, args.run_id)
            message = f"Run {args.run_id}: {data['status']}"
            if data["next_action"]:
                command = str(data["next_action"]).replace("RUN_ID", args.run_id)
                message += f"\nNext: specromancy {command}"
            return Result.success("status", message, data)
        if args.command == "next":
            data = status_run(root, args.run_id)
            action = next_action(data)
            command = action.action.replace("RUN_ID", args.run_id) if action.action else None
            message = action.description
            if command:
                message += f"\nNext: specromancy {command}"
            if action.gate:
                message += f"\nGate: {action.gate}"
            return Result.success(
                "next",
                message,
                {
                    "run_id": args.run_id,
                    "status": data["status"],
                    "action": command,
                    "required_gate": action.gate,
                    "terminal": data["terminal"],
                },
            )
        if args.command == "resume":
            data = resume_run(root, args.run_id)
            return Result.success("resume", data["continuation_brief"], data)
        if args.command == "cancel":
            manifest = cancel_run(root, args.run_id, reason=args.reason)
            return Result.success(
                "cancel",
                f"Run {args.run_id} cancelled.",
                {"run_id": args.run_id, "status": manifest["status"], "reason": args.reason},
            )
        if args.command == "lock":
            if args.lock_action == "recover":
                data = recover_lock(root, args.run_id)
                return Result.success(
                    "lock", f"Recovered stale lock for run {args.run_id}.", data
                )
            info = inspect_run_lock(root, args.run_id)
            if info is None:
                return Result.success(
                    "lock", f"Run {args.run_id} is not locked.", {"run_id": args.run_id, "locked": False}
                )
            return Result.success(
                "lock",
                f"Run {args.run_id} is locked by PID {info.pid} on {info.hostname}.",
                {"run_id": info.run_id, "locked": True, "owner_id": info.owner_id, "pid": info.pid,
                 "hostname": info.hostname, "created_at": info.created_at, "command": info.command},
            )
        if args.command == "verify":
            argv = list(args.argv)
            if argv and argv[0] == "--":
                argv.pop(0)
            result = execute_verification(
                root,
                args.run_id,
                argv,
                cwd=args.cwd,
                blocking=not args.nonblocking,
                failure_reason=getattr(args, "failure_reason", None),
            )
            return Result.success(
                "verify",
                f"Verification {result.command_id} exited with code {result.exit_code}.",
                {
                    "run_id": args.run_id,
                    "command_id": result.command_id,
                    "exit_code": result.exit_code,
                    "blocking": result.blocking,
                    "record_path": result.record_path,
                    "stdout_path": result.stdout_path,
                    "stderr_path": result.stderr_path,
                },
            )
        if args.command == "artifact":
            if args.artifact_action == "verify":
                verified = verify_artifacts(root, args.run_id, args.artifact_name)
                label = args.artifact_name or "all recorded artifacts"
                return Result.success(
                    "artifact",
                    f"Verified {label} for run {args.run_id}.",
                    {"run_id": args.run_id, "verified": verified},
                )
            validate_manifest(paths, args.run_id, validate_artifacts=False)
            if args.artifact_name == "request":
                target = paths.run_artifact(args.run_id, "request.md")
            elif args.artifact_name == "research":
                target = research_artifact_path(root, args.run_id)
            elif args.artifact_name == "plan":
                target = plan_artifact_path(root, args.run_id)
            elif args.artifact_name == "implementation":
                target = implementation_artifact_path(root, args.run_id)
            else:
                target = review_artifact_path(root, args.run_id)
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
            if args.phase_name is None:
                manifest = validate_manifest(
                    paths, args.run_id, validate_artifacts=True, validate_events=True
                )
                return Result.success(
                    "validate",
                    f"Run {args.run_id} manifest and recorded artifacts are valid.",
                    {"run_id": args.run_id, "status": manifest["status"], "phase": None},
                )
            if args.phase_name == "research":
                artifact = validate_research_file(root, args.run_id)
                target = research_artifact_path(root, args.run_id)
                warnings = list(artifact.warnings)
            elif args.phase_name == "plan":
                validate_plan_file(root, args.run_id)
                target = plan_artifact_path(root, args.run_id)
                warnings = []
            elif args.phase_name == "implementation":
                validate_implementation_file(root, args.run_id)
                target = implementation_artifact_path(root, args.run_id)
                warnings = []
            else:
                validate_review_file(root, args.run_id)
                target = review_artifact_path(root, args.run_id)
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
        if args.phase_action == "fail":
            manifest = fail_phase(
                root, args.run_id, args.phase_name, reason=args.reason
            )
            return Result.success(
                "phase",
                f"Run {args.run_id} blocked from phase {args.phase_name}.",
                {"run_id": args.run_id, "phase": args.phase_name, "status": manifest["status"]},
            )
        if args.phase_action == "repair":
            current = status_run(root, args.run_id)
            if current["review_cycle"] >= current["max_review_cycles"]:
                manifest = exhaust_review_cycles(root, args.run_id)
                return Result.success(
                    "phase",
                    f"Run {args.run_id} blocked because review repair cycles are exhausted.",
                    {"run_id": args.run_id, "phase": "implementation", "status": manifest["status"]},
                )
            result = start_repair(root, args.run_id)
            return Result.success(
                "phase", f"Implementation repair started for run {args.run_id}.",
                {"run_id": result.run_id, "phase": "implementation", "status": result.status,
                 "artifact_path": result.artifact_path},
            )
        if args.phase_action == "abort":
            result = abort_implementation(root, args.run_id, reason=args.reason)
            return Result.success(
                "phase", f"Implementation aborted for run {args.run_id}.",
                {"run_id": result.run_id, "phase": "implementation", "status": result.status,
                 "artifact_path": result.artifact_path},
            )
        if args.phase_action == "start":
            if args.phase_name == "research":
                result = start_research(root, args.run_id)
            elif args.phase_name == "plan":
                result = start_plan(root, args.run_id)
            elif args.phase_name == "implementation":
                result = start_implementation(root, args.run_id)
            else:
                result = start_review(root, args.run_id)
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
        if args.phase_name == "research":
            result = complete_research(root, args.run_id)
        elif args.phase_name == "plan":
            result = complete_plan(root, args.run_id)
        elif args.phase_name == "implementation":
            result = complete_implementation(root, args.run_id)
        else:
            result = complete_review(root, args.run_id)
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

    raise InvalidInputError(f"Command '{args.command}' is not implemented.")


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
