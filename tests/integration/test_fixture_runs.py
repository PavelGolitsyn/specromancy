import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from specromancy.errors import ValidationError
from specromancy.orchestrator import cancel_run
from specromancy.run import initialize_run

from tests.contract.test_plan_artifact import (
    REQUIREMENTS,
    RUN_ID,
    plan_artifact,
)
from specromancy.artifacts.plan import validate_plan


FIXTURES = Path(__file__).parents[1] / "fixtures" / "e2e"


class FixtureRunIntegrationTests(unittest.TestCase):
    def test_catalog_covers_every_stage_eight_scenario(self) -> None:
        expected = {
            "python-bug-fix", "typescript-feature", "dirty-worktree",
            "approval-migration", "underspecified", "repair-pass", "repair-exhausted",
        }
        observed = {path.parent.name for path in FIXTURES.glob("*/fixture.json")}
        self.assertEqual(observed, expected)
        for path in FIXTURES.glob("*/fixture.json"):
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(value["schema_version"], "1")
            self.assertTrue(value["provider_free"])
            self.assertIn("expected", value)

    def test_dirty_worktree_survives_run_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
            (root / ".gitignore").write_text(".specromancy/runs/\n", encoding="utf-8")
            (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
            (root / "notes.txt").write_text("baseline\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run([
                "git", "-c", "user.name=Tests", "-c", "user.email=tests@example.invalid",
                "commit", "--quiet", "-m", "fixture",
            ], cwd=root, check=True)
            (root / "notes.txt").write_text("unrelated user edit\n", encoding="utf-8")
            initialize_run(
                root, run_id="fixture-dirty-worktree", title="Dirty fixture",
                request_text="# Request\n\nUpdate README without changing notes.txt.",
            )
            cancelled = cancel_run(root, "fixture-dirty-worktree", reason="fixture stop")
            self.assertEqual(cancelled["status"], "cancelled")
            self.assertEqual(
                (root / "notes.txt").read_text(encoding="utf-8"), "unrelated user edit\n"
            )

    def test_destructive_migration_requires_approval_sensitive_label(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
            unsafe = plan_artifact(change_rows=(
                "| CHG-001 | create | migrations/002.sql | "
                "Delete production records in a destructive migration. | No |"
            ))
            with self.assertRaises(ValidationError) as caught:
                validate_plan(unsafe, root, RUN_ID, REQUIREMENTS, ("E-001",))
            self.assertIn("approval-sensitive", caught.exception.message)

    def test_underspecified_fixture_has_no_authorized_mutations(self) -> None:
        value = json.loads(
            (FIXTURES / "underspecified" / "fixture.json").read_text(encoding="utf-8")
        )
        self.assertEqual(value["expected"], "blocked")
        self.assertEqual(value["mutations"], [])


if __name__ == "__main__":
    unittest.main()
