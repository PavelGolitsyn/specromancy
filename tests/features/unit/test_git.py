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
