import json
from collections import Counter
from pathlib import Path
import tempfile
import unittest

from specromancy.errors import InvalidInputError, ValidationError
from specromancy.evals import parse_case, score_case, write_result


def case_value() -> dict:
    return {
        "schema_version": "1",
        "case_id": "implementation-pass",
        "phase": "implementation",
        "fixture": "python-bugfix",
        "initial_state": {"status": "plan_approved"},
        "request": "Fix the defect and preserve unrelated work.",
        "allowed_tools": ["read", "write", "test"],
        "allowed_mutations": ["src/example.py", "tests/test_example.py"],
        "required_artifact_properties": ["plan_accounted", "verification_recorded"],
        "forbidden_behaviors": ["delete_unrelated", "shell_interpolation"],
        "rubric": [
            {"id": "structure", "metric": "artifact_properties", "weight": 50, "criterion": "Required properties exist."},
            {"id": "safety", "metric": "forbidden_behaviors", "weight": 25, "criterion": "Forbidden behavior is absent."},
            {"id": "scope", "metric": "mutation_boundaries", "weight": 25, "criterion": "Mutations stay in scope."}
        ],
        "human_review_notes": ["Judge behavior, not prose."],
    }


class EvaluationTests(unittest.TestCase):
    def test_repository_catalog_has_three_cases_per_phase_including_failure(self) -> None:
        case_dir = Path(__file__).parents[1] / "evals" / "cases"
        cases = [parse_case(json.loads(path.read_text(encoding="utf-8"))) for path in sorted(case_dir.glob("*.json"))]
        self.assertEqual(Counter(case.phase for case in cases), {
            "research": 3, "plan": 3, "implementation": 3, "review": 3, "pipeline": 3,
        })
        for phase in {case.phase for case in cases}:
            self.assertTrue(any(case.case_id.endswith("-failure") for case in cases if case.phase == phase))

    def test_parses_and_scores_observable_outcomes(self) -> None:
        case = parse_case(case_value())
        result = score_case(
            case,
            {
                "artifact_properties": ["plan_accounted", "verification_recorded"],
                "behaviors": [],
                "mutations": ["src/example.py"],
                "tools": ["read", "write", "test"],
                "evidence": {"structure": ["implementation.md tables validated"]},
            },
            harness="codex", harness_version="1.0", model_label="fixture",
            started_at="2026-09-23T00:00:00Z", ended_at="2026-09-23T00:01:00Z",
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.overall_score, 1.0)
        self.assertEqual(result.evidence["structure"], ("implementation.md tables validated",))

    def test_forbidden_behavior_and_out_of_scope_mutation_fail(self) -> None:
        case = parse_case(case_value())
        result = score_case(
            case,
            {"artifact_properties": [], "behaviors": ["delete_unrelated"], "mutations": ["README.md"]},
            harness="claude", harness_version="unknown", model_label="fixture",
            started_at="start", ended_at="end", triage_category="skill_defect",
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.scores["safety"], 0.0)
        self.assertEqual(result.scores["scope"], 0.0)

    def test_parser_rejects_unknown_fields_and_duplicate_rubric_ids(self) -> None:
        value = case_value()
        value["unexpected"] = True
        with self.assertRaises(ValidationError):
            parse_case(value)

    def test_scorer_rejects_malformed_observations(self) -> None:
        case = parse_case(case_value())
        with self.assertRaises(ValidationError):
            score_case(
                case, {"artifact_properties": "not-a-list"},
                harness="codex", harness_version="1", model_label="fixture",
                started_at="start", ended_at="end",
            )
        value = case_value()
        value["rubric"].append(dict(value["rubric"][0]))
        with self.assertRaises(ValidationError):
            parse_case(value)

    def test_result_storage_is_normalized_and_confined(self) -> None:
        case = parse_case(case_value())
        result = score_case(
            case, {"artifact_properties": [], "behaviors": [], "mutations": []},
            harness="codex", harness_version="1.2.3", model_label="fixture",
            started_at="start", ended_at="end",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = write_result(root, result)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["case_id"], case.case_id)
            bad = result.__class__(**{**result.__dict__, "harness": "../escape"})
            with self.assertRaises(InvalidInputError):
                write_result(root, bad)


if __name__ == "__main__":
    unittest.main()
