"""Stable process exit codes for the public CLI contract."""

from enum import IntEnum


class ExitCode(IntEnum):
    """Exit status returned by a Specromancy command."""

    SUCCESS = 0
    USAGE_ERROR = 2
    INVALID_PIPELINE = 3
    NOT_FOUND = 4
    ILLEGAL_TRANSITION = 5
    VALIDATION_FAILED = 6
    APPROVAL_REQUIRED = 7
    AGENT_ACTION_REQUIRED = 8
    RUN_BLOCKED = 9
    LOCK_HELD = 10
    ADAPTER_DRIFT = 11
    INTERNAL_ERROR = 12


EXIT_CODE_DESCRIPTIONS = {
    ExitCode.SUCCESS: "Command completed successfully",
    ExitCode.USAGE_ERROR: "CLI usage error",
    ExitCode.INVALID_PIPELINE: "Invalid pipeline configuration",
    ExitCode.NOT_FOUND: "Run or artifact not found",
    ExitCode.ILLEGAL_TRANSITION: "Illegal state transition",
    ExitCode.VALIDATION_FAILED: "Validation failed",
    ExitCode.APPROVAL_REQUIRED: "Approval required",
    ExitCode.AGENT_ACTION_REQUIRED: "Agent action required",
    ExitCode.RUN_BLOCKED: "Run blocked or stopped",
    ExitCode.LOCK_HELD: "Concurrent run lock held",
    ExitCode.ADAPTER_DRIFT: "Adapter drift detected",
    ExitCode.INTERNAL_ERROR: "Internal or corrupt-state error",
}

# Named integer constants are kept for callers that do not want to import the enum.
SUCCESS = int(ExitCode.SUCCESS)
USAGE_ERROR = int(ExitCode.USAGE_ERROR)
INVALID_PIPELINE = int(ExitCode.INVALID_PIPELINE)
NOT_FOUND = int(ExitCode.NOT_FOUND)
ILLEGAL_TRANSITION = int(ExitCode.ILLEGAL_TRANSITION)
VALIDATION_FAILED = int(ExitCode.VALIDATION_FAILED)
APPROVAL_REQUIRED = int(ExitCode.APPROVAL_REQUIRED)
AGENT_ACTION_REQUIRED = int(ExitCode.AGENT_ACTION_REQUIRED)
RUN_BLOCKED = int(ExitCode.RUN_BLOCKED)
LOCK_HELD = int(ExitCode.LOCK_HELD)
ADAPTER_DRIFT = int(ExitCode.ADAPTER_DRIFT)
INTERNAL_ERROR = int(ExitCode.INTERNAL_ERROR)

