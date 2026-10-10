from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from specromancy.git import (
    GitError,
    capture_repository_snapshot,
    compare_snapshots,
    enforce_mutation_policy,
)


class GitSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.name", "Test"], check=True
        )
        (self.root / ".gitignore").write_text(".specromancy/\nignored.txt\n")
        (self.root / "tracked.txt").write_text("base\n")
        (self.root / "dirty.txt").write_text("base\n")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-qm", "base"], check=True
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_content_snapshot_detects_dirty_untracked_delete_rename_and_mode(self) -> None:
        (self.root / "dirty.txt").write_text("already dirty\n")
        before = capture_repository_snapshot(self.root)
        (self.root / "dirty.txt").write_text("changed again\n")
        (self.root / "new.txt").write_text("new\n")
        (self.root / "tracked.txt").rename(self.root / "renamed.txt")
        mode = (self.root / ".gitignore").stat().st_mode
        os.chmod(self.root / ".gitignore", mode | 0o100)
        after = capture_repository_snapshot(self.root)
        result = compare_snapshots(before, after)
        self.assertIn("dirty.txt", result["changed"])
        self.assertIn("new.txt", result["added"])
        self.assertEqual(
            result["renamed"], [{"from": "tracked.txt", "to": "renamed.txt"}]
        )
        self.assertIn(".gitignore", result["mode_changed"])

    def test_symlink_target_is_hashed_without_following_it(self) -> None:
        outside = Path(self.temporary.name).parent / "specromancy-outside-target"
        outside.write_text("one\n")
        try:
            (self.root / "link").symlink_to(outside)
            before = capture_repository_snapshot(self.root)
            outside.write_text("two\n")
            unchanged = capture_repository_snapshot(self.root)
            self.assertEqual(before["files"]["link"], unchanged["files"]["link"])
            (self.root / "link").unlink()
            (self.root / "link").symlink_to("another-target")
            changed = compare_snapshots(before, capture_repository_snapshot(self.root))
            self.assertIn("link", changed["changed"])
        finally:
            outside.unlink(missing_ok=True)

    def test_read_only_and_allowlist_enforcement(self) -> None:
        before = capture_repository_snapshot(self.root)
        (self.root / "docs").mkdir()
        (self.root / "docs" / "result.md").write_text("ok\n")
        after = capture_repository_snapshot(self.root)
        with self.assertRaises(GitError):
            enforce_mutation_policy(before, after, "read-only")
        enforce_mutation_policy(before, after, "allowlist", ("docs/**",))
        with self.assertRaises(GitError):
            enforce_mutation_policy(before, after, "allowlist", ("src/**",))

    def test_read_only_rejects_index_head_and_branch_only_changes(self) -> None:
        (self.root / "tracked.txt").write_text("staged later\n")
        before_index = capture_repository_snapshot(self.root)
        subprocess.run(
            ["git", "-C", str(self.root), "add", "tracked.txt"], check=True
        )
        after_index = capture_repository_snapshot(self.root)
        self.assertEqual(compare_snapshots(before_index, after_index)["paths"], [])
        with self.assertRaises(GitError) as staged:
            enforce_mutation_policy(before_index, after_index, "read-only")
        self.assertEqual(staged.exception.details["paths"], ["@git/index"])

        before_commit = after_index
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-qm", "index change"],
            check=True,
        )
        after_commit = capture_repository_snapshot(self.root)
        self.assertEqual(compare_snapshots(before_commit, after_commit)["paths"], [])
        with self.assertRaises(GitError) as committed:
            enforce_mutation_policy(before_commit, after_commit, "read-only")
        self.assertEqual(committed.exception.details["paths"], ["@git/head"])

        before_branch = after_commit
        subprocess.run(
            ["git", "-C", str(self.root), "checkout", "-qb", "alternate"],
            check=True,
        )
        after_branch = capture_repository_snapshot(self.root)
        self.assertEqual(compare_snapshots(before_branch, after_branch)["paths"], [])
        with self.assertRaises(GitError) as switched:
            enforce_mutation_policy(before_branch, after_branch, "read-only")
        self.assertEqual(switched.exception.details["paths"], ["@git/branch"])

    def test_allowlist_never_allows_git_metadata_changes(self) -> None:
        (self.root / "tracked.txt").write_text("staged later\n")
        before = capture_repository_snapshot(self.root)
        subprocess.run(
            ["git", "-C", str(self.root), "add", "tracked.txt"], check=True
        )
        after = capture_repository_snapshot(self.root)
        with self.assertRaises(GitError) as raised:
            enforce_mutation_policy(before, after, "allowlist", ("**",))
        self.assertEqual(raised.exception.details["paths"], ["@git/index"])

    def test_non_git_operation_requires_explicit_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "file.txt").write_text("content\n")
            with self.assertRaises(GitError) as raised:
                capture_repository_snapshot(root)
            self.assertEqual(raised.exception.diagnostic_code, "git-worktree-required")
            snapshot = capture_repository_snapshot(root, allow_non_git=True)
            self.assertFalse(snapshot["is_worktree"])
            self.assertIn("file.txt", snapshot["files"])


if __name__ == "__main__":
    unittest.main()
