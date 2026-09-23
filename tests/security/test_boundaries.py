import json
from pathlib import Path
import tempfile
import unittest

from specromancy.commands import run_verification_command
from specromancy.errors import SafetyError, ValidationError
from specromancy.io import read_text
from specromancy.redaction import REDACTED, bounded_utf8, redact_text
from specromancy.security import (
    validate_canonical_skills,
    validate_documentation,
    validate_repository_file,
    validate_subprocess_argv,
)


SKILL = """---
name: demo
description: Use for demo validation.
---

# Demo

Read [policy](references/policy.md).
"""


class SecurityBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.root.joinpath(".specromancy/runs/run-1").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_repository_file_rejects_traversal_and_symlink_escape(self) -> None:
        outside = self.root.parent / "outside-security.txt"
        outside.write_text("outside", encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        with self.assertRaises(SafetyError):
            validate_repository_file(self.root, "../outside-security.txt")
        link = self.root / "escape.txt"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(SafetyError):
            validate_repository_file(self.root, "escape.txt")

    def test_shell_metacharacters_are_literal_argv_and_nul_is_rejected(self) -> None:
        argv = validate_subprocess_argv(["python3", "-c", "print('; rm -rf literal')"])
        self.assertIn("; rm -rf literal", argv[-1])
        with self.assertRaises(Exception):
            validate_subprocess_argv(["python3", "bad\x00argument"])

    def test_verification_never_invokes_a_shell(self) -> None:
        marker = self.root / "must-not-exist"
        record = run_verification_command(
            self.root,
            "run-1",
            ["python3", "-c", "import sys; print(sys.argv[1])", f"; touch {marker}"],
        )
        self.assertEqual(record.exit_code, 0)
        self.assertFalse(marker.exists())

    def test_redacts_assignments_tokens_headers_and_private_keys(self) -> None:
        private = "-----BEGIN PRIVATE KEY-----\nmaterial\n-----END PRIVATE KEY-----"
        value = "password=hunter2 Authorization: Bearer abcdef ghp_abcdefghijklmnop " + private
        redacted = redact_text(value)
        self.assertNotIn("hunter2", redacted)
        self.assertNotIn("abcdefghijklmnop", redacted)
        self.assertNotIn("material", redacted)
        self.assertGreaterEqual(redacted.count(REDACTED), 3)

    def test_bounded_utf8_and_managed_read_cap(self) -> None:
        bounded, truncated = bounded_utf8("é" * 1000, 256)
        self.assertTrue(truncated)
        self.assertLessEqual(len(bounded.encode("utf-8")), 256)
        target = self.root / "large.txt"
        target.write_text("x" * 20, encoding="utf-8")
        with self.assertRaises(ValidationError) as caught:
            read_text(target, max_bytes=10)
        self.assertEqual(caught.exception.details["limit_bytes"], 10)

    def test_skill_reference_escape_missing_and_cycle_are_rejected(self) -> None:
        skill_dir = self.root / ".agents/skills/demo"
        references = skill_dir / "references"
        references.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(SKILL, encoding="utf-8")
        policy = references / "policy.md"
        policy.write_text("[loop](../SKILL.md)\n", encoding="utf-8")
        with self.assertRaises(ValidationError) as cycle:
            validate_canonical_skills(self.root, ("demo",))
        self.assertIn("cyclic", cycle.exception.message)
        policy.write_text("[escape](../../../outside.md)\n", encoding="utf-8")
        with self.assertRaises(SafetyError):
            validate_canonical_skills(self.root, ("demo",))
        policy.write_text("[missing](missing.md)\n", encoding="utf-8")
        with self.assertRaises(ValidationError) as missing:
            validate_canonical_skills(self.root, ("demo",))
        self.assertIn("missing", missing.exception.message)

    def test_deep_skill_reference_chain_is_rejected(self) -> None:
        skill_dir = self.root / ".agents/skills/demo"
        references = skill_dir / "references"
        references.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(SKILL, encoding="utf-8")
        (references / "policy.md").write_text("[a](a.md)\n", encoding="utf-8")
        (references / "a.md").write_text("[b](b.md)\n", encoding="utf-8")
        (references / "b.md").write_text("[c](c.md)\n", encoding="utf-8")
        (references / "c.md").write_text("[d](d.md)\n", encoding="utf-8")
        (references / "d.md").write_text("end\n", encoding="utf-8")
        with self.assertRaises(ValidationError) as caught:
            validate_canonical_skills(self.root, ("demo",))
        self.assertIn("depth", caught.exception.message)

    def test_documentation_links_and_example_commands_are_checked(self) -> None:
        docs = self.root / "docs"
        docs.mkdir()
        readme = self.root / "README.md"
        readme.write_text("[missing](docs/missing.md)\n", encoding="utf-8")
        with self.assertRaises(ValidationError) as missing:
            validate_documentation(self.root)
        self.assertIn("link target", missing.exception.message)
        (docs / "guide.md").write_text("guide\n", encoding="utf-8")
        readme.write_text("[guide](docs/guide.md)\n\n```bash\nspecromancy explode\n```\n", encoding="utf-8")
        with self.assertRaises(ValidationError) as command:
            validate_documentation(self.root)
        self.assertEqual(command.exception.details["command"], "explode")

    def test_command_record_contains_redacted_bounded_output(self) -> None:
        record = run_verification_command(
            self.root,
            "run-1",
            ["python3", "-c", "print('pass' + 'word=' + 'topsecret'); print('x' * 1000)"],
            output_limit=256,
        )
        output = (self.root / record.stdout_path).read_text(encoding="utf-8")
        payload = json.loads((self.root / record.record_path).read_text(encoding="utf-8"))
        self.assertNotIn("topsecret", output)
        self.assertIn(REDACTED, output)
        self.assertTrue(payload["stdout_truncated"])


if __name__ == "__main__":
    unittest.main()
