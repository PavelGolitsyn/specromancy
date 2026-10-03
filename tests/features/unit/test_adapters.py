from __future__ import annotations

import io
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from specromancy.adapters import (
    AGENTS_SOURCE_PATH,
    ENGINE_ARTIFACTS_PATH,
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
        instructions = self.root / AGENTS_SOURCE_PATH
        instructions.parent.mkdir(parents=True)
        instructions.write_text(
            "# Repository instructions\n\n- Keep workflow logic canonical.\n",
            encoding="utf-8",
        )
        self.write_skill("compose")
        self.write_skill("pipeline", engine=True)
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

    def write_skill(self, name: str, *, engine: bool = False) -> Path:
        base = self.root / ENGINE_ARTIFACTS_PATH if engine else self.root
        path = base / "skills" / name / "SKILL.md"
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
                        with (fixture.root / AGENTS_SOURCE_PATH).open("a", encoding="utf-8") as stream:
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
        self.assertEqual(
            result["adapters"]["removed"],
            [".agents/skills/extra/SKILL.md", ".claude/skills/extra/SKILL.md"],
        )

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
                "codex": "generated",
                "copilot": "generated",
                "hermes": "generated",
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

    def test_shared_skills_are_generated_from_pipeline_sources(self) -> None:
        source = self.fixture.root / "skills" / "compose" / "SKILL.md"
        before = source.read_bytes()
        self.fixture.generate()
        shared = self.fixture.root / ".agents" / "skills" / "compose" / "SKILL.md"
        claude = self.fixture.root / ".claude" / "skills" / "compose" / "SKILL.md"
        self.assertEqual(shared.read_bytes(), claude.read_bytes())
        self.assertIn("# Canonical source: skills/compose/SKILL.md.", shared.read_text())
        self.assertEqual(source.read_bytes(), before)

        manifest = json.loads((self.fixture.root / MANIFEST_PATH).read_text())
        inputs = {
            entry["path"] for entry in manifest["canonical_source"]["inputs"]
            if entry["kind"] == "canonical-skill"
        }
        self.assertEqual(inputs, {"skills/compose/SKILL.md"})
        targets = {entry["name"]: entry for entry in manifest["targets"]}
        for harness in ("codex", "copilot", "hermes", "opencode"):
            self.assertIn(".agents/skills/compose/SKILL.md", targets[harness]["paths"])

    def test_engine_artifacts_generate_instructions_and_orchestrator_directly(self) -> None:
        source = self.fixture.root / AGENTS_SOURCE_PATH
        skill = self.fixture.root / ENGINE_ARTIFACTS_PATH / "skills/pipeline/SKILL.md"
        before = {path: path.read_bytes() for path in (source, skill)}
        self.assertFalse((self.fixture.root / "AGENTS.md").exists())
        self.fixture.generate()
        root_instructions = self.fixture.root / "AGENTS.md"
        self.assertIn(f"Canonical source: {AGENTS_SOURCE_PATH}.", root_instructions.read_text())
        for relative in ("AGENTS.md", ".claude/CLAUDE.md", ".github/copilot-instructions.md"):
            self.assertIn(source.read_text(), (self.fixture.root / relative).read_text())
        for surface in (".agents", ".claude"):
            generated = self.fixture.root / surface / "skills/pipeline/SKILL.md"
            self.assertIn(f"# Canonical source: {ENGINE_ARTIFACTS_PATH}/skills/pipeline/SKILL.md.", generated.read_text())
        self.assertEqual(before, {path: path.read_bytes() for path in before})

        manifest = json.loads((self.fixture.root / MANIFEST_PATH).read_text())
        inputs = {entry["path"] for entry in manifest["canonical_source"]["inputs"]}
        self.assertIn(AGENTS_SOURCE_PATH, inputs)
        self.assertIn(f"{ENGINE_ARTIFACTS_PATH}/skills/pipeline/SKILL.md", inputs)
        self.assertNotIn("AGENTS.md", inputs)
        self.assertFalse(any(path.startswith(".agents/") for path in inputs))

    def test_generated_instructions_are_outputs_and_never_adapter_inputs(self) -> None:
        self.fixture.generate()
        instructions = self.fixture.root / "AGENTS.md"
        instructions.write_text("A change in generated instructions.\n")
        with self.assertRaises(AdapterError) as caught:
            self.fixture.generate(check=True)
        self.assertEqual(caught.exception.details["modified"], ["AGENTS.md"])
        self.fixture.generate()
        self.assertNotIn("A change in generated instructions.", instructions.read_text())
        self.fixture.generate(check=True)

    def test_unowned_root_instructions_are_preserved(self) -> None:
        instructions = self.fixture.root / "AGENTS.md"
        instructions.write_text("Existing user instructions.\n")
        with self.assertRaises(AdapterError) as caught:
            self.fixture.generate()
        self.assertEqual(caught.exception.details["unowned"], ["AGENTS.md"])
        self.assertEqual(instructions.read_text(), "Existing user instructions.\n")
        self.assertFalse((self.fixture.root / MANIFEST_PATH).exists())

    def test_engine_skill_changes_update_every_mirror(self) -> None:
        self.fixture.generate()
        source = self.fixture.root / ENGINE_ARTIFACTS_PATH / "skills/pipeline/SKILL.md"
        source.write_text(source.read_text() + "An updated orchestration procedure.\n")
        with self.assertRaises(AdapterError) as caught:
            self.fixture.generate(check=True)
        for surface in (".agents", ".claude"):
            self.assertIn(f"{surface}/skills/pipeline/SKILL.md", caught.exception.details["modified"])
        self.fixture.generate()
        for surface in (".agents", ".claude"):
            self.assertIn("An updated orchestration procedure.", (self.fixture.root / surface / "skills/pipeline/SKILL.md").read_text())
        self.fixture.generate(check=True)

    def test_workflow_cannot_override_an_engine_skill(self) -> None:
        duplicate = self.fixture.write_skill("pipeline")
        with self.assertRaises(AdapterError) as caught:
            self.fixture.generate()
        self.assertEqual(caught.exception.details["conflicting_sources"], ["skills/pipeline/SKILL.md"])
        self.assertTrue(duplicate.is_file())
        self.assertFalse((self.fixture.root / "AGENTS.md").exists())

    def test_shared_skill_drift_and_canonical_updates_are_checked(self) -> None:
        self.fixture.generate()
        shared = self.fixture.root / ".agents" / "skills" / "compose" / "SKILL.md"
        shared.write_text("user change\n", encoding="utf-8")
        with self.assertRaises(AdapterError) as caught:
            self.fixture.generate(check=True)
        self.assertIn(".agents/skills/compose/SKILL.md", caught.exception.details["modified"])
        self.assertEqual(shared.read_text(), "user change\n")
        self.fixture.generate()

        source = self.fixture.root / "skills" / "compose" / "SKILL.md"
        source.write_text(source.read_text() + "A new canonical procedure.\n")
        with self.assertRaises(AdapterError) as caught:
            self.fixture.generate(check=True)
        self.assertIn(".agents/skills/compose/SKILL.md", caught.exception.details["modified"])
        self.fixture.generate()
        self.assertIn("A new canonical procedure.", shared.read_text())
        self.fixture.generate(check=True)

    def test_unowned_shared_skill_is_preserved_before_any_generation(self) -> None:
        path = self.fixture.root / ".agents" / "skills" / "compose" / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text("user owned\n", encoding="utf-8")
        with self.assertRaises(AdapterError) as caught:
            self.fixture.generate()
        self.assertEqual(caught.exception.details["unowned"], [".agents/skills/compose/SKILL.md"])
        self.assertEqual(path.read_text(), "user owned\n")
        self.assertFalse((self.fixture.root / ".claude").exists())
        self.assertFalse((self.fixture.root / MANIFEST_PATH).exists())

    def test_modified_stale_shared_skill_is_preserved(self) -> None:
        source = self.fixture.write_skill("extra")
        self.fixture.generate()
        path = self.fixture.root / ".agents" / "skills" / "extra" / "SKILL.md"
        path.write_text("user change\n", encoding="utf-8")
        source.unlink()
        with self.assertRaises(AdapterError) as caught:
            self.fixture.generate()
        self.assertEqual(caught.exception.details["stale_modified"], [".agents/skills/extra/SKILL.md"])
        self.assertEqual(path.read_text(), "user change\n")
        self.assertTrue((self.fixture.root / ".claude/skills/extra/SKILL.md").is_file())

    def test_shared_skill_symlink_destination_is_rejected(self) -> None:
        path = self.fixture.root / ".agents" / "skills" / "compose" / "SKILL.md"
        path.parent.mkdir(parents=True)
        source = self.fixture.root / "skills" / "compose" / "SKILL.md"
        before = source.read_bytes()
        path.symlink_to(source)
        with self.assertRaises(AdapterError) as caught:
            self.fixture.generate()
        self.assertEqual(caught.exception.details["unsafe"], [{
            "path": ".agents/skills/compose/SKILL.md", "reason": "target-is-symlink",
        }])
        self.assertEqual(source.read_bytes(), before)

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
