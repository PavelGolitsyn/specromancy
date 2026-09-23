"""Side-effect-free installation and repository diagnostics."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .adapters import check as check_adapters
from .contracts import validate_contracts
from .errors import SpecromancyError
from .io import read_text
from .locking import inspect_run_lock, lock_is_stale
from .paths import RepositoryPaths
from .security import validate_canonical_skills


HARNESSES = ("claude", "codex", "copilot", "hermes", "opencode")
_SAFE_CONFIG_KEYS = {"schema_version", "max_review_cycles"}


@dataclass(frozen=True)
class Diagnostic:
    name: str
    status: str
    summary: str
    remediation: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)


@dataclass(frozen=True)
class DoctorReport:
    status: str
    diagnostics: tuple[Diagnostic, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "diagnostics": [diagnostic.as_dict() for diagnostic in self.diagnostics],
        }


def _diagnostic(name: str, operation, success: str, remediation: str) -> Diagnostic:
    try:
        operation()
    except (SpecromancyError, OSError, ValueError, json.JSONDecodeError) as exc:
        return Diagnostic(name, "fail", str(exc), remediation)
    return Diagnostic(name, "pass", success)


def _git_version(root: Path) -> str:
    completed = subprocess.run(
        ["git", "--version"], cwd=root, check=False, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    if completed.returncode != 0:
        raise OSError("Git version probe failed.")
    value = completed.stdout.strip()
    if not value.startswith("git version "):
        raise ValueError("Git returned an unexpected version response.")
    return value.removeprefix("git version ")


def _writable_run_directory(paths: RepositoryPaths) -> None:
    target = paths.runs_dir
    probe = target if target.exists() else target.parent
    if not probe.is_dir() or not os.access(probe, os.W_OK):
        raise OSError("The Specromancy run directory is not writable.")


def _stale_locks(paths: RepositoryPaths) -> list[str]:
    stale: list[str] = []
    if not paths.runs_dir.exists():
        return stale
    for run_dir in sorted(path for path in paths.runs_dir.iterdir() if path.is_dir()):
        lock = run_dir / "run.lock"
        if not lock.exists():
            continue
        try:
            info = inspect_run_lock(paths.root, run_dir.name)
            if info is not None and lock_is_stale(info)[0]:
                stale.append(run_dir.name)
        except SpecromancyError:
            stale.append(run_dir.name)
    return stale


def _risky_configuration(paths: RepositoryPaths) -> list[str]:
    if not paths.config_file.is_file():
        return []
    value = json.loads(read_text(paths.config_file))
    if not isinstance(value, dict):
        return ["configuration is not an object"]
    risks = [f"unsupported key: {key}" for key in sorted(set(value) - _SAFE_CONFIG_KEYS)]
    cycles = value.get("max_review_cycles")
    if cycles is not None and (not isinstance(cycles, int) or isinstance(cycles, bool) or not 1 <= cycles <= 10):
        risks.append("max_review_cycles is outside the supported range 1..10")
    return risks


def run_doctor(root: str | Path) -> DoctorReport:
    """Inspect only safe metadata; never emit environment or configuration values."""

    repository = Path(root).resolve()
    paths = RepositoryPaths(repository)
    diagnostics: list[Diagnostic] = [
        Diagnostic(
            "python",
            "pass" if tuple(map(int, platform.python_version_tuple()[:2])) >= (3, 11) else "fail",
            f"Python {platform.python_version()} with specromancy {__version__}.",
            None if tuple(map(int, platform.python_version_tuple()[:2])) >= (3, 11) else "Install Python 3.11 or newer.",
        )
    ]
    try:
        git_version = _git_version(repository)
    except (OSError, ValueError) as exc:
        diagnostics.append(Diagnostic("git", "fail", str(exc), "Install Git and run inside a repository."))
    else:
        diagnostics.append(Diagnostic("git", "pass", f"Git {git_version}; repository discovered."))
    diagnostics.append(_diagnostic(
        "run_directory", lambda: _writable_run_directory(paths),
        "Run directory is writable.", "Make .specromancy writable for the current user.",
    ))
    diagnostics.append(_diagnostic(
        "contracts", validate_contracts, "Packaged contracts are internally consistent.",
        "Reinstall Specromancy from a complete distribution.",
    ))
    diagnostics.append(_diagnostic(
        "canonical_skills",
        lambda: validate_canonical_skills(repository, ("pipeline", "research", "plan", "implement", "review")),
        "Canonical skills and reference graphs are valid.",
        "Repair canonical skill frontmatter or confined references.",
    ))
    diagnostics.append(_diagnostic(
        "adapters", lambda: check_adapters(repository), "Generated adapters are current.",
        "Run `specromancy adapters generate` after resolving collisions.",
    ))
    stale = _stale_locks(paths)
    diagnostics.append(Diagnostic(
        "stale_locks", "warn" if stale else "pass",
        f"Stale or malformed locks: {', '.join(stale)}." if stale else "No stale locks found.",
        "Inspect ownership, then use explicit lock recovery." if stale else None,
    ))
    try:
        risks = _risky_configuration(paths)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        diagnostics.append(Diagnostic(
            "configuration", "warn", f"Configuration could not be validated: {type(exc).__name__}.",
            "Repair .specromancy/config.json without adding secrets.",
        ))
    else:
        diagnostics.append(Diagnostic(
            "configuration", "warn" if risks else "pass",
            "; ".join(risks) if risks else "No unsupported or risky configuration found.",
            "Remove unsupported keys or use documented safe bounds." if risks else None,
        ))
    found = [name for name in HARNESSES if shutil.which(name)]
    diagnostics.append(Diagnostic(
        "optional_harnesses", "pass", "Available: " + (", ".join(found) if found else "none") + "."
    ))
    overall = "fail" if any(row.status == "fail" for row in diagnostics) else (
        "warn" if any(row.status == "warn" for row in diagnostics) else "pass"
    )
    return DoctorReport(overall, tuple(diagnostics))


def render_doctor(report: DoctorReport) -> str:
    lines = [f"Specromancy doctor: {report.status.upper()}"]
    for diagnostic in report.diagnostics:
        lines.append(f"[{diagnostic.status.upper()}] {diagnostic.name}: {diagnostic.summary}")
        if diagnostic.remediation:
            lines.append(f"  Remediation: {diagnostic.remediation}")
    return "\n".join(lines)
