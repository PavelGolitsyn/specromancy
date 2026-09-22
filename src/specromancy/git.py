"""Read-only Git inspection for implementation baselines and inventories."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .errors import ExternalCommandError, ValidationError
from .io import sha256_file
from .paths import RepositoryPaths


@dataclass(frozen=True)
class GitStatusEntry:
    path: str
    index_status: str
    worktree_status: str
    original_path: str | None = None


@dataclass(frozen=True)
class GitSnapshot:
    head: str | None
    branch: str | None
    staged_paths: tuple[str, ...]
    unstaged_paths: tuple[str, ...]
    untracked_paths: tuple[str, ...]
    entries: tuple[GitStatusEntry, ...]
    hashes: dict[str, str | None]


def _run_git(root: Path, arguments: Iterable[str], *, text: bool = True):
    argv = ["git", *arguments]
    try:
        completed = subprocess.run(
            argv,
            cwd=root,
            check=False,
            capture_output=True,
            text=text,
            encoding="utf-8" if text else None,
        )
    except FileNotFoundError as exc:
        raise ExternalCommandError(
            "Git is required to inspect the implementation repository.",
            hint="Install Git and retry the implementation action.",
        ) from exc
    if completed.returncode != 0:
        stderr = completed.stderr if text else completed.stderr.decode("utf-8", "replace")
        raise ExternalCommandError(
            "Git could not inspect the implementation repository.",
            hint="Resolve the Git repository error and retry.",
            details={"git_exit_code": completed.returncode, "stderr": stderr[:500]},
        )
    return completed.stdout


def current_head(repository_root: str | Path) -> str | None:
    root = Path(repository_root).resolve()
    try:
        return str(_run_git(root, ["rev-parse", "--verify", "HEAD"])).strip() or None
    except ExternalCommandError as exc:
        # An unborn repository has no HEAD, but remains a valid implementation target.
        if exc.details.get("git_exit_code") == 128:
            return None
        raise


def current_branch(repository_root: str | Path) -> str | None:
    root = Path(repository_root).resolve()
    try:
        output = str(_run_git(root, ["symbolic-ref", "--quiet", "--short", "HEAD"])).strip()
    except ExternalCommandError as exc:
        if exc.details.get("git_exit_code") == 1:
            return None
        raise
    return output or None


def status_entries(repository_root: str | Path) -> tuple[GitStatusEntry, ...]:
    root = Path(repository_root).resolve()
    raw = _run_git(
        root,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        text=False,
    )
    chunks = raw.split(b"\0")
    result: list[GitStatusEntry] = []
    index = 0
    while index < len(chunks):
        chunk = chunks[index]
        index += 1
        if not chunk:
            continue
        decoded = chunk.decode("utf-8", errors="surrogateescape")
        if len(decoded) < 4 or decoded[2] != " ":
            raise ValidationError(
                "Git returned malformed porcelain status output.",
                hint="Retry after checking the repository with git status.",
            )
        x, y, path = decoded[0], decoded[1], decoded[3:]
        original: str | None = None
        if (x in "RC" or y in "RC") and index < len(chunks) and chunks[index]:
            original = chunks[index].decode("utf-8", errors="surrogateescape")
            index += 1
        result.append(GitStatusEntry(path=path, index_status=x, worktree_status=y, original_path=original))
    return tuple(result)


def _hashes(root: Path, paths: Iterable[str]) -> dict[str, str | None]:
    confined = RepositoryPaths(root)
    result: dict[str, str | None] = {}
    for serialized in sorted(set(paths)):
        target = confined.resolve_relative(serialized)
        result[serialized] = sha256_file(target) if target.is_file() else None
    return result


def capture_snapshot(
    repository_root: str | Path,
    *,
    additional_paths: Iterable[str] = (),
) -> GitSnapshot:
    root = Path(repository_root).resolve()
    entries = status_entries(root)
    staged: set[str] = set()
    unstaged: set[str] = set()
    untracked: set[str] = set()
    changed: set[str] = set(additional_paths)
    for entry in entries:
        paths = {entry.path}
        if entry.original_path is not None:
            paths.add(entry.original_path)
        changed.update(paths)
        if entry.index_status == "?" and entry.worktree_status == "?":
            untracked.update(paths)
        else:
            if entry.index_status not in {" ", "?"}:
                staged.update(paths)
            if entry.worktree_status not in {" ", "?"}:
                unstaged.update(paths)
    return GitSnapshot(
        head=current_head(root),
        branch=current_branch(root),
        staged_paths=tuple(sorted(staged)),
        unstaged_paths=tuple(sorted(unstaged)),
        untracked_paths=tuple(sorted(untracked)),
        entries=entries,
        hashes=_hashes(root, changed),
    )


def snapshot_payload(snapshot: GitSnapshot) -> dict[str, object]:
    return {
        "git_head": snapshot.head,
        "git_branch": snapshot.branch,
        "staged_paths": list(snapshot.staged_paths),
        "unstaged_paths": list(snapshot.unstaged_paths),
        "untracked_paths": list(snapshot.untracked_paths),
        "hashes": dict(snapshot.hashes),
    }


# Descriptive aliases used by phase code and external contract tests.
capture_worktree = capture_snapshot
worktree_snapshot = capture_snapshot
git_status = status_entries
capture_baseline = capture_snapshot
