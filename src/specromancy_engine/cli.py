"""Dependency-free command-line boundary for Specromancy."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, TextIO

from .contracts import RESERVED_COMMANDS
from .actions import render_action_packet
from ._cli.cli_commands import adapter_command_metadata, command_definitions
from ._config.config_models import PipelineConfig
from .engine import Engine
from .errors import SpecromancyError, UsageError
from .exit_codes import EXIT_CODE_DESCRIPTIONS, ExitCode
from ._cli.pipeline_selection import selected_pipeline as _selected_pipeline
from .registry import load_registry
from .status import render_status

ACTIONABLE_CODES = frozenset(
    {
        ExitCode.APPROVAL_REQUIRED,
        ExitCode.AGENT_ACTION_REQUIRED,
        ExitCode.RUN_BLOCKED,
        ExitCode.RUN_PAUSED,
    }
)


def discover_repository_root(
    start: str | os.PathLike[str] | None = None,
    explicit_root: str | os.PathLike[str] | None = None,
) -> Path:
    """Return an explicit root or walk upward until a Git marker is found.

    A ``.git`` marker may be either a directory or a file, as used by Git
    worktrees. Explicit roots intentionally do not need to be Git repositories,
    which keeps fixture and non-Git use deterministic.
    """

    if explicit_root is not None:
        root = Path(explicit_root).expanduser().resolve()
        if not root.exists():
            raise UsageError(
                f"explicit repository root does not exist: {root}",
                {"root": str(root)},
            )
        if not root.is_dir():
            raise UsageError(
                f"explicit repository root is not a directory: {root}",
                {"root": str(root)},
            )
        return root

    candidate = Path.cwd() if start is None else Path(start)
    candidate = candidate.expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent

    for directory in (candidate, *candidate.parents):
        if (directory / ".git").exists():
            return directory

    raise UsageError(
        "could not find a repository root; pass --root PATH",
        {"start": str(candidate)},
    )


class CommandParser(argparse.ArgumentParser):
    """Argument parser that reports expected failures through our contract."""

    def error(self, message: str) -> None:
        raise UsageError(message, {"usage": self.format_usage().strip()})


def _exit_code_help() -> str:
    lines = ["exit codes:"]
    for code, description in EXIT_CODE_DESCRIPTIONS.items():
        lines.append(f"  {int(code):>2}  {description}")
    return "\n".join(lines)


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    # SUPPRESS prevents a subparser's default from overwriting a value supplied
    # before the command name on the root parser.
    parser.add_argument(
        "--root",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="repository root (required when no .git marker can be discovered)",
    )
    parser.add_argument(
        "--pipeline",
        metavar="ID",
        default=argparse.SUPPRESS,
        help="registered pipeline ID (required for init)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="emit exactly one JSON object",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=argparse.SUPPRESS,
        help="suppress human-readable non-error output",
    )


def _add_command(
    subparsers: Any,
    name: str,
    help_text: str,
    arguments: Iterable[tuple[tuple[str, ...], dict[str, Any]]],
) -> argparse.ArgumentParser:
    command = subparsers.add_parser(name, help=help_text, description=help_text)
    _add_common_options(command)
    for names, options in arguments:
        command.add_argument(*names, **options)
    command.set_defaults(command=name)
    return command


def build_parser(dynamic_phases: Iterable[str] = ()) -> CommandParser:
    """Build the stable parser, optionally adding validated dynamic aliases."""

    parser = CommandParser(
        prog="specromancy",
        description="Run a configured, artifact-based agentic pipeline.",
        epilog=_exit_code_help(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_common_options(parser)
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    for definition in command_definitions(dynamic_phases):
        command = _add_command(
            subparsers, definition.name, definition.description, definition.arguments
        )
        if definition.name not in RESERVED_COMMANDS:
            command.set_defaults(command="dynamic-phase", phase=definition.name)
        elif definition.name == "adapters":
            adapters = command

    adapter_commands = adapters.add_subparsers(
        dest="adapter_command", metavar="COMMAND"
    )
    generate = adapter_commands.add_parser(
        "generate", help="generate harness adapters"
    )
    _add_common_options(generate)
    generate.add_argument(
        "--check",
        action="store_true",
        help="report adapter drift without writing files",
    )
    generate.set_defaults(command="adapters", adapter_command="generate")

    return parser


def _write_payload(payload: dict[str, Any], stream: TextIO, as_json: bool) -> None:
    if as_json:
        stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        stream.write("\n")
        return
    if payload.get("kind") == "action":
        stream.write(payload["message"])
        stream.write("\n\n")
        stream.write(render_action_packet(payload["action"]))
    elif payload.get("kind") == "status":
        stream.write(payload["message"])
        stream.write("\n\n")
        stream.write(render_status(payload["status"]))
    elif payload.get("kind") == "approval":
        stream.write(payload["message"])
        approval = payload.get("approval")
        if approval is not None:
            stream.write(
                f"\nReason: {approval['reason']}\nPhase: {approval['phase_id']}"
            )
    else:
        stream.write(payload["message"])
    stream.write("\n")


def _description(arguments: argparse.Namespace, root: Path) -> str:
    inline = arguments.description
    declared_file = getattr(arguments, "description_file", None)
    if inline is not None and declared_file is not None:
        raise UsageError("pass DESCRIPTION or --description-file, not both")
    if declared_file is None:
        if inline is None:
            raise UsageError("DESCRIPTION or --description-file is required")
        return inline
    path = Path(declared_file).expanduser()
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise UsageError(
            f"cannot read description file: {path}", {"path": str(path)}
        ) from exc


def _dispatch(
    arguments: argparse.Namespace, root: Path, pipeline: PipelineConfig
) -> dict[str, Any]:
    engine = Engine(pipeline)
    if arguments.command == "init":
        return engine.initialize(_description(arguments, root))
    if arguments.command in {"phase", "dynamic-phase"}:
        return engine.start_phase(arguments.run_id, arguments.phase)
    if arguments.command == "validate":
        return engine.validate(
            arguments.run_id, arguments.phase, outcome=arguments.outcome
        )
    if arguments.command == "request-approval":
        return engine.request_approval(
            arguments.run_id,
            reason=arguments.reason,
            details=arguments.details,
            outcome=arguments.outcome,
        )
    if arguments.command == "approve":
        return engine.approve(arguments.run_id, arguments.phase)
    if arguments.command == "block":
        return engine.block(
            arguments.run_id, reason=arguments.reason, details=arguments.details
        )
    if arguments.command == "status":
        return engine.status(arguments.run_id)
    if arguments.command == "resume":
        return engine.resume(arguments.run_id)
    if arguments.command == "run":
        return engine.run(arguments.run_id)
    raise UsageError(f"unsupported command: {arguments.command}")


def _initial_arguments(raw_args: Sequence[str]) -> argparse.Namespace:
    """Parse stable commands and provisionally parse a run-specific alias."""

    probe = CommandParser(add_help=False)
    _add_common_options(probe)
    probe.add_argument("command", nargs="?")
    probe.add_argument("remainder", nargs=argparse.REMAINDER)
    command = probe.parse_args(raw_args)
    if command.command and command.command not in RESERVED_COMMANDS:
        if not command.remainder:
            return build_parser().parse_args(raw_args)
        return build_parser([command.command]).parse_args(raw_args)
    return build_parser().parse_args(raw_args)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Parse and dispatch a command, returning a stable process exit code."""

    raw_args = list(sys.argv[1:] if argv is None else argv)
    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    wants_json = "--json" in raw_args
    wants_quiet = "--quiet" in raw_args

    # argparse renders help and raises SystemExit before returning a namespace.
    # Handle JSON help at the process boundary so --json still keeps its
    # one-object guarantee. Human-readable help retains argparse's normal form.
    if wants_json and ("--help" in raw_args or "-h" in raw_args):
        _write_payload(
            {
                "code": int(ExitCode.SUCCESS),
                "message": build_parser().format_help(),
            },
            output,
            True,
        )
        return int(ExitCode.SUCCESS)

    try:
        if any(arg in {"-h", "--help"} for arg in raw_args):
            build_parser().parse_args(raw_args)
            return int(ExitCode.SUCCESS)
        arguments = _initial_arguments(raw_args)
        if arguments.command is None:
            raise UsageError("a command is required")
        root = discover_repository_root(
            explicit_root=getattr(arguments, "root", None)
        )
        registry = load_registry(root)
        selector = getattr(arguments, "pipeline", None)
        if arguments.command == "adapters" and not getattr(
            arguments, "adapter_command", None
        ):
            raise UsageError("an adapters command is required")
        if arguments.command == "adapters":
            if selector is not None:
                raise UsageError("adapters generate processes all registered pipelines; omit --pipeline")
            from .adapters import generate_adapters

            payload = generate_adapters(
                root,
                registry,
                check=arguments.check,
            )
        else:
            pipeline = _selected_pipeline(arguments, root, registry)
            arguments = build_parser(pipeline.phase_ids).parse_args(raw_args)
            payload = _dispatch(arguments, root, pipeline)
        if wants_json or not wants_quiet:
            _write_payload(payload, output, wants_json)
        return int(payload["code"])
    except SpecromancyError as exc:
        payload = exc.as_dict()
        # Approval, agent-action, and blocked statuses are actionable responses;
        # all other expected failures are errors.
        stream = output if exc.code in ACTIONABLE_CODES else errors
        if wants_json or not (wants_quiet and exc.code in ACTIONABLE_CODES):
            _write_payload(payload, stream, wants_json)
        return int(exc.code)
    except Exception as exc:  # pragma: no cover - defensive process boundary
        payload = {
            "code": int(ExitCode.INTERNAL_ERROR),
            "message": "internal Specromancy error",
            "details": {"error": str(exc)},
        }
        _write_payload(payload, errors, wants_json)
        return int(ExitCode.INTERNAL_ERROR)
