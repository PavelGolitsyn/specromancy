from __future__ import annotations

import io
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from specromancy.adapters import (
    MANIFEST_PATH,
    AdapterError,
    generate_adapters,
)
from specromancy.cli import adapter_command_metadata, main
from specromancy.config import load_pipeline
from specromancy.exit_codes import ExitCode
from specromancy.hashing import sha256_bytes


class AdapterFixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".git").mkdir()
        (self.root / "AGENTS.md").write_text(
            "# Repository instructions\n\n- Keep workflow logic canonical.\n",
            encoding="utf-8",
        )
        self.write_skill("compose")
        self.pipeline_path = self.root / "pipeline.toml"
        self.pipeline_path.write_text(
            textwrap.dedent(
                """
                schema_version = 1
                id = "adapter-fixture"
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
            ).lstrip(),
            encoding="utf-8",
        )

    def close(self) -> None:
        self.temporary.cleanup()

    def write_skill(self, name: str) -> Path:
        path = self.root / ".agents" / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            textwrap.dedent(
                f"""
                ---
                name: {name}
                description: Use when the fixture needs {name}.
                license: MIT
                compatibility: Specromancy pipeline schema version 1.
                metadata:
                  role: phase
                ---

                # {name.title()}

                Follow the emitted action packet.
                """
            ).lstrip(),
            encoding="utf-8",
        )
        return path

    def pipeline(self):
        return load_pipeline(self.pipeline_path, self.root)

    def generate(self, *, check: bool = False):
        pipeline = self.pipeline()
        return generate_adapters(
            self.root,
            pipeline,
            adapter_command_metadata(pipeline.phase_ids),
            check=check,
        )

    def snapshot(self) -> dict[str, bytes]:
        manifest_path = self.root / MANIFEST_PATH
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        paths = [entry["path"] for entry in manifest["generated"]]
        paths.append(MANIFEST_PATH)
        return {path: (self.root / path).read_bytes() for path in paths}


class AdapterGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = AdapterFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_two_generations_are_byte_identical(self) -> None:
        self.fixture.generate()
        first = self.fixture.snapshot()
        self.fixture.generate()
        self.assertEqual(self.fixture.snapshot(), first)
        self.fixture.generate(check=True)

    def test_check_detects_changes_without_writing_generated_output(self) -> None:
        cases = ("modified", "missing", "unexpected", "canonical")
        for case in cases:
            with self.subTest(case=case):
                fixture = AdapterFixture()
                try:
                    fixture.generate()
                    before = fixture.snapshot()
                    if case == "modified":
                        path = fixture.root / ".claude" / "CLAUDE.md"
                        path.write_text("changed\n", encoding="utf-8")
                    elif case == "missing":
                        (fixture.root / ".opencode" / "commands" / "specromancy-status.md").unlink()
                    elif case == "unexpected":
                        path = fixture.root / ".opencode" / "commands" / "specromancy-extra.md"
                        path.write_text("extra\n", encoding="utf-8")
                    else:
                        with (fixture.root / "AGENTS.md").open("a", encoding="utf-8") as stream:
                            stream.write("- A new canonical rule.\n")
                    changed_before_check = {
                        path: (fixture.root / path).read_bytes()
                        for path in before
                        if (fixture.root / path).is_file()
                    }
                    with self.assertRaises(AdapterError) as caught:
                        fixture.generate(check=True)
                    self.assertEqual(caught.exception.code, ExitCode.ADAPTER_DRIFT)
                    changed_after_check = {
                        path: (fixture.root / path).read_bytes()
                        for path in changed_before_check
                    }
                    self.assertEqual(changed_after_check, changed_before_check)
                finally:
                    fixture.close()

    def test_generation_never_overwrites_an_unowned_destination(self) -> None:
        path = self.fixture.root / ".claude" / "CLAUDE.md"
        path.parent.mkdir(parents=True)
        path.write_text("user owned\n", encoding="utf-8")
        with self.assertRaises(AdapterError) as caught:
            self.fixture.generate()
        self.assertEqual(caught.exception.details["unowned"], [".claude/CLAUDE.md"])
        self.assertEqual(path.read_text(encoding="utf-8"), "user owned\n")
        self.assertFalse((self.fixture.root / MANIFEST_PATH).exists())

    def test_stale_unchanged_file_is_removed(self) -> None:
        extra = self.fixture.write_skill("extra")
        self.fixture.generate()
        generated = self.fixture.root / ".claude" / "skills" / "extra" / "SKILL.md"
        self.assertTrue(generated.is_file())
        extra.unlink()
        result = self.fixture.generate()
        self.assertFalse(generated.exists())
        self.assertEqual(result["adapters"]["removed"], [".claude/skills/extra/SKILL.md"])

    def test_stale_modified_file_is_preserved_with_an_error(self) -> None:
        extra = self.fixture.write_skill("extra")
        self.fixture.generate()
        generated = self.fixture.root / ".claude" / "skills" / "extra" / "SKILL.md"
        generated.write_text("user change\n", encoding="utf-8")
        extra.unlink()
        with self.assertRaises(AdapterError) as caught:
            self.fixture.generate()
        self.assertEqual(
            caught.exception.details["stale_modified"],
            [".claude/skills/extra/SKILL.md"],
        )
        self.assertEqual(generated.read_text(encoding="utf-8"), "user change\n")

    def test_manifest_records_targets_relative_paths_and_content_hashes(self) -> None:
        self.fixture.generate()
        manifest = json.loads(
            (self.fixture.root / MANIFEST_PATH).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["schema_version"], 1)
        modes = {entry["name"]: entry["mode"] for entry in manifest["targets"]}
        self.assertEqual(
            modes,
            {
                "claude": "generated",
                "codex": "native",
                "copilot": "generated",
                "hermes": "native",
                "opencode": "generated",
            },
        )
        for target in manifest["targets"]:
            if target["mode"] == "native":
                self.assertEqual(target["paths"], [])
        for entry in manifest["generated"]:
            path = entry["path"]
            self.assertFalse(Path(path).is_absolute())
            self.assertNotIn("..", Path(path).parts)
            self.assertEqual(
                entry["sha256"], sha256_bytes((self.fixture.root / path).read_bytes())
            )

    def test_tampered_manifest_cannot_claim_an_unrelated_path(self) -> None:
        self.fixture.generate()
        unrelated = self.fixture.root / "README.md"
        unrelated.write_text("keep me\n", encoding="utf-8")
        manifest_path = self.fixture.root / MANIFEST_PATH
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["generated"].append(
            {
                "path": "README.md",
                "sha256": sha256_bytes(unrelated.read_bytes()),
                "target": "claude",
            }
        )
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(AdapterError) as caught:
            self.fixture.generate()
        self.assertIn("outside generated adapter locations", caught.exception.message)
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep me\n")

    def test_unmanaged_skill_support_file_does_not_count_as_drift(self) -> None:
        self.fixture.generate()
        support = self.fixture.root / ".claude" / "skills" / "compose" / "notes.md"
        support.write_text("user support file\n", encoding="utf-8")
        self.fixture.generate(check=True)

    def test_cli_check_reports_json_drift_and_writes_nothing(self) -> None:
        common = [
            "--root",
            str(self.fixture.root),
            "--pipeline",
            str(self.fixture.pipeline_path),
            "--json",
            "adapters",
            "generate",
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        self.assertEqual(main(common, stdout=stdout, stderr=stderr), ExitCode.SUCCESS)
        changed = self.fixture.root / ".github" / "copilot-instructions.md"
        changed.write_text("changed\n", encoding="utf-8")
        before = changed.read_bytes()
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = main([*common, "--check"], stdout=stdout, stderr=stderr)
        self.assertEqual(code, ExitCode.ADAPTER_DRIFT)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertIn(".github/copilot-instructions.md", payload["details"]["modified"])
        self.assertEqual(changed.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
