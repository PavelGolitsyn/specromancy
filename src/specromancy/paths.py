"""Repository discovery and repository-confined path construction."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Final

from .errors import ExternalCommandError, SafetyError, ValidationError


_RUN_ID: Final = re.compile(r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")


def _start_directory(start: str | Path | None) -> Path:
    candidate = Path.cwd() if start is None else Path(start)
    candidate = candidate.expanduser().resolve()
    candidate = candidate.parent if candidate.is_file() else candidate
    if not candidate.is_dir():
        raise ValidationError(
            "Repository discovery path is not a directory.", path=str(candidate)
        )
    return candidate


def _filesystem_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / ".specromancy" / "config.json").is_file():
            return candidate.resolve()
        if (candidate / "pyproject.toml").is_file():
            return candidate.resolve()
    return None


def discover_repository(
    start: str | Path | None = None, *, allow_filesystem_fallback: bool = False
) -> Path:
    """Return the nearest Git root, optionally using explicit test markers."""

    start_dir = _start_directory(start)
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start_dir,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        if allow_filesystem_fallback:
            fallback = _filesystem_root(start_dir)
            if fallback is not None:
                return fallback
        raise ExternalCommandError(
            "Git is required to discover the repository root.",
            hint="Install Git or use the explicit filesystem fallback in tests.",
        ) from exc

    if completed.returncode == 0:
        output = completed.stdout.strip()
        if not output:
            raise ValidationError("Git returned an empty repository root.")
        root = Path(output).expanduser().resolve()
        if not root.is_dir():
            raise ValidationError(
                "Git returned a repository root that is not a directory.",
                path=str(root),
            )
        return root

    if allow_filesystem_fallback:
        fallback = _filesystem_root(start_dir)
        if fallback is not None:
            return fallback

    raise ValidationError(
        "No Git repository could be discovered.",
        hint="Run the command inside a Git repository or pass --repo.",
        details={"git_exit_code": completed.returncode},
    )


@dataclass(frozen=True)
class RepositoryPaths:
    """Construct normalized paths which cannot escape a repository root."""

    root: Path

    def __post_init__(self) -> None:
        resolved = Path(self.root).expanduser().resolve()
        if not resolved.is_dir():
            raise ValidationError("Repository root is not a directory.", path=str(resolved))
        object.__setattr__(self, "root", resolved)

    def resolve_relative(self, serialized: str | Path, *, allow_root: bool = False) -> Path:
        raw = str(serialized)
        windows = PureWindowsPath(raw)
        if not raw or "\x00" in raw:
            raise SafetyError("Managed paths must be non-empty and contain no NUL bytes.")
        if "\\" in raw:
            raise SafetyError(
                "Serialized paths must use POSIX separators.",
                path=raw,
            )
        candidate_input = Path(raw)
        if candidate_input.is_absolute() or windows.is_absolute() or windows.drive:
            raise SafetyError("Managed paths must be repository-relative.", path=raw)
        if ".." in candidate_input.parts:
            raise SafetyError("Parent traversal is not allowed in managed paths.", path=raw)

        candidate = (self.root / candidate_input).resolve()
        try:
            relative = candidate.relative_to(self.root)
        except ValueError as exc:
            raise SafetyError("Managed path escapes the repository root.", path=raw) from exc
        if relative == Path(".") and not allow_root:
            raise SafetyError("Managed path must identify a repository child.", path=raw)
        return candidate

    def serialize(self, path: str | Path) -> str:
        resolved = Path(path).expanduser().resolve()
        try:
            relative = resolved.relative_to(self.root)
        except ValueError as exc:
            raise SafetyError("Path cannot be serialized outside the repository.") from exc
        if relative == Path("."):
            return "."
        return relative.as_posix()

    @property
    def state_dir(self) -> Path:
        return self.resolve_relative(".specromancy")

    @property
    def config_file(self) -> Path:
        return self.resolve_relative(".specromancy/config.json")

    @property
    def runs_dir(self) -> Path:
        return self.resolve_relative(".specromancy/runs")

    def run_dir(self, run_id: str) -> Path:
        if not _RUN_ID.fullmatch(run_id):
            raise ValidationError("Run ID is not valid.", details={"run_id": run_id})
        return self.resolve_relative(f".specromancy/runs/{run_id}")

    def run_manifest(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "run.json"

    def run_events(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "events.jsonl"

    def run_lock(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "run.lock"

    def run_artifact(self, run_id: str, relative_path: str | Path) -> Path:
        raw = str(relative_path)
        if Path(raw).is_absolute() or PureWindowsPath(raw).is_absolute():
            raise SafetyError("Artifact paths must be run-relative.", path=raw)
        run_relative = Path(".specromancy") / "runs" / run_id / raw
        target = self.resolve_relative(run_relative.as_posix())
        run_dir = self.run_dir(run_id)
        try:
            target.relative_to(run_dir)
        except ValueError as exc:
            raise SafetyError("Artifact path escapes its run directory.", path=raw) from exc
        return target
