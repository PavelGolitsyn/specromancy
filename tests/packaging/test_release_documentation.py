"""Execute consumer documentation against the active installed engine.

For a wheel-only check, copy this module plus examples/release-documentation/
and docs/guides/installation.md outside the producer. Set
SPECROMANCY_CONSUMER_BUNDLE to that bundle root and run this module there with
the wheel environment's Python. No tests build or install dependencies.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from specromancy_engine import RunStore, load_registry
from specromancy_engine.artifacts import ArtifactError


BUNDLE = (Path(os.environ["SPECROMANCY_CONSUMER_BUNDLE"])
          if "SPECROMANCY_CONSUMER_BUNDLE" in os.environ
          else Path(__file__).resolve().parents[2])
EXAMPLE = BUNDLE / "examples/release-documentation"


def snapshot(root: Path) -> dict:
    """Observe all project files, including hidden files, except run storage."""
    return {path.relative_to(root).as_posix(): (path.stat().st_mode, path.read_bytes())
            for path in root.rglob("*") if path.is_file()
            and ".specromancy" not in path.relative_to(root).parts}


def documented_python(path: Path, marker: str) -> str:
    text = path.read_text(encoding="utf-8").split(f"<!-- {marker}:", 1)[1]
    return re.search(r"```python\n(.*?)\n```", text, re.DOTALL).group(1)


class ReleaseDocumentationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "consumer"
        shutil.copytree(EXAMPLE, self.root)
        self.outside = self.base / "outside"
        self.outside.mkdir()
        self.env = {name: value for name, value in os.environ.items()
                    if not name.startswith(("PYTHON", "GIT_"))}
        self.env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1",
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]
        self.console = Path(sys.executable).with_name("specromancy")
        self.assertTrue(self.console.is_file(), "Install the checkout before testing")
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True,
                       env=self.env, capture_output=True)
        self.assertFalse((self.root / "src").exists())
        self.assertFalse((self.root / "bin/specromancy").exists())
        self.store = RunStore(self.root)

    def command(self, *args: str, expected: int = 0) -> dict:
        result = subprocess.run(
            [str(self.console), "--root", str(self.root), "--json", *args],
            cwd=self.outside, env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout or result.stderr)

    def walkthrough(self) -> dict:
        code = documented_python(self.root / "README.md", "walkthrough")
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code],
                                cwd=self.root, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_documented_walkthrough_completes_without_changing_project_files(self) -> None:
        for argv in ([str(self.console), "--help"],
                     [sys.executable, "-m", "specromancy_engine", "--help"]):
            result = subprocess.run(argv, cwd=self.root, env=self.env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--pipeline", result.stdout)
        self.assertEqual([p.id for p in load_registry(self.root).load_all()],
                         ["release-documentation"])
        canonical = snapshot(self.root)
        self.command("adapters", "generate")
        protected = snapshot(self.root)
        result = self.walkthrough()
        self.assertEqual(result["outcome"], "approved")
        manifest = self.store.load(result["run_id"])
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual([visit["phase_id"] for visit in manifest["visits"]],
                         ["draft-release-notes", "review-release-notes"])
        for visit, key in zip(manifest["visits"], ("notes", "review")):
            self.assertEqual(visit["status"], "completed")
            output = Path(result[key])
            self.assertEqual(output, self.store.run_directory(result["run_id"]) / visit["output"]["path"])
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), visit["output"]["sha256"])
        request = manifest["visits"][0]["inputs"][0]
        self.assertEqual((self.store.run_directory(result["run_id"]) / request["path"]).read_bytes(),
                         (self.root / "sample-changes.md").read_bytes())
        events = self.store.read_events(result["run_id"])
        self.assertEqual(events[-1]["manifest_revision"], manifest["revision"])
        self.command("adapters", "generate", "--check")
        self.assertEqual(snapshot(self.root), protected)
        self.assertEqual({path: protected[path] for path in canonical}, canonical)
        self.assertEqual(snapshot(self.outside), {})

    def test_completed_outputs_reject_store_writes_and_report_external_drift(self) -> None:
        result = self.walkthrough()
        run_id = result["run_id"]
        before = {p: p.read_bytes() for p in self.store.run_directory(run_id).rglob("*") if p.is_file()}
        for visit in self.store.load(run_id)["visits"]:
            with self.assertRaises(ArtifactError) as raised:
                self.store.write_visit_output(run_id, visit["ordinal"], "replacement")
            self.assertEqual(raised.exception.diagnostic_code, "immutable-artifact")
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        # Deliberate corruption in the temporary test consumer: status warns;
        # continuation rejects drift and does not silently reseal the artifact.
        Path(result["notes"]).write_text("tampered\n", encoding="utf-8")
        self.assertTrue(self.command("status", run_id)["status"]["warnings"])
        self.command("resume", run_id, expected=12)

    def test_documented_public_api_starts_an_action(self) -> None:
        before = snapshot(self.root)
        code = documented_python(BUNDLE / "docs/guides/installation.md", "public-api")
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code],
                                cwd=self.root, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(Path(result.stdout.strip()).is_relative_to(self.root / ".specromancy/runs"))
        self.assertEqual(snapshot(self.root), before)

    def start_draft(self) -> dict:
        pending = self.command("init", "--description-file", "sample-changes.md",
                               "--pipeline", "release-documentation", expected=8)["action"]
        return self.command("phase", pending["run_id"], pending["phase"], expected=8)["action"]

    def write_draft(self, action: dict) -> None:
        Path(action["output"]["absolute_path"]).write_text(
            "# Lantern 1.4.0\n## Summary\nReport updates.\n## Changes\n"
            "CSV export and duplicate notification fix.\n## Upgrade Notes\n"
            "Rename report_timeout to report_timeout_seconds before upgrading; keep its value.\n",
            encoding="utf-8",
        )

    def test_read_only_draft_rejects_project_mutation(self) -> None:
        action = self.start_draft()
        self.write_draft(action)
        (self.root / "sample-changes.md").write_text("modified during draft\n", encoding="utf-8")
        response = self.command("validate", action["run_id"], action["phase"], expected=6)
        self.assertEqual(response["details"]["error_code"], "mutation-policy-violation")
        self.assertEqual(self.store.load(action["run_id"])["status"], "active")

    def test_review_can_block_and_preserves_sealed_draft(self) -> None:
        action = self.start_draft()
        self.write_draft(action)
        draft = Path(action["output"]["absolute_path"]).read_bytes()
        pending = self.command("validate", action["run_id"], action["phase"], expected=8)["action"]
        review = self.command("phase", pending["run_id"], pending["phase"], expected=8)["action"]
        Path(review["output"]["absolute_path"]).write_text(
            "# Review\n## Verdict\nBlocked.\n## Findings\nNeeds clarification.\n"
            "## Verification\nCompared against the request.\n", encoding="utf-8")
        blocked = self.command("block", action["run_id"], "--reason", "unsupported-release-claims",
                               "--details", "Needs clarification", expected=9)
        self.assertEqual(blocked["status"]["status"], "blocked")
        manifest = self.store.load(action["run_id"])
        self.assertEqual(manifest["block_reason"]["reason"], "unsupported-release-claims")
        self.assertEqual(manifest["visits"][0]["status"], "completed")
        self.assertEqual(Path(action["output"]["absolute_path"]).read_bytes(), draft)

    def test_missing_registry_fails_without_writes(self) -> None:
        (self.root / "workflow/pipelines.toml").unlink()
        before = snapshot(self.root)
        response = self.command("init", "Request", "--pipeline", "release-documentation", expected=3)
        self.assertEqual(response["details"]["error_code"], "invalid-registry")
        self.assertFalse((self.root / ".specromancy").exists())
        self.assertEqual(snapshot(self.root), before)

    def test_missing_orchestrator_fails_without_writes(self) -> None:
        (self.root / ".agents/skills/pipeline/SKILL.md").unlink()
        before = snapshot(self.root)
        response = self.command("adapters", "generate", expected=11)
        self.assertEqual(response["message"], "canonical pipeline orchestrator skill is missing")
        self.assertEqual(snapshot(self.root), before)

    def test_invalid_or_missing_pipeline_selection_fails_without_writes(self) -> None:
        before = snapshot(self.root)
        for args in ((), ("--pipeline", "unknown"), ("--pipeline", "../release-documentation")):
            with self.subTest(args=args):
                self.command("init", "Request", *args, expected=3 if args else 2)
        self.assertFalse((self.root / ".specromancy").exists())
        self.assertEqual(snapshot(self.root), before)


if __name__ == "__main__":
    unittest.main()
