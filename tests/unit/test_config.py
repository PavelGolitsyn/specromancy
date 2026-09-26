from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from specromancy.config import (
    DEFAULT_PIPELINE_PATH,
    PipelineConfigError,
    load_pipeline,
    require_pipeline_hash,
)
from specromancy.exit_codes import ExitCode


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


PHASE = """
[[phases]]
id = "compose"
skill = "compose"
inputs = ["request"]
output_name = "{visit:03}-result.md"
mutation = "read-only"
completion_criteria = ["Write the result."]
validator = "file"
approval_conditions = []
stop_conditions = []
max_visits = 1

[[phases.transitions]]
outcome = "done"
"""


def document(phase: str = PHASE, **changes: str) -> str:
    values = {
        "schema_version": "1",
        "id": '"fixture"',
        "version": "1",
        "start": '"compose"',
        "terminal_outcomes": '["done"]',
        "artifact_pattern": '"artifacts/{visit:03}-{phase}.md"',
    }
    values.update(changes)
    return textwrap.dedent(
        f"""
        schema_version = {values['schema_version']}
        id = {values['id']}
        version = {values['version']}
        start = {values['start']}
        terminal_outcomes = {values['terminal_outcomes']}
        artifact_pattern = {values['artifact_pattern']}
        {phase}
        """
    )


class PipelineFixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".git").mkdir()
        skill = self.root / ".agents" / "skills" / "compose" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nname: compose\ndescription: Test.\n---\n", encoding="utf-8")
        templates = self.root / "config" / "templates"
        templates.mkdir(parents=True)
        (templates / "result.md").write_text("# Result\n", encoding="utf-8")
        self.path = self.root / "config" / "pipeline.toml"

    def close(self) -> None:
        self.temporary.cleanup()

    def write(self, content: str, name: str = "pipeline.toml") -> Path:
        path = self.path.with_name(name)
        path.write_text(content, encoding="utf-8")
        return path


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = PipelineFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def assert_error(self, content: str, diagnostic: str) -> PipelineConfigError:
        path = self.fixture.write(content)
        with self.assertRaises(PipelineConfigError) as raised:
            load_pipeline(path)
        error = raised.exception
        self.assertEqual(error.code, ExitCode.INVALID_PIPELINE)
        self.assertEqual(error.details["error_code"], diagnostic)
        self.assertEqual(error.details["path"], str(path.resolve()))
        self.assertIn("remediation", error.details)
        return error

    def test_default_pipeline_loads_as_immutable_domain_objects(self) -> None:
        pipeline = load_pipeline(DEFAULT_PIPELINE_PATH)
        self.assertEqual(pipeline.start, "research")
        self.assertEqual(pipeline.phase_ids, ("research", "plan", "implement", "review"))
        self.assertRegex(pipeline.config_hash, r"^[0-9a-f]{64}$")
        self.assertTrue(pipeline.phase("research").skill_path.is_file())
        with self.assertRaises(FrozenInstanceError):
            pipeline.version = 2  # type: ignore[misc]

    def test_table_driven_valid_fixtures_include_unrelated_phase_names(self) -> None:
        for name, expected in (
            ("config-valid-minimal", ("compose",)),
            ("config-valid-branch", ("inspect", "transform", "verify")),
            ("config-valid-loop", ("transform", "verify")),
        ):
            with self.subTest(name=name):
                loaded = load_pipeline(FIXTURES / name / "pipeline.toml")
                self.assertEqual(loaded.phase_ids, expected)

    def test_duplicate_phase_is_rejected(self) -> None:
        duplicate = PHASE + PHASE.replace('id = "compose"', 'id = "compose"')
        self.assert_error(document(duplicate), "duplicate-phase")

    def test_missing_start_is_rejected(self) -> None:
        self.assert_error(document(start='"missing"'), "missing-start-phase")

    def test_unreachable_phase_is_rejected(self) -> None:
        orphan = PHASE.replace('id = "compose"', 'id = "orphan"').replace(
            'skill = "compose"', 'skill = "compose"'
        )
        self.assert_error(document(PHASE + orphan), "unreachable-phase")

    def test_unknown_transition_target_is_rejected(self) -> None:
        phase = PHASE.replace('outcome = "done"', 'outcome = "next"\ntarget = "missing"')
        self.assert_error(document(phase), "unknown-transition-target")

    def test_duplicate_outcome_is_rejected(self) -> None:
        phase = PHASE + '\n[[phases.transitions]]\noutcome = "done"\n'
        self.assert_error(document(phase), "duplicate-outcome")

    def test_unbounded_cycle_is_rejected(self) -> None:
        cyclic = PHASE.replace('outcome = "done"', 'outcome = "again"\ntarget = "compose"')
        cyclic = cyclic.replace("max_visits = 1\n", "")
        self.assert_error(document(cyclic), "unbounded-cycle")

    def test_parallel_unbounded_edge_does_not_borrow_another_outcomes_bound(self) -> None:
        cyclic = PHASE.replace(
            'outcome = "done"',
            'outcome = "bounded"\ntarget = "compose"\nmax_traversals = 1'
            '\n[[phases.transitions]]\noutcome = "unbounded"\ntarget = "compose"',
        ).replace("max_visits = 1\n", "")
        self.assert_error(document(cyclic), "unbounded-cycle")

    def test_bounds_must_be_positive(self) -> None:
        changed = PHASE.replace("max_visits = 1", "max_visits = 0")
        self.assert_error(document(changed), "invalid-bound")

    def test_reserved_phase_id_is_rejected(self) -> None:
        phase = PHASE.replace('id = "compose"', 'id = "status"')
        self.assert_error(document(phase, start='"status"'), "reserved-phase-id")

    def test_invalid_mutation_policy_is_rejected(self) -> None:
        phase = PHASE.replace('mutation = "read-only"', 'mutation = "sometimes"')
        self.assert_error(document(phase), "invalid-mutation-policy")

    def test_approval_required_is_optional_boolean_and_affects_provenance(self) -> None:
        omitted = load_pipeline(self.fixture.write(document(), "omitted.toml"))
        explicit_false = load_pipeline(
            self.fixture.write(
                document(
                    PHASE.replace(
                        "approval_conditions = []",
                        "approval_required = false\napproval_conditions = []",
                    )
                ),
                "false.toml",
            )
        )
        required = load_pipeline(
            self.fixture.write(
                document(
                    PHASE.replace(
                        "approval_conditions = []",
                        "approval_required = true\napproval_conditions = []",
                    )
                ),
                "required.toml",
            )
        )
        self.assertFalse(omitted.phase("compose").approval_required)
        self.assertFalse(explicit_false.phase("compose").approval_required)
        self.assertTrue(required.phase("compose").approval_required)
        self.assertEqual(omitted.config_hash, explicit_false.config_hash)
        self.assertNotEqual(omitted.config_hash, required.config_hash)

        invalid = PHASE.replace(
            "approval_conditions = []",
            'approval_required = "yes"\napproval_conditions = []',
        )
        self.assert_error(document(invalid), "invalid-field-type")

    def test_non_finite_command_timeout_is_rejected(self) -> None:
        phase = PHASE.replace(
            "[[phases.transitions]]",
            '[[phases.commands]]\nargv = ["check"]\n'
            "timeout_seconds = nan\n\n[[phases.transitions]]",
        )
        self.assert_error(document(phase), "invalid-command-timeout")

    def test_allowlist_policy_requires_patterns(self) -> None:
        phase = PHASE.replace('mutation = "read-only"', 'mutation = "allowlist"')
        self.assert_error(document(phase), "empty-field")

    def test_missing_skill_and_template_are_rejected(self) -> None:
        self.assert_error(
            document(PHASE.replace('skill = "compose"', 'skill = "missing"')),
            "missing-file",
        )
        phase = PHASE.replace(
            'output_name = "{visit:03}-result.md"',
            'output_name = "{visit:03}-result.md"\noutput_template = "templates/missing.md"',
        )
        self.assert_error(document(phase), "missing-file")

    def test_unsafe_template_and_output_paths_are_rejected(self) -> None:
        (self.fixture.root / "outside.md").write_text("# Safe parent\n", encoding="utf-8")
        phase = PHASE.replace(
            'output_name = "{visit:03}-result.md"',
            'output_name = "{visit:03}-result.md"\noutput_template = "../../../outside.md"',
        )
        self.assert_error(document(phase), "unsafe-path")
        unsafe_output = PHASE.replace(
            'output_name = "{visit:03}-result.md"', 'output_name = "../result.md"'
        )
        self.assert_error(
            document(unsafe_output),
            "unsafe-output-path",
        )

    def test_template_parent_segments_may_stay_inside_repository(self) -> None:
        template = self.fixture.root / "shared.md"
        template.write_text("# Shared\n", encoding="utf-8")
        phase = PHASE.replace(
            'output_name = "{visit:03}-result.md"',
            'output_name = "{visit:03}-result.md"\noutput_template = "../shared.md"',
        )
        loaded = load_pipeline(self.fixture.write(document(phase)))
        self.assertEqual(loaded.phase("compose").output_template_path, template.resolve())

    def test_template_symlink_cannot_escape_repository(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "target.md"
            target.write_text("# Outside\n", encoding="utf-8")
            link = self.fixture.root / "config" / "templates" / "link.md"
            link.symlink_to(target)
            phase = PHASE.replace(
                'output_name = "{visit:03}-result.md"',
                'output_name = "{visit:03}-result.md"\n'
                'output_template = "templates/link.md"',
            )
            self.assert_error(document(phase), "unsafe-path")

    def test_input_must_have_a_possible_producer(self) -> None:
        phase = PHASE.replace('inputs = ["request"]', 'inputs = ["latest:compose"]')
        self.assert_error(document(phase), "unavailable-input")

    def test_input_producer_must_dominate_all_incoming_routes(self) -> None:
        phase = textwrap.dedent(
            """
            [[phases]]
            id = "compose"
            skill = "compose"
            inputs = ["request"]
            output_name = "compose.md"
            mutation = "read-only"
            completion_criteria = ["Choose a route."]
            validator = "file"
            approval_conditions = []
            stop_conditions = []
            max_visits = 1
            [[phases.transitions]]
            outcome = "direct"
            target = "consume"
            [[phases.transitions]]
            outcome = "indirect"
            target = "produce"

            [[phases]]
            id = "produce"
            skill = "compose"
            inputs = ["request"]
            output_name = "produce.md"
            mutation = "read-only"
            completion_criteria = ["Produce."]
            validator = "file"
            approval_conditions = []
            stop_conditions = []
            max_visits = 1
            [[phases.transitions]]
            outcome = "next"
            target = "consume"

            [[phases]]
            id = "consume"
            skill = "compose"
            inputs = ["latest:produce"]
            output_name = "consume.md"
            mutation = "read-only"
            completion_criteria = ["Consume."]
            validator = "file"
            approval_conditions = []
            stop_conditions = []
            max_visits = 1
            [[phases.transitions]]
            outcome = "done"
            """
        )
        self.assert_error(document(phase), "unavailable-input")

    def test_visit_input_must_be_available_before_consumer(self) -> None:
        phase = PHASE.replace('inputs = ["request"]', 'inputs = ["visit:1"]')
        self.assert_error(document(phase), "unavailable-input")

    def test_terminal_outcome_cannot_also_be_a_phase(self) -> None:
        phase = PHASE.replace('id = "compose"', 'id = "done"')
        self.assert_error(document(phase, start='"done"'), "terminal-outcome-phase")

    def test_diagnostic_serializes_without_traceback_data(self) -> None:
        error = self.assert_error(document(schema_version="2"), "unsupported-schema-version")
        payload = error.as_dict()
        self.assertEqual(payload["code"], ExitCode.INVALID_PIPELINE)
        json.dumps(payload)
        self.assertNotIn("traceback", payload)

    def test_hash_is_stable_across_toml_key_order(self) -> None:
        first = self.fixture.write(document(), "first.toml")
        reordered_phase = PHASE.replace(
            'id = "compose"\nskill = "compose"',
            'skill = "compose"\nid = "compose"',
        )
        reordered = self.fixture.write(
            textwrap.dedent(
                f"""
                artifact_pattern = "artifacts/{{visit:03}}-{{phase}}.md"
                terminal_outcomes = ["done"]
                start = "compose"
                version = 1
                id = "fixture"
                schema_version = 1
                {reordered_phase}
                """
            ),
            "second.toml",
        )
        self.assertEqual(load_pipeline(first).config_hash, load_pipeline(reordered).config_hash)

    def test_hash_changes_after_semantic_edit_and_drift_is_actionable(self) -> None:
        first = load_pipeline(self.fixture.write(document(), "first.toml"))
        changed_phase = PHASE.replace(
            "Write the result.", "Write a reviewed result."
        )
        changed = load_pipeline(
            self.fixture.write(document(changed_phase), "changed.toml")
        )
        self.assertNotEqual(first.config_hash, changed.config_hash)
        with self.assertRaises(PipelineConfigError) as raised:
            require_pipeline_hash(changed, first.config_hash)
        self.assertEqual(raised.exception.diagnostic_code, "pipeline-hash-mismatch")

    def test_declared_and_resolved_paths_are_retained(self) -> None:
        phase = PHASE.replace(
            'output_name = "{visit:03}-result.md"',
            'output_name = "{visit:03}-result.md"\noutput_template = "templates/result.md"',
        )
        loaded = load_pipeline(self.fixture.write(document(phase)))
        configured = loaded.phase("compose")
        self.assertEqual(configured.output_template, "templates/result.md")
        self.assertEqual(
            configured.output_template_path,
            (self.fixture.root / "config" / "templates" / "result.md").resolve(),
        )

    def test_unsupported_json_schema_keyword_is_rejected_at_load(self) -> None:
        schema = self.fixture.root / "config" / "result.schema.json"
        schema.write_text('{"type":"string","minLength":1}', encoding="utf-8")
        phase = PHASE.replace(
            'validator = "file"',
            'validator = { type = "json", schema = "result.schema.json" }',
        )
        self.assert_error(document(phase), "unsupported-json-schema")


if __name__ == "__main__":
    unittest.main()
