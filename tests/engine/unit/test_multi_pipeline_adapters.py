from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from specromancy.adapters import AdapterError, generate_adapters, render_adapters
from specromancy._adapters.adapter_rendering import expected_manifest, render_sources
from specromancy._adapters.adapter_sources import capture_sources
from specromancy.cli import adapter_command_metadata
from specromancy.registry import load_registry
from tests.engine.support import MultiPipelineFixture


class MultiPipelineAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = MultiPipelineFixture()
        self.root = self.fixture.root

    def tearDown(self) -> None:
        self.fixture.close()

    def generate(self, *, check: bool = False) -> dict:
        registry = load_registry(self.root)
        phases = sorted({phase for graph in registry.load_all() for phase in graph.phase_ids})
        return generate_adapters(self.root, registry, adapter_command_metadata(phases), check=check)

    def snapshot(self) -> dict[str, bytes]:
        manifest = self.root / "adapters/manifest.json"
        entries = json.loads(manifest.read_text())["generated"]
        return {entry["path"]: (self.root / entry["path"]).read_bytes() for entry in entries} | {"adapters/manifest.json": manifest.read_bytes()}

    def test_registered_launch_skills_are_discoverable_and_do_not_hash_themselves(self) -> None:
        self.generate()
        first = self.snapshot()
        manifest = json.loads(first["adapters/manifest.json"])
        sources = manifest["canonical_source"]["inputs"]
        self.assertEqual(sum(item["kind"] == "validated-pipeline" for item in sources), 2)
        self.assertEqual(sum(item["kind"] == "pipeline-dependency" for item in sources), 1)
        self.assertFalse(any("skills/specromancy-" in item["path"] for item in sources))
        self.assertTrue(any(item["kind"] == "validated-registry" for item in sources))
        for pipeline_id in ("alpha", "beta"):
            relative = f".agents/skills/specromancy-{pipeline_id}/SKILL.md"
            text = first[relative].decode()
            self.assertIn(f"--pipeline {pipeline_id}", text)
            self.assertIn(".agents/skills/pipeline/SKILL.md", text)
            self.assertEqual(first[f".claude/skills/specromancy-{pipeline_id}/SKILL.md"], first[relative])
        native = {item["name"]: item for item in manifest["targets"] if item["mode"] == "native"}
        self.assertEqual(native["codex"]["discovery_paths"], native["hermes"]["discovery_paths"])
        self.assertEqual(len(native["codex"]["discovery_paths"]), 2)
        self.fixture.register("beta", "alpha")
        self.generate()
        self.assertEqual(self.snapshot(), first)
        self.generate(check=True)

    def test_render_and_hash_share_captured_bytes_after_sources_change(self) -> None:
        registry = load_registry(self.root)
        sources = capture_sources(self.root, registry, None)
        rendered = render_sources(sources)
        manifest = expected_manifest(sources, rendered)
        for relative in (
            "AGENTS.md", ".agents/skills/compose/SKILL.md",
            "workflow/templates/shared.md", "workflow/pipelines/beta.toml",
        ):
            path = self.root / relative
            path.write_bytes(path.read_bytes() + b"\n# A later source edit\n")
        self.assertEqual(render_sources(sources), rendered)
        self.assertEqual(expected_manifest(sources, rendered), manifest)
        fresh = capture_sources(self.root, registry, None)
        self.assertNotEqual(expected_manifest(fresh, render_sources(fresh)), manifest)

    def test_public_render_does_not_read_manifest_dependency_bytes(self) -> None:
        registry = load_registry(self.root)
        metadata = adapter_command_metadata(["compose", "inspect"])
        expected = render_adapters(self.root, registry, metadata)
        with patch("pathlib.Path.read_bytes", side_effect=AssertionError("manifest input read")):
            self.assertEqual(render_adapters(self.root, registry, metadata), expected)

    def test_renamed_registration_replaces_only_its_owned_launch_skills(self) -> None:
        self.generate()
        self.fixture.add_pipeline("renamed", "inspect")
        self.fixture.register("alpha", "renamed")
        result = self.generate()
        self.assertEqual(set(result["adapters"]["removed"]), {
            f"{directory}/specromancy-beta/SKILL.md"
            for directory in (".agents/skills", ".claude/skills")
        })
        for directory in (".agents/skills", ".claude/skills"):
            self.assertTrue((self.root / directory / "specromancy-renamed/SKILL.md").is_file())
        self.generate(check=True)

    def test_registration_add_and_remove_updates_only_owned_launch_skills(self) -> None:
        self.generate()
        self.fixture.add_pipeline("gamma", "compose")
        self.fixture.register("alpha", "beta", "gamma")
        self.generate()
        self.assertTrue((self.root / ".agents/skills/specromancy-gamma/SKILL.md").is_file())
        canonical = self.root / ".agents/skills/compose/SKILL.md"
        before = canonical.read_bytes()
        self.fixture.register("alpha")
        result = self.generate()
        self.assertEqual(set(result["adapters"]["removed"]), {
            f"{directory}/specromancy-{pipeline_id}/SKILL.md"
            for directory in (".agents/skills", ".claude/skills") for pipeline_id in ("beta", "gamma")
        })
        self.assertEqual(canonical.read_bytes(), before)
        self.generate(check=True)

    def test_source_changes_and_launch_skill_drift_are_read_only_in_check_mode(self) -> None:
        for relative in ("workflow/pipelines/beta.toml", "workflow/templates/shared.md", ".agents/skills/specromancy-alpha/SKILL.md"):
            with self.subTest(path=relative):
                self.generate()
                target = self.root / relative
                before = self.snapshot()
                source = target.read_bytes()
                changed_source = source.replace(b"\nversion = 1", b"\nversion = 2") if target.suffix == ".toml" else source + b"\nChanged content.\n"
                target.write_bytes(changed_source)
                changed = self.snapshot()
                with self.assertRaises(AdapterError):
                    self.generate(check=True)
                self.assertEqual(self.snapshot(), changed)
                target.write_bytes(source)
                self.assertEqual(self.snapshot(), before)

    def test_unowned_and_modified_stale_native_skills_are_preserved(self) -> None:
        native = self.root / ".agents/skills/specromancy-beta/SKILL.md"
        native.parent.mkdir(parents=True)
        native.write_text("User owned\n")
        with self.assertRaises(AdapterError) as caught:
            self.generate()
        self.assertIn(native.relative_to(self.root).as_posix(), caught.exception.details["unowned"])
        self.assertEqual(native.read_text(), "User owned\n")
        native.unlink()
        self.generate()
        native.write_text("User edited\n")
        self.fixture.register("alpha")
        manifest = (self.root / "adapters/manifest.json").read_bytes()
        with self.assertRaises(AdapterError) as caught:
            self.generate()
        self.assertIn(native.relative_to(self.root).as_posix(), caught.exception.details["stale_modified"])
        self.assertEqual(native.read_text(), "User edited\n")
        self.assertEqual((self.root / "adapters/manifest.json").read_bytes(), manifest)

    def test_manifest_cannot_claim_a_canonical_skill(self) -> None:
        self.generate()
        path = self.root / "adapters/manifest.json"
        manifest = json.loads(path.read_text())
        manifest["generated"][0]["path"] = ".agents/skills/compose/SKILL.md"
        path.write_text(json.dumps(manifest))
        with self.assertRaises(AdapterError):
            self.generate()
        self.assertTrue((self.root / ".agents/skills/compose/SKILL.md").is_file())

    def test_native_launch_skill_parent_symlink_is_rejected(self) -> None:
        skill = self.root / ".agents/skills/specromancy-alpha"
        skill.symlink_to(self.root / ".agents/skills/compose", target_is_directory=True)
        before = (self.root / ".agents/skills/compose/SKILL.md").read_bytes()
        with self.assertRaises(AdapterError):
            self.generate()
        self.assertEqual((self.root / ".agents/skills/compose/SKILL.md").read_bytes(), before)
