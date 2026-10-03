from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from specromancy.config import ValidatorConfig
from specromancy.validation import (
    SchemaDefinitionError,
    ValidationFailure,
    markdown_heading_counts,
    validate_artifact,
    validate_schema_definition,
)


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.run = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, content: str, name: str = "output.md") -> Path:
        path = self.run / name
        path.write_text(content, encoding="utf-8")
        return path

    def assert_failure(self, code: str, validator: ValidatorConfig) -> None:
        with self.assertRaises(ValidationFailure) as raised:
            validate_artifact(self.run, "output.md", validator)
        self.assertEqual(raised.exception.diagnostic_code, code)

    def test_missing_empty_and_unresolved_outputs_fail(self) -> None:
        validator = ValidatorConfig("file")
        self.assert_failure("missing-output", validator)
        self.write(" \n")
        self.assert_failure("empty-output", validator)
        self.write("{{ unresolved }}\n")
        self.assert_failure("unresolved-template-marker", ValidatorConfig("markdown"))

    def test_unchanged_template_fails(self) -> None:
        template = self.write("# Result\n", "template.md")
        self.write("# Result\n")
        with self.assertRaises(ValidationFailure) as raised:
            validate_artifact(
                self.run, "output.md", ValidatorConfig("markdown"), template_path=template
            )
        self.assertEqual(raised.exception.diagnostic_code, "unchanged-template")

    def test_markdown_headings_are_scanned_outside_fences(self) -> None:
        content = "# Report\n\n## Evidence\n\n```md\n## Evidence\n```\n"
        self.write(content)
        check = validate_artifact(
            self.run,
            "output.md",
            ValidatorConfig("markdown", ("Evidence",)),
        )
        self.assertEqual(check["headings"], {"Evidence": 1})
        self.assertEqual(markdown_heading_counts("Title\n=====\n"), {"Title": 1})

    def test_markdown_heading_occurrence_is_configurable(self) -> None:
        self.write("## Evidence\n\n## Evidence\n")
        self.assert_failure(
            "invalid-markdown-headings",
            ValidatorConfig(
                "markdown", ("Evidence",), heading_occurrence="exactly-once"
            ),
        )
        validate_artifact(
            self.run,
            "output.md",
            ValidatorConfig(
                "markdown", ("Evidence",), heading_occurrence="at-least-once"
            ),
        )

    def test_json_subset_accepts_and_rejects_values(self) -> None:
        schema = {
            "type": "object",
            "required": ["name", "tags"],
            "properties": {
                "name": {"type": "string", "pattern": "^[a-z]+$"},
                "tags": {"type": "array", "items": {"enum": ["safe", "fast"]}},
            },
            "additionalProperties": False,
        }
        validate_schema_definition(schema)
        validator = ValidatorConfig("json", json_schema=schema)
        self.write(json.dumps({"name": "demo", "tags": ["safe"]}))
        validate_artifact(self.run, "output.md", validator)
        self.write(json.dumps({"name": "Demo", "tags": ["unknown"], "extra": True}))
        self.assert_failure("json-schema-failed", validator)
        self.write("{")
        self.assert_failure("malformed-json", validator)

    def test_unsupported_schema_keyword_fails_definition(self) -> None:
        with self.assertRaises(SchemaDefinitionError):
            validate_schema_definition({"type": "string", "minLength": 1})


if __name__ == "__main__":
    unittest.main()
