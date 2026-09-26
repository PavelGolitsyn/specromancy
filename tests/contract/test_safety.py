from __future__ import annotations

import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from specromancy.commands import execute_validation_commands
from specromancy.config import ValidationCommand, load_pipeline
from specromancy.engine import Engine, EngineError
from specromancy.exit_codes import ExitCode
from specromancy.run_store import RunStore

from tests.contract.support import DEFAULT_ARTIFACTS, CliRepository, advance_to


def phase(name: str, *, target: str | None = None, extra: str = "") -> str:
    transition = f'outcome = "next"\n' + (f'target = "{target}"\n' if target else "")
    return textwrap.dedent(
        f"""
        [[phases]]
        id = "{name}"
        skill = "{name}"
        inputs = ["request"]
        output_name = "{{visit:03}}-{name}.md"
        mutation = "read-only"
        completion_criteria = ["Complete safely."]
        validator = "file"
        approval_conditions = []
        stop_conditions = []
        {extra}
        [[phases.transitions]]
        {transition}
        """
    )


class SafetyFixture:
    def __init__(self, phases: str, *, terminal: str = "next") -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".git").mkdir()
        names = []
        for line in phases.splitlines():
            if line.strip().startswith("id ="):
                names.append(line.split('"')[1])
        for name in names:
            skill = self.root / ".agents" / "skills" / name / "SKILL.md"
            skill.parent.mkdir(parents=True, exist_ok=True)
            skill.write_text(f"---\nname: {name}\ndescription: Test.\n---\n")
        self.pipeline_path = self.root / "pipeline.toml"
        self.pipeline_path.write_text(
            textwrap.dedent(
                f"""
                schema_version = 1
                id = "safety"
                version = 1
                start = "{names[0]}"
                terminal_outcomes = ["{terminal}"]
                artifact_pattern = "artifacts/{{visit:03}}-{{phase}}.md"
                allow_non_git = true
                {phases}
                """
            )
        )
        self.pipeline = load_pipeline(self.pipeline_path, self.root)
        self.store = RunStore(self.root)
        self.engine = Engine(self.pipeline, self.store)

    def close(self) -> None:
        self.temporary.cleanup()

    def start(self) -> str:
        result = self.engine.initialize("safe request")
        run_id = result["action"]["run_id"]
        self.engine.start_phase(run_id, self.pipeline.start)
        return run_id

    def output(self, run_id: str, content: str = "done\n") -> None:
        manifest = self.store.load(run_id)
        self.store.write_visit_output(run_id, manifest["current_visit"], content)


class SafetyContractTests(unittest.TestCase):
    def test_real_git_read_only_phase_rejects_clean_and_preexisting_dirty_edits(self) -> None:
        for dirty_before_start in (False, True):
            with self.subTest(dirty_before_start=dirty_before_start):
                repo = CliRepository()
                try:
                    if dirty_before_start:
                        (repo.root / "tracked.txt").write_text(
                            "dirty before start\n", encoding="utf-8"
                        )
                    run_id = repo.initialize("Preserve read-only state")
                    repo.start_and_write(
                        run_id, "research", DEFAULT_ARTIFACTS["research"]
                    )
                    (repo.root / "tracked.txt").write_text(
                        "changed during phase\n", encoding="utf-8"
                    )
                    result = repo.command("validate", run_id, "research")
                    self.assertEqual(result.returncode, ExitCode.VALIDATION_FAILED)
                    self.assertEqual(
                        repo.payload(result)["details"]["error_code"],
                        "mutation-policy-violation",
                    )
                    manifest = json.loads(
                        (
                            repo.root
                            / ".specromancy"
                            / "runs"
                            / run_id
                            / "run.json"
                        ).read_text(encoding="utf-8")
                    )
                    self.assertEqual(
                        manifest["visits"][0]["mutation_result"]["violations"],
                        ["tracked.txt"],
                    )
                finally:
                    repo.close()

    def test_real_cli_marks_approval_stale_after_artifact_edit(self) -> None:
        repo = CliRepository()
        try:
            run_id = repo.initialize("Invalidate changed approval")
            advance_to(repo, run_id, "plan")
            output = repo.start_and_write(run_id, "plan", DEFAULT_ARTIFACTS["plan"])
            requested = repo.command(
                "request-approval", run_id, "--reason", "material-scope-change"
            )
            self.assertEqual(requested.returncode, ExitCode.APPROVAL_REQUIRED)
            output.write_text(DEFAULT_ARTIFACTS["plan"] + "\nChanged.\n", encoding="utf-8")
            approved = repo.command("approve", run_id, "plan")
            self.assertEqual(approved.returncode, ExitCode.APPROVAL_REQUIRED)
            self.assertEqual(
                repo.payload(approved)["details"]["error_code"], "stale-approval"
            )
            manifest = json.loads(
                (
                    repo.root / ".specromancy" / "runs" / run_id / "run.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["approvals"][0]["status"], "stale")
        finally:
            repo.close()

    def test_command_timeout_missing_executable_and_optional_continuation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / ".specromancy" / "run"
            run.mkdir(parents=True)
            results = execute_validation_commands(
                [
                    ValidationCommand(
                        (sys.executable, "-c", "import time; time.sleep(1)"),
                        0.01,
                        False,
                    ),
                    ValidationCommand(("definitely-not-a-real-executable",), 1, False),
                    ValidationCommand((sys.executable, "-c", "print('continued')"), 1),
                ],
                root,
                run,
                1,
            )
            self.assertTrue(results[0]["timed_out"])
            self.assertTrue(results[1]["missing_executable"])
            self.assertEqual(results[2]["status"], "passed")
            self.assertIn("continued", results[2]["stdout_summary"])

    def test_read_only_detects_edit_to_already_dirty_file(self) -> None:
        fixture = SafetyFixture(phase("inspect"))
        try:
            dirty = fixture.root / "dirty.txt"
            dirty.write_text("first\n")
            run_id = fixture.start()
            dirty.write_text("second\n")
            fixture.output(run_id)
            with self.assertRaises(EngineError) as raised:
                fixture.engine.validate(run_id)
            self.assertEqual(raised.exception.diagnostic_code, "mutation-policy-violation")
            manifest = fixture.store.load(run_id)
            self.assertEqual(manifest["status"], "active")
            self.assertEqual(
                manifest["visits"][0]["mutation_result"]["violations"], ["dirty.txt"]
            )
        finally:
            fixture.close()

    def test_command_failures_capture_outputs_and_redact_manifest_summary(self) -> None:
        secret = "stage05-super-secret"
        command = json.dumps(
            [
                sys.executable,
                "-c",
                "import os,sys; print(os.environ['SPECROMANCY_SECRET']); print('bad', file=sys.stderr); raise SystemExit(3)",
            ]
        )
        extra = f'[[phases.commands]]\nargv = {command}\ntimeout_seconds = 5\nrequired = true\n'
        fixture = SafetyFixture(phase("inspect", extra=extra))
        previous = os.environ.get("SPECROMANCY_SECRET")
        os.environ["SPECROMANCY_SECRET"] = secret
        try:
            run_id = fixture.start()
            fixture.output(run_id)
            with self.assertRaises(EngineError) as raised:
                fixture.engine.validate(run_id)
            self.assertEqual(raised.exception.diagnostic_code, "validation-command-failed")
            manifest = fixture.store.load(run_id)
            result = manifest["visits"][0]["command_results"][0]
            self.assertEqual(result["exit_code"], 3)
            self.assertNotIn(secret, json.dumps(manifest))
            stdout = fixture.store.run_directory(run_id) / result["stdout_path"]
            self.assertTrue(stdout.is_file())
        finally:
            if previous is None:
                os.environ.pop("SPECROMANCY_SECRET", None)
            else:
                os.environ["SPECROMANCY_SECRET"] = previous
            fixture.close()

    def test_artifact_edit_invalidates_pending_approval(self) -> None:
        configured = phase("publish").replace(
            "approval_conditions = []", 'approval_conditions = ["external-side-effect"]'
        )
        fixture = SafetyFixture(configured)
        try:
            run_id = fixture.start()
            fixture.output(run_id, "first\n")
            fixture.engine.request_approval(run_id, reason="external-side-effect")
            fixture.output(run_id, "changed\n")
            with self.assertRaises(EngineError) as raised:
                fixture.engine.approve(run_id, "publish")
            self.assertEqual(raised.exception.diagnostic_code, "stale-approval")
            manifest = fixture.store.load(run_id)
            self.assertEqual(manifest["status"], "awaiting-approval")
            self.assertEqual(manifest["approvals"][0]["status"], "stale")
        finally:
            fixture.close()

    def test_pipeline_edit_invalidates_pending_approval(self) -> None:
        configured = phase("publish").replace(
            "approval_conditions = []", 'approval_conditions = ["external-side-effect"]'
        )
        fixture = SafetyFixture(configured)
        try:
            run_id = fixture.start()
            fixture.output(run_id)
            fixture.engine.request_approval(run_id, reason="external-side-effect")
            fixture.pipeline_path.write_text(
                fixture.pipeline_path.read_text().replace(
                    "Complete safely.", "Complete with reviewed evidence."
                )
            )
            changed_engine = Engine(
                load_pipeline(fixture.pipeline_path, fixture.root), fixture.store
            )
            with self.assertRaises(EngineError) as raised:
                changed_engine.approve(run_id, "publish")
            self.assertEqual(raised.exception.details["mismatches"], ["pipeline"])
            self.assertEqual(fixture.store.load(run_id)["approvals"][0]["status"], "stale")
        finally:
            fixture.close()

    def test_loop_limit_blocks_before_new_visit(self) -> None:
        first = phase("first", target="second")
        second = phase(
            "second",
            target="first",
            extra="max_visits = 2",
        ).replace('target = "first"', 'target = "first"\nmax_traversals = 1')
        fixture = SafetyFixture(first + second, terminal="done")
        try:
            run_id = fixture.start()
            fixture.output(run_id)
            fixture.engine.validate(run_id)
            fixture.engine.start_phase(run_id, "second")
            fixture.output(run_id)
            fixture.engine.validate(run_id)
            fixture.engine.start_phase(run_id, "first")
            fixture.output(run_id)
            fixture.engine.validate(run_id)
            fixture.engine.start_phase(run_id, "second")
            fixture.output(run_id)
            blocked = fixture.engine.validate(run_id)
            manifest = fixture.store.load(run_id)
            self.assertEqual(blocked["code"], ExitCode.RUN_BLOCKED)
            self.assertEqual(len(manifest["visits"]), 4)
            self.assertEqual(
                manifest["block_reason"]["reason"], "transition-traversal-limit"
            )
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
