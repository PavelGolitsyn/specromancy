"""Harness-agnostic agentic pipeline framework."""

from .config import PipelineConfig, PipelineConfigError, load_pipeline
from .engine import Engine, EngineError
from .exit_codes import ExitCode
from .registry import PipelineRegistry, PipelineRegistration, load_registry
from .run_store import (
    RunCorruptionError,
    RunNotFoundError,
    RunStore,
    generate_run_id,
    validate_run_id,
)

__all__ = [
    "ExitCode",
    "Engine",
    "EngineError",
    "PipelineConfig",
    "PipelineConfigError",
    "PipelineRegistry",
    "PipelineRegistration",
    "RunCorruptionError",
    "RunNotFoundError",
    "RunStore",
    "generate_run_id",
    "load_pipeline",
    "load_registry",
    "validate_run_id",
]
__version__ = "0.1.0"
