"""Dependency-free command-line boundary for Specromancy."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, TextIO

from .errors import SpecromancyError, UsageError
from .exit_codes import EXIT_CODE_DESCRIPTIONS, ExitCode


RESERVED_COMMANDS = frozenset(
    {
        "init",
        "phase",
        "validate",
        "approve",
        "request-approval",
        "block",
        "status",
        "resume",
        "run",
        "adapters",
    }
)

ACTIONABLE_CODES = frozenset(
    {
        ExitCode.APPROVAL_REQUIRED,
        ExitCode.AGENT_ACTION_REQUIRED,
        ExitCode.RUN_BLOCKED,
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
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="pipeline configuration path",
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

    _add_command(
        subparsers,
        "init",
        "create a run for DESCRIPTION",
        [(("description",), {"metavar": "DESCRIPTION"})],
    )
    _add_command(
        subparsers,
        "phase",
        "emit the action packet for PHASE",
        [
            (("run_id",), {"metavar": "RUN_ID"}),
            (("phase",), {"metavar": "PHASE"}),
        ],
    )
    _add_command(
        subparsers,
        "validate",
        "validate a run's current or named phase",
        [
            (("run_id",), {"metavar": "RUN_ID"}),
            (("phase",), {"metavar": "PHASE", "nargs": "?"}),
        ],
    )
    _add_command(
        subparsers,
        "approve",
        "approve a phase artifact",
        [
            (("run_id",), {"metavar": "RUN_ID"}),
            (("phase",), {"metavar": "PHASE"}),
        ],
    )
    for name, help_text in (
        ("request-approval", "request approval for the current visit"),
        ("block", "mark a run blocked"),
        ("status", "show run status"),
        ("resume", "resume a run"),
        ("run", "advance a run"),
    ):
        _add_command(
            subparsers,
            name,
            help_text,
            [(("run_id",), {"metavar": "RUN_ID"})],
        )

    adapters = _add_command(
        subparsers, "adapters", "manage generated harness adapters", []
    )
    adapter_commands = adapters.add_subparsers(
        dest="adapter_command", metavar="COMMAND"
    )
    generate = adapter_commands.add_parser(
        "generate", help="generate harness adapters"
    )
    _add_common_options(generate)
    generate.set_defaults(command="adapters", adapter_command="generate")

    for phase in dynamic_phases:
        if phase in RESERVED_COMMANDS:
            continue
        alias = _add_command(
            subparsers,
            phase,
            f"emit the action packet for the {phase} phase",
            [(("run_id",), {"metavar": "RUN_ID"})],
        )
        alias.set_defaults(command="dynamic-phase", phase=phase)

    return parser


def _placeholder_result(arguments: argparse.Namespace, root: Path) -> dict[str, Any]:
    command = arguments.command
    if command == "adapters":
        command = f"adapters {getattr(arguments, 'adapter_command', '')}".rstrip()
    elif command == "dynamic-phase":
        command = str(arguments.phase)
    return {
        "code": int(ExitCode.AGENT_ACTION_REQUIRED),
        "message": f"command '{command}' is reserved; implementation follows in a later stage",
        "details": {"command": command, "root": str(root)},
    }


def _write_payload(payload: dict[str, Any], stream: TextIO, as_json: bool) -> None:
    if as_json:
        stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        stream.write("\n")
        return
    stream.write(payload["message"])
    stream.write("\n")


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
        arguments = build_parser().parse_args(raw_args)
        if arguments.command is None:
            raise UsageError("a command is required")
        if arguments.command == "adapters" and not getattr(
            arguments, "adapter_command", None
        ):
            raise UsageError("an adapters command is required")

        root = discover_repository_root(explicit_root=getattr(arguments, "root", None))
        payload = _placeholder_result(arguments, root)
        if wants_json or not wants_quiet:
            _write_payload(payload, output, wants_json)
        return int(ExitCode.AGENT_ACTION_REQUIRED)
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
