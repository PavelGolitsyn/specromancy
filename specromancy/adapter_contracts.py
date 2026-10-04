"""Shared adapter contracts, re-exported by the public adapters facade."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .errors import SpecromancyError
from .exit_codes import ExitCode


ADAPTER_SCHEMA_VERSION = 1
GENERATOR_VERSION = 1
MANIFEST_PATH = "adapters/manifest.json"
REGENERATION_COMMAND = "bin/specromancy adapters generate"


@dataclass(frozen=True, slots=True)
class AdapterCommand:
    """A thin harness command that delegates to the stable CLI."""

    name: str
    cli_command: str
    arguments: str
    description: str


ADAPTER_COMMANDS = (
    AdapterCommand(
        "init",
        "init",
        "PIPELINE_ID DESCRIPTION",
        "Initialize a Specromancy run and return its recorded next action.",
    ),
    AdapterCommand(
        "resume",
        "resume",
        "RUN_ID",
        "Resume a Specromancy run from persisted state.",
    ),
    AdapterCommand(
        "status",
        "status",
        "RUN_ID",
        "Read a Specromancy run's persisted status and next command.",
    ),
    AdapterCommand(
        "phase",
        "phase",
        "RUN_ID PHASE",
        "Start or resume the named current phase and return its action packet.",
    ),
)

HARNESS_MODES = {
    "claude": "generated",
    "codex": "native",
    "copilot": "generated",
    "hermes": "native",
    "opencode": "generated",
}


class AdapterError(SpecromancyError):
    """Report adapter drift or an ownership conflict without unsafe writes."""

    def __init__(self, message: str, details: Mapping[str, Any]) -> None:
        super().__init__(ExitCode.ADAPTER_DRIFT, message, details)


def _target_for_path(path: str) -> str:
    if path.startswith(".agents/"):
        return "codex"
    if path.startswith(".claude/"):
        return "claude"
    if path.startswith(".github/"):
        return "copilot"
    if path.startswith(".opencode/"):
        return "opencode"
    raise AdapterError("generated path has no target harness", {"path": path})
