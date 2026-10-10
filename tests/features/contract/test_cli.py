from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from specromancy.exit_codes import ExitCode


ROOT = Path(__file__).resolve().parents[3]


class CliContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".git").mkdir()
        skill = self.root / ".agents" / "skills" / "compose" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\nname: compose\ndescription: Fixture.\n---\n", encoding="utf-8"
        )
        self.pipeline = self.root / "workflow/pipelines/cli-fixture.toml"
        self.pipeline.parent.mkdir(parents=True)
        (self.root / "workflow/pipelines.toml").write_text(
            'schema_version = 1\n[[pipelines]]\nid = "cli-fixture"\npath = "pipelines/cli-fixture.toml"\n', encoding="utf-8"
        )
        self.pipeline.write_text(
            textwrap.dedent(
                """
                schema_version = 1
                id = "cli-fixture"
                version = 1
                start = "compose"
                terminal_outcomes = ["done"]
                artifact_pattern = "artifacts/{visit:03}-{phase}.md"
                allow_non_git = true
                [[phases]]
                id = "compose"
                skill = "compose"
                inputs = ["request"]
                output_name = "{visit:03}-result.md"
                mutation = "read-only"
                completion_criteria = ["Write a result."]
                validator = "file"
                approval_conditions = []
                stop_conditions = []
                max_visits = 1
                [[phases.transitions]]
                outcome = "done"
                """
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def command(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "specromancy",
                "--json",
                "--root",
                str(self.root),
                "--pipeline",
                "cli-fixture",
                *arguments,
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_fresh_process_drives_full_run_with_dynamic_alias(self) -> None:
        initialized = self.command("init", "Build the fixture")
        self.assertEqual(initialized.returncode, ExitCode.AGENT_ACTION_REQUIRED)
        init_payload = json.loads(initialized.stdout)
        self.assertEqual(init_payload["schema_version"], 1)
        self.assertEqual(init_payload["action"]["visit_status"], "pending")
        run_id = init_payload["action"]["run_id"]

        started = self.command("compose", run_id)
        self.assertEqual(started.returncode, ExitCode.AGENT_ACTION_REQUIRED)
        action = json.loads(started.stdout)["action"]
        self.assertEqual(action["visit_status"], "active")
        Path(action["output"]["absolute_path"]).write_text(
            "complete\n", encoding="utf-8"
        )

        status = self.command("status", run_id)
        self.assertEqual(status.returncode, ExitCode.SUCCESS)
        self.assertEqual(json.loads(status.stdout)["status"]["status"], "active")
        completed = self.command("validate", run_id, "compose")
        self.assertEqual(completed.returncode, ExitCode.SUCCESS, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"]["status"], "completed")
        resumed = self.command("resume", run_id)
        self.assertEqual(resumed.returncode, ExitCode.SUCCESS)

    def test_generic_phase_and_run_commands_stop_at_agent_boundary(self) -> None:
        first = json.loads(self.command("init", "Generic phase").stdout)
        run_id = first["action"]["run_id"]
        generic = self.command("phase", run_id, "compose")
        self.assertEqual(generic.returncode, ExitCode.AGENT_ACTION_REQUIRED)
        self.assertEqual(json.loads(generic.stdout)["action"]["phase"], "compose")

        second = json.loads(self.command("init", "Deterministic run").stdout)
        run_id = second["action"]["run_id"]
        run = self.command("run", run_id)
        self.assertEqual(run.returncode, ExitCode.AGENT_ACTION_REQUIRED)
        self.assertEqual(json.loads(run.stdout)["action"]["visit_status"], "active")

    def test_malformed_status_fails_before_recovery_without_changing_files(self) -> None:
        initialized = self.command("init", "Malformed status fixture")
        self.assertEqual(initialized.returncode, ExitCode.AGENT_ACTION_REQUIRED)
        run_id = json.loads(initialized.stdout)["action"]["run_id"]
        directory = self.root / ".specromancy" / "runs" / run_id
        manifest_path = directory / "run.json"
        events_path = directory / "events.jsonl"
        original_manifest = manifest_path.read_bytes()
        original_events = events_path.read_bytes()
        events = original_events.splitlines(keepends=True)
        self.assertGreater(len(events), 1)
        self.assertEqual(json.loads(events[-1])["manifest_revision"],
                         json.loads(original_manifest)["revision"])

        for gap in (False, True):
            for level, message in (("run", "manifest status is invalid"),
                                   ("visit", "visit identity or status is invalid")):
                for invalid in (None, False, True, 0, 1, 1.5, "unknown", [], {}):
                    with self.subTest(gap=gap, level=level, invalid=invalid):
                        manifest = json.loads(original_manifest)
                        target = manifest if level == "run" else manifest["visits"][0]
                        target["status"] = invalid
                        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                        events_path.write_bytes(b"".join(events[:-1]) if gap else original_events)
                        before = {path.relative_to(directory): path.read_bytes()
                                  for path in directory.rglob("*") if path.is_file()}

                        result = self.command("status", run_id)

                        self.assertEqual(result.returncode, ExitCode.INTERNAL_ERROR)
                        self.assertEqual(result.stdout, "")
                        self.assertEqual(json.loads(result.stderr), {
                            "code": 12,
                            "message": message,
                            "details": {"error_code": "corrupt-run", "run_id": run_id},
                        })
                        self.assertEqual(
                            {path.relative_to(directory): path.read_bytes()
                             for path in directory.rglob("*") if path.is_file()},
                            before,
                        )

    def test_valid_manifest_recovers_before_artifact_verification_fails(self) -> None:
        initialized = self.command("init", "Artifact recovery fixture")
        self.assertEqual(initialized.returncode, ExitCode.AGENT_ACTION_REQUIRED)
        run_id = json.loads(initialized.stdout)["action"]["run_id"]
        directory = self.root / ".specromancy" / "runs" / run_id
        manifest_path = directory / "run.json"
        events_path = directory / "events.jsonl"
        original_manifest = manifest_path.read_bytes()
        manifest = json.loads(original_manifest)
        retained_events = b"".join(events_path.read_bytes().splitlines(keepends=True)[:-1])
        events_path.write_bytes(retained_events)
        (directory / manifest["request"]["path"]).write_text("changed\n", encoding="utf-8")

        result = self.command("resume", run_id)

        self.assertEqual(result.returncode, ExitCode.INTERNAL_ERROR)
        self.assertEqual(result.stdout, "")
        self.assertEqual(json.loads(result.stderr)["details"]["error_code"],
                         "artifact-hash-mismatch")
        self.assertEqual(manifest_path.read_bytes(), original_manifest)
        recovered_events = events_path.read_bytes()
        self.assertTrue(recovered_events.startswith(retained_events))
        appended = recovered_events[len(retained_events):].splitlines()
        self.assertEqual(len(appended), 1)
        recovery = json.loads(appended[0])
        self.assertEqual(recovery["type"], "recovery")
        self.assertEqual(recovery["manifest_revision"], manifest["revision"])


if __name__ == "__main__":
    unittest.main()
