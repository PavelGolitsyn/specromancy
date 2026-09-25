"""Content-level Git repository snapshots and mutation-policy checks."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any


class GitError(RuntimeError):
    """Git metadata cannot be captured under the pipeline's policy."""

    def __init__(self, diagnostic_code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.diagnostic_code = diagnostic_code
        self.message = message
        self.details = details


def capture_repository_snapshot(
    root: Path, *, allow_non_git: bool = False
) -> dict[str, Any]:
    """Capture HEAD, branch, and content/mode for tracked and visible files."""

    root = root.resolve(strict=True)
    try:
        inside = _git(root, "rev-parse", "--is-inside-work-tree", text=True)
    except (OSError, subprocess.TimeoutExpired) as exc:
        if allow_non_git:
            return _non_git_snapshot(root)
        raise GitError("git-unavailable", "Git is unavailable", error=str(exc)) from exc
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        if allow_non_git:
            return _non_git_snapshot(root)
        raise GitError(
            "git-worktree-required",
            "the pipeline requires a Git worktree",
            stderr=inside.stderr.strip(),
        )

    try:
        head_result = _git(root, "rev-parse", "HEAD", text=True)
        branch_result = _git(
            root, "symbolic-ref", "--quiet", "--short", "HEAD", text=True
        )
        listed = _git(
            root, "ls-files", "-co", "--exclude-standard", "-z", text=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(
            "git-snapshot-failed", "Git metadata capture failed", error=str(exc)
        ) from exc
    if listed.returncode != 0:
        raise GitError(
            "git-snapshot-failed",
            "Git could not enumerate repository files",
            stderr=listed.stderr.decode("utf-8", "replace").strip(),
        )
    files: dict[str, dict[str, Any]] = {}
    for raw in listed.stdout.split(b"\0"):
        if not raw:
            continue
        path = os.fsdecode(raw)
        normalized = PurePosixPath(path).as_posix()
        if normalized == ".git" or normalized.startswith(".git/"):
            continue
        if normalized == ".specromancy" or normalized.startswith(".specromancy/"):
            continue
        if not os.path.lexists(root / normalized):
            # Deleted tracked files are represented by their absence and are
            # therefore discovered by snapshot comparison.
            continue
        files[normalized] = _path_record(root, normalized)
    return {
        "is_worktree": True,
        "head": head_result.stdout.strip() if head_result.returncode == 0 else None,
        "branch": branch_result.stdout.strip() if branch_result.returncode == 0 else None,
        "files": dict(sorted(files.items())),
    }


def compare_snapshots(
    before: dict[str, Any], after: dict[str, Any]
) -> dict[str, Any]:
    """Return added/changed/deleted/mode/rename details for two snapshots."""

    old = before.get("files", {})
    new = after.get("files", {})
    old_paths = set(old)
    new_paths = set(new)
    added = set(new_paths - old_paths)
    deleted = set(old_paths - new_paths)
    changed: set[str] = set()
    mode_changed: set[str] = set()
    for path in old_paths & new_paths:
        if old[path].get("sha256") != new[path].get("sha256") or old[path].get(
            "kind"
        ) != new[path].get("kind"):
            changed.add(path)
        elif old[path].get("mode") != new[path].get("mode"):
            mode_changed.add(path)

    renames: list[dict[str, str]] = []
    for source in sorted(tuple(deleted)):
        source_record = old[source]
        destination = next(
            (
                candidate
                for candidate in sorted(added)
                if new[candidate].get("sha256") == source_record.get("sha256")
                and new[candidate].get("kind") == source_record.get("kind")
            ),
            None,
        )
        if destination is not None:
            deleted.remove(source)
            added.remove(destination)
            renames.append({"from": source, "to": destination})
    paths = set(added) | set(deleted) | changed | mode_changed
    for rename in renames:
        paths.update(rename.values())
    return {
        "added": sorted(added),
        "changed": sorted(changed),
        "deleted": sorted(deleted),
        "mode_changed": sorted(mode_changed),
        "renamed": renames,
        "paths": sorted(paths),
        "before_head": before.get("head"),
        "after_head": after.get("head"),
    }


def enforce_mutation_policy(
    before: dict[str, Any],
    after: dict[str, Any],
    policy: str,
    allowlist: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    """Compare snapshots and raise when changed paths violate the policy."""

    comparison = compare_snapshots(before, after)
    comparison["policy"] = policy
    comparison["status"] = "passed"
    comparison["head"] = {
        "is_worktree": after.get("is_worktree", False),
        "head": after.get("head"),
        "branch": after.get("branch"),
    }
    violations: list[str] = []
    if policy == "read-only":
        violations = list(comparison["paths"])
    elif policy == "allowlist":
        violations = [
            path
            for path in comparison["paths"]
            if not any(_glob_matches(path, pattern) for pattern in allowlist)
        ]
    elif policy != "repository-write":
        raise ValueError(f"unsupported mutation policy: {policy!r}")
    if violations:
        comparison["status"] = "failed"
        comparison["violations"] = violations
        raise GitError(
            "mutation-policy-violation",
            f"repository changes violate the {policy!r} mutation policy",
            mutation_result=comparison,
            paths=violations,
        )
    comparison["violations"] = []
    return comparison


def _path_record(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise GitError(
            "git-snapshot-failed", "an enumerated path cannot be inspected", path=relative
        ) from exc
    mode = stat.S_IMODE(metadata.st_mode)
    if stat.S_ISLNK(metadata.st_mode):
        target = os.readlink(path)
        content = os.fsencode(target)
        kind = "symlink"
    elif stat.S_ISREG(metadata.st_mode):
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise GitError(
                "git-snapshot-failed", "an enumerated file cannot be read", path=relative
            ) from exc
        kind = "file"
    else:
        raise GitError(
            "git-snapshot-failed",
            "an enumerated path is neither a regular file nor a symlink",
            path=relative,
        )
    return {"sha256": hashlib.sha256(content).hexdigest(), "mode": mode, "kind": kind}


def _git(root: Path, *arguments: str, text: bool) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=text,
        timeout=15,
    )


def _non_git_snapshot(root: Path) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative == ".git" or relative.startswith(".git/"):
            continue
        if relative == ".specromancy" or relative.startswith(".specromancy/"):
            continue
        if path.is_symlink() or path.is_file():
            files[relative] = _path_record(root, relative)
    return {
        "is_worktree": False,
        "head": None,
        "branch": None,
        "files": files,
    }


def _glob_matches(path: str, pattern: str) -> bool:
    if fnmatch.fnmatchcase(path, pattern):
        return True
    if pattern.endswith("/**") and path == pattern[:-3].rstrip("/"):
        return True
    return False


# A concise public alias matches the terminology used in action records.
snapshot_repository = capture_repository_snapshot
