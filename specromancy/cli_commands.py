"""Static CLI descriptions shared by parser construction and adapter metadata."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .contracts import RESERVED_COMMANDS


@dataclass(frozen=True, slots=True)
class CommandDefinition:
    name: str
    description: str
    arguments: list[tuple[tuple[str, ...], dict[str, Any]]]


COMMANDS = (
    CommandDefinition(
        'init',
        'create a run for DESCRIPTION',
        [
            (('description',), {'metavar': 'DESCRIPTION', 'nargs': '?'}),
            (('--description-file',), {'metavar': 'PATH', 'help': 'read DESCRIPTION from a UTF-8 file'}),
        ],
    ),
    CommandDefinition(
        'phase',
        'emit the action packet for PHASE',
        [
            (('run_id',), {'metavar': 'RUN_ID'}),
            (('phase',), {'metavar': 'PHASE'}),
        ],
    ),
    CommandDefinition(
        'validate',
        "validate a run's current or named phase",
        [
            (('run_id',), {'metavar': 'RUN_ID'}),
            (('phase',), {'metavar': 'PHASE', 'nargs': '?'}),
            (('--outcome',), {'metavar': 'OUTCOME'}),
        ],
    ),
    CommandDefinition(
        'approve',
        'approve a phase artifact',
        [
            (('run_id',), {'metavar': 'RUN_ID'}),
            (('phase',), {'metavar': 'PHASE'}),
        ],
    ),
    CommandDefinition(
        'request-approval',
        'request approval for the current visit',
        [
            (('run_id',), {'metavar': 'RUN_ID'}),
            (('--reason',), {'metavar': 'CODE'}),
            (('--details',), {'metavar': 'TEXT'}),
            (('--outcome',), {'metavar': 'OUTCOME'}),
        ],
    ),
    CommandDefinition(
        'block',
        'mark a run blocked',
        [
            (('run_id',), {'metavar': 'RUN_ID'}),
            (('--reason',), {'metavar': 'CODE'}),
            (('--details',), {'metavar': 'TEXT'}),
        ],
    ),
    CommandDefinition(
        'status',
        'show run status',
        [
            (('run_id',), {'metavar': 'RUN_ID'}),
        ],
    ),
    CommandDefinition(
        'resume',
        'resume a run',
        [
            (('run_id',), {'metavar': 'RUN_ID'}),
        ],
    ),
    CommandDefinition(
        'run',
        'advance a run',
        [
            (('run_id',), {'metavar': 'RUN_ID'}),
        ],
    ),
    CommandDefinition(
        'adapters',
        'manage generated harness adapters',
        [
        ],
    ),
)

if (
    len(COMMANDS) != len(RESERVED_COMMANDS)
    or {command.name for command in COMMANDS} != RESERVED_COMMANDS
):
    raise RuntimeError("CLI definitions and reserved commands disagree")


def command_definitions(dynamic_phases: Iterable[str] = ()) -> tuple[CommandDefinition, ...]:
    """Keep built-ins authoritative and aliases local to this invocation."""

    commands = list(COMMANDS)
    seen = set(RESERVED_COMMANDS)
    for phase in dynamic_phases:
        if phase in RESERVED_COMMANDS:
            continue
        if phase in seen:
            raise argparse.ArgumentError(None, f"conflicting subparser: {phase}")
        seen.add(phase)
        commands.append(
            CommandDefinition(
                phase,
                f"emit the action packet for the {phase} phase",
                [(("run_id",), {"metavar": "RUN_ID"})],
            )
        )
    return tuple(commands)


def adapter_command_metadata(dynamic_phases: Iterable[str] = ()) -> dict[str, Any]:
    """Return stable, sorted names and descriptions without inspecting argparse."""

    commands = sorted(command_definitions(dynamic_phases), key=lambda command: command.name)
    return {"commands": [
        {"name": command.name, "help": command.description} for command in commands
    ]}
