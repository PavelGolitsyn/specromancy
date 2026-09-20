import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from specromancy.errors import SafetyError, ValidationError
from specromancy.paths import RepositoryPaths, discover_repository


FIXTURE = Path(__file__).parents[1] / "fixtures" / "repositories" / "minimal"


class RepositoryDiscoveryTests(unittest.TestCase):
    def test_discovers_git_root_from_nested_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            subprocess.run(
                ["git", "init", "--quiet", str(root)], check=True, capture_output=True
            )
            nested = root / "one" / "two"
            nested.mkdir(parents=True)
            self.assertEqual(discover_repository(nested), root)

    def test_explicit_filesystem_fallback_finds_fixture_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory, "fixture")
            shutil.copytree(FIXTURE, root)
            nested = root / "nested"
            nested.mkdir()
            self.assertEqual(
                discover_repository(nested, allow_filesystem_fallback=True),
                root.resolve(),
            )

    def test_non_git_directory_without_fallback_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValidationError):
                discover_repository(directory)

    def test_missing_start_directory_is_rejected_before_running_git(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory, "missing")
            with self.assertRaises(ValidationError):
                discover_repository(missing)


class RepositoryPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.paths = RepositoryPaths(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_service_constructs_run_paths(self) -> None:
        run_id = "20260920-example"
        self.assertEqual(
            self.paths.serialize(self.paths.run_manifest(run_id)),
            ".specromancy/runs/20260920-example/run.json",
        )
        self.assertEqual(
            self.paths.serialize(self.paths.run_artifact(run_id, "research.md")),
            ".specromancy/runs/20260920-example/research.md",
        )

    def test_parent_traversal_is_rejected(self) -> None:
        with self.assertRaises(SafetyError):
            self.paths.resolve_relative("artifacts/../../outside")
        with self.assertRaises(SafetyError):
            self.paths.run_artifact("20260920-example", "../run.json")

    def test_absolute_artifact_path_is_rejected(self) -> None:
        with self.assertRaises(SafetyError):
            self.paths.run_artifact("20260920-example", "/tmp/outside.md")

    def test_windows_absolute_and_backslash_paths_are_rejected(self) -> None:
        fixtures = (r"C:\temp\artifact.md", r"folder\artifact.md", r"\\server\share\file")
        for fixture in fixtures:
            with self.subTest(path=fixture), self.assertRaises(SafetyError):
                self.paths.resolve_relative(fixture)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_symlink_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            link = self.root / "linked"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            with self.assertRaises(SafetyError):
                self.paths.resolve_relative("linked/artifact.md")


if __name__ == "__main__":
    unittest.main()
