import contextlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import tempfile
import unittest

from specromancy.artifacts.research import validate_research
from specromancy.artifacts.frontmatter import parse_frontmatter
from specromancy.clock import FixedClock
from specromancy.cli import main
from specromancy.errors import (
    ExitCode,
    InvalidInputError,
    InvalidTransitionError,
    ValidationError,
)
from specromancy.io import sha256_file
from specromancy.phases.research import (
    complete_research,
    start_research,
    validate_research_file,
)


RUN_ID = "20260921-research"
NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def artifact(*, location: str = "README.md:1", evidence_row: str | None = None) -> str:
    row = evidence_row or (
        f"| E-001 | The fixture is documented. | Repository | {location} | High |"
    )
    return f'''---
schema-version: "1"
run-id: "{RUN_ID}"
stage: "research"
status: "ready"
created-at: "2026-09-21T12:00:00Z"
---

## Request interpretation

Document the current fixture behavior.

## Repository map

`README.md` documents the fixture.

## Current behavior

The fixture is documented (E-001).

## Constraints and invariants

The research phase is read-only outside its run directory.

## Evidence

| Evidence ID | Claim | Source | Location | Confidence |
| --- | --- | --- | --- | --- |
{row}

## Unknowns and assumptions

None.

## Risks

Documentation may drift after implementation.

## Planning inputs

- Affected areas: README documentation.
- Acceptance criteria gaps: None.
- Recommended verification: Run the contract test suite.
'''


class ResearchArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / "README.md").write_text("# Fixture\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_valid_minimal_research_artifact(self) -> None:
        parsed = validate_research(artifact(), self.root, RUN_ID)
        self.assertEqual(parsed.evidence[0].evidence_id, "E-001")
        self.assertEqual(parsed.warnings, ())

    def test_repository_path_in_source_column_is_supported(self) -> None:
        row = "| E-001 | The fixture is documented. | README.md | line 1 | High |"
        parsed = validate_research(artifact(evidence_row=row), self.root, RUN_ID)
        self.assertEqual(parsed.evidence[0].source, "README.md")

    def test_missing_or_duplicated_heading_is_rejected(self) -> None:
        missing = artifact().replace(
            "## Risks\n\nDocumentation may drift after implementation.\n", ""
        )
        duplicate = artifact() + "\n## Risks\n\nAgain.\n"
        for content in (missing, duplicate):
            with self.subTest(content=content[-30:]), self.assertRaises(ValidationError) as caught:
                validate_research(content, self.root, RUN_ID)
            self.assertIsNotNone(caught.exception.hint)

    def test_malformed_evidence_table_is_rejected(self) -> None:
        content = artifact(evidence_row="| E-001 | Claim | Repository | README.md:1 |")
        with self.assertRaises(ValidationError) as caught:
            validate_research(content, self.root, RUN_ID)
        self.assertIn("cells", caught.exception.hint or "")

    def test_local_evidence_outside_repository_is_rejected(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            validate_research(artifact(location="../outside.md:1"), self.root, RUN_ID)
        self.assertIn("relative", caught.exception.hint or "")

    def test_placeholder_content_is_rejected(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            validate_research(artifact().replace("None.", "TBD"), self.root, RUN_ID)
        self.assertIn("Replace", caught.exception.hint or "")

    def test_secret_like_content_is_rejected(self) -> None:
        content = artifact().replace("None.", "password=super-secret-value")
        with self.assertRaises(ValidationError) as caught:
            validate_research(content, self.root, RUN_ID)
        self.assertIn("sensitive", caught.exception.hint or "")

    def test_line_number_drift_warns_without_failing(self) -> None:
        parsed = validate_research(artifact(location="README.md:99"), self.root, RUN_ID)
        self.assertEqual(len(parsed.warnings), 1)

    def test_frontmatter_rejects_duplicate_or_general_yaml_syntax(self) -> None:
        duplicate = artifact().replace(
            'run-id: "20260921-research"\n',
            'run-id: "20260921-research"\nrun-id: "20260921-research"\n',
        )
        unquoted = artifact().replace('schema-version: "1"', "schema-version: 1")
        for content in (duplicate, unquoted):
            with self.subTest(), self.assertRaises(ValidationError) as caught:
                parse_frontmatter(content, expected_run_id=RUN_ID)
            self.assertIsNotNone(caught.exception.hint)

    def test_assumption_stated_elsewhere_must_be_recorded(self) -> None:
        content = artifact().replace(
            "The fixture is documented (E-001).",
            "Assumption: callers use the public CLI.",
        )
        with self.assertRaises(ValidationError) as caught:
            validate_research(content, self.root, RUN_ID)
        self.assertIn("assumption", caught.exception.message.lower())


class ResearchLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        subprocess.run(["git", "init", "--quiet"], cwd=self.root, check=True)
        (self.root / ".gitignore").write_text(".specromancy/runs/\n", encoding="utf-8")
        (self.root / "README.md").write_text("# Fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Specromancy Tests",
                "-c",
                "user.email=tests@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "fixture",
            ],
            cwd=self.root,
            check=True,
        )
        self.run_dir = self.root / ".specromancy" / "runs" / RUN_ID
        self.run_dir.mkdir(parents=True)
        request = f'''---
schema-version: "1"
run-id: "{RUN_ID}"
stage: "request"
status: "ready"
created-at: "2026-09-21T12:00:00Z"
---

# Request

Research the fixture.
'''
        request_path = self.run_dir / "request.md"
        request_path.write_text(request, encoding="utf-8")
        request_digest = sha256_file(request_path)
        manifest = {
            "schema_version": "1",
            "run_id": RUN_ID,
            "title": "Research fixture",
            "created_at": "2026-09-21T12:00:00Z",
            "updated_at": "2026-09-21T12:00:00Z",
            "status": "initialized",
            "current_phase": None,
            "repository_root": str(self.root),
            "repository_url": None,
            "git_base": None,
            "git_head": None,
            "git_branch": None,
            "initial_worktree": {
                "recorded_at": "2026-09-21T12:00:00Z",
                "staged_paths": [],
                "unstaged_paths": [],
                "untracked_paths": [],
            },
            "implementation_baseline": None,
            "requirements": [],
            "artifacts": {
                "request": {
                    "path": f".specromancy/runs/{RUN_ID}/request.md",
                    "sha256": request_digest,
                    "validated_at": "2026-09-21T12:00:00Z",
                    "schema_version": "1",
                    "bindings": {},
                }
            },
            "approvals": [],
            "changed_files": [],
            "review_subject_sha256": None,
            "review_cycle": 0,
            "max_review_cycles": 3,
            "last_error": None,
            "events_path": f".specromancy/runs/{RUN_ID}/events.jsonl",
            "lock_path": f".specromancy/runs/{RUN_ID}/run.lock",
        }
        (self.run_dir / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.run_dir / "events.jsonl").write_text("", encoding="utf-8")
        self.clock = FixedClock(NOW)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_unknown_run_id_is_rejected(self) -> None:
        with self.assertRaises(InvalidInputError):
            validate_research_file(self.root, "20260921-unknown", clock=self.clock)

    def test_completion_from_invalid_prior_state_is_rejected(self) -> None:
        (self.run_dir / "research.md").write_text(artifact(), encoding="utf-8")
        with self.assertRaises(InvalidTransitionError):
            complete_research(self.root, RUN_ID, clock=self.clock)

    def test_completion_binds_digest_and_unchanged_replay_is_idempotent(self) -> None:
        start_research(self.root, RUN_ID, clock=self.clock)
        (self.run_dir / "research.md").write_text(artifact(), encoding="utf-8")
        first = complete_research(self.root, RUN_ID, clock=self.clock)
        event_count = len((self.run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines())
        second = complete_research(self.root, RUN_ID, clock=self.clock)
        manifest = json.loads((self.run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(first.artifact_sha256, manifest["artifacts"]["research"]["sha256"])
        self.assertTrue(second.replayed)
        self.assertEqual(
            len((self.run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()),
            event_count,
        )

    def test_research_completion_rejects_source_changes(self) -> None:
        start_research(self.root, RUN_ID, clock=self.clock)
        (self.run_dir / "research.md").write_text(artifact(), encoding="utf-8")
        (self.root / "README.md").write_text("# Changed during research\n", encoding="utf-8")
        with self.assertRaises(ValidationError) as caught:
            complete_research(self.root, RUN_ID, clock=self.clock)
        self.assertIn("outside the active run", caught.exception.message)

    def test_cli_exposes_path_validation_and_lifecycle(self) -> None:
        def invoke(*arguments: str) -> tuple[int, dict[str, object]]:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(arguments)
            return code, json.loads(output.getvalue())

        common = ("--repo", str(self.root), "--format", "json")
        code, started = invoke("phase", "start", RUN_ID, "research", *common)
        self.assertEqual(code, ExitCode.SUCCESS)
        self.assertEqual(started["data"]["status"], "research_in_progress")

        code, path_result = invoke("artifact", "path", RUN_ID, "research", *common)
        self.assertEqual(code, ExitCode.SUCCESS)
        self.assertEqual(
            path_result["data"]["path"],
            f".specromancy/runs/{RUN_ID}/research.md",
        )
        (self.run_dir / "research.md").write_text(artifact(), encoding="utf-8")

        code, validation = invoke("validate", RUN_ID, "research", *common)
        self.assertEqual(code, ExitCode.SUCCESS)
        self.assertEqual(validation["data"]["warnings"], [])
        code, completed = invoke("phase", "complete", RUN_ID, "research", *common)
        self.assertEqual(code, ExitCode.SUCCESS)
        self.assertEqual(completed["data"]["status"], "research_ready")


if __name__ == "__main__":
    unittest.main()
