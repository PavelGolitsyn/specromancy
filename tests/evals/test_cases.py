from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


CASES = Path(__file__).with_name("cases")
REQUIRED_CATEGORIES = {
    "approval-safety",
    "bounded-loop",
    "honest-blocking",
    "instruction-precedence",
    "missing-information",
    "scope-control",
    "validation-failure",
}
BOUNDARY_STATUSES = {
    "awaiting-approval",
    "blocked",
    "completed",
    "validation-failed",
}


class BehaviorEvalFixtureTests(unittest.TestCase):
    def test_cases_are_complete_unique_and_semantic(self) -> None:
        paths = sorted(CASES.glob("*.json"))
        self.assertGreaterEqual(len(paths), 7)
        identifiers: set[str] = set()
        categories: set[str] = set()
        for path in paths:
            value = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(path=path.name):
                self.assertEqual(
                    set(value),
                    {
                        "schema_version",
                        "id",
                        "category",
                        "initial_repository",
                        "request",
                        "expected_phase_sequence",
                        "expected_boundary",
                        "required_artifact_properties",
                    },
                )
                self.assertEqual(value["schema_version"], 1)
                self.assertRegex(value["id"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                self.assertNotIn(value["id"], identifiers)
                identifiers.add(value["id"])
                categories.add(value["category"])
                self.assertIsInstance(value["initial_repository"], dict)
                self.assertTrue(value["request"].strip())
                self.assertTrue(value["expected_phase_sequence"])
                self.assertTrue(
                    all(
                        isinstance(phase, str)
                        and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", phase)
                        for phase in value["expected_phase_sequence"]
                    )
                )
                self.assertIn(value["expected_boundary"]["status"], BOUNDARY_STATUSES)
                self.assertTrue(value["required_artifact_properties"])
                self.assertTrue(
                    all(
                        isinstance(item, str) and item.strip()
                        for item in value["required_artifact_properties"]
                    )
                )
        self.assertEqual(categories, REQUIRED_CATEGORIES)


if __name__ == "__main__":
    unittest.main()
