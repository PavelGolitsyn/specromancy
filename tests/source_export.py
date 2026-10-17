"""Exclude generated development debris, preserving real workflow evidence."""

from pathlib import Path


def ignore_development_outputs(directory: str, names: list[str]) -> set[str]:
    return {
        name for name in names
        if name in {".git", ".specromancy", "__pycache__", ".venv", "build", "dist"}
        or name.endswith((".pyc", ".pyo", ".egg-info", ".dist-info"))
        or (Path(directory) / name / "pyvenv.cfg").is_file()
    }
