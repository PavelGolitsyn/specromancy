"""Harness-agnostic agentic pipeline framework."""

from .config import PipelineConfig, PipelineConfigError, load_pipeline
from .exit_codes import ExitCode

__all__ = ["ExitCode", "PipelineConfig", "PipelineConfigError", "load_pipeline"]
__version__ = "0.1.0"
