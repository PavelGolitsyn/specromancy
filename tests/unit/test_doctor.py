import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from specromancy.cli import main
from specromancy.doctor import DoctorReport, Diagnostic, render_doctor, run_doctor
from specromancy.errors import ValidationError


class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        subprocess.run(["git", "init", "--quiet"], cwd=self.root, check=True)
        self.root.joinpath(".specromancy/runs").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @mock.patch("specromancy.doctor.check_adapters")
    @mock.patch("specromancy.doctor.validate_canonical_skills")
    def test_report_is_safe_and_lists_harness_names_not_paths(self, skills, adapters) -> None:
        skills.return_value = ()
        adapters.return_value = {"status": "current", "checked": []}
        with mock.patch("specromancy.doctor.shutil.which", side_effect=lambda name: f"/secret/bin/{name}" if name == "codex" else None):
            report = run_doctor(self.root)
        rendered = render_doctor(report)
        self.assertIn("Available: codex", rendered)
        self.assertNotIn("/secret/bin", rendered)
        self.assertFalse(any("environment" in row.summary.lower() for row in report.diagnostics))

    def test_stale_lock_is_reported_without_owner_secrets(self) -> None:
        run = self.root / ".specromancy/runs/stale-run"
        run.mkdir()
        (run / "run.lock").write_text(json.dumps({
            "schema_version": "1", "run_id": "stale-run", "owner_id": "do-not-print",
            "pid": 99999999, "hostname": "localhost", "created_at": "2000-01-01T00:00:00Z",
            "command": "test",
        }), encoding="utf-8")
        with mock.patch("specromancy.doctor.check_adapters", return_value={}), mock.patch(
            "specromancy.doctor.validate_canonical_skills", return_value=()
        ):
            report = run_doctor(self.root)
        rendered = render_doctor(report)
        self.assertIn("stale-run", rendered)
        self.assertNotIn("do-not-print", rendered)

    def test_risky_configuration_reports_keys_not_values(self) -> None:
        secret_value = "must-never-appear"
        (self.root / ".specromancy/config.json").write_text(
            json.dumps({"schema_version": "1", "unsafe_token": secret_value}),
            encoding="utf-8",
        )
        with mock.patch("specromancy.doctor.check_adapters", return_value={}), mock.patch(
            "specromancy.doctor.validate_canonical_skills", return_value=()
        ):
            report = run_doctor(self.root)
        rendered = render_doctor(report)
        self.assertIn("unsupported key: unsafe_token", rendered)
        self.assertNotIn(secret_value, rendered)

    def test_cli_json_uses_standard_envelope(self) -> None:
        report = DoctorReport("pass", (Diagnostic("test", "pass", "Safe."),))
        output = io.StringIO()
        with mock.patch("specromancy.cli.discover_repository", return_value=self.root), mock.patch(
            "specromancy.cli.run_doctor", return_value=report
        ), contextlib.redirect_stdout(output):
            code = main(["doctor", "--format", "json"])
        envelope = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(envelope["command"], "doctor")
        self.assertEqual(envelope["data"]["status"], "pass")

    def test_cli_doctor_remains_callable_when_startup_contract_check_fails(self) -> None:
        report = DoctorReport("fail", (Diagnostic("contracts", "fail", "Broken."),))
        output = io.StringIO()
        with mock.patch("specromancy.cli.validate_contracts", side_effect=ValidationError("broken")), mock.patch(
            "specromancy.cli.discover_repository", return_value=self.root
        ), mock.patch("specromancy.cli.run_doctor", return_value=report), contextlib.redirect_stdout(output):
            code = main(["doctor", "--format", "json"])
        envelope = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(envelope["ok"])
        self.assertEqual(envelope["data"]["status"], "fail")


if __name__ == "__main__":
    unittest.main()
