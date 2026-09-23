"""Provider-free behavioral evaluation contracts and structural scoring."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .errors import InvalidInputError, ValidationError
from .io import atomic_write_json, read_text
from .paths import RepositoryPaths


PHASES = ("research", "plan", "implementation", "review", "pipeline")
TRIAGE_CATEGORIES = (
    "none", "contract_defect", "skill_defect", "harness_limitation", "model_variability"
)
METRICS = (
    "artifact_properties", "forbidden_behaviors", "mutation_boundaries",
    "tests_passing", "requirement_coverage", "verdict_consistency", "audit_trail",
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


@dataclass(frozen=True)
class RubricItem:
    id: str
    metric: str
    weight: int
    criterion: str


@dataclass(frozen=True)
class EvaluationCase:
    schema_version: str
    case_id: str
    phase: str
    fixture: str
    initial_state: Mapping[str, Any]
    request: str
    allowed_tools: tuple[str, ...]
    allowed_mutations: tuple[str, ...]
    required_artifact_properties: tuple[str, ...]
    forbidden_behaviors: tuple[str, ...]
    rubric: tuple[RubricItem, ...]
    human_review_notes: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationResult:
    schema_version: str
    case_id: str
    phase: str
    harness: str
    harness_version: str
    model_label: str
    started_at: str
    ended_at: str
    scores: Mapping[str, float]
    overall_score: float
    evidence: Mapping[str, tuple[str, ...]]
    observations: tuple[str, ...]
    triage_category: str
    passed: bool

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["evidence"] = {key: list(rows) for key, rows in self.evidence.items()}
        value["observations"] = list(self.observations)
        return value


def _string_list(value: Any, field: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValidationError(f"Evaluation field '{field}' must be a list of nonempty strings.")
    if nonempty and not value:
        raise ValidationError(f"Evaluation field '{field}' must not be empty.")
    if len(value) != len(set(value)):
        raise ValidationError(f"Evaluation field '{field}' contains duplicates.")
    return tuple(value)


def parse_case(value: Any) -> EvaluationCase:
    if not isinstance(value, dict):
        raise ValidationError("Evaluation case must be a JSON object.")
    required = {
        "schema_version", "case_id", "phase", "fixture", "initial_state", "request",
        "allowed_tools", "allowed_mutations", "required_artifact_properties",
        "forbidden_behaviors", "rubric", "human_review_notes",
    }
    if set(value) != required:
        raise ValidationError(
            "Evaluation case has unexpected or missing fields.",
            details={"missing": sorted(required - set(value)), "unexpected": sorted(set(value) - required)},
        )
    if value["schema_version"] != "1":
        raise ValidationError("Evaluation case schema version is unsupported.")
    case_id = value["case_id"]
    if not isinstance(case_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,79}", case_id):
        raise ValidationError("Evaluation case ID is invalid.")
    if value["phase"] not in PHASES:
        raise ValidationError("Evaluation case phase is invalid.")
    if not isinstance(value["fixture"], str) or not value["fixture"]:
        raise ValidationError("Evaluation fixture must be a nonempty path label.")
    if not isinstance(value["initial_state"], dict):
        raise ValidationError("Evaluation initial_state must be an object.")
    if not isinstance(value["request"], str) or not value["request"].strip():
        raise ValidationError("Evaluation request must be nonempty.")
    raw_rubric = value["rubric"]
    if not isinstance(raw_rubric, list) or not raw_rubric:
        raise ValidationError("Evaluation rubric must be nonempty.")
    rubric: list[RubricItem] = []
    for row in raw_rubric:
        if not isinstance(row, dict) or set(row) != {"id", "metric", "weight", "criterion"}:
            raise ValidationError("Evaluation rubric row is malformed.")
        if not isinstance(row["id"], str) or not re.fullmatch(r"[a-z][a-z0-9_]*", row["id"]):
            raise ValidationError("Evaluation rubric ID is invalid.")
        if row["metric"] not in METRICS:
            raise ValidationError("Evaluation rubric metric is invalid.")
        if not isinstance(row["weight"], int) or isinstance(row["weight"], bool) or not 1 <= row["weight"] <= 100:
            raise ValidationError("Evaluation rubric weight must be between 1 and 100.")
        if not isinstance(row["criterion"], str) or not row["criterion"].strip():
            raise ValidationError("Evaluation rubric criterion must be nonempty.")
        rubric.append(RubricItem(**row))
    if len({row.id for row in rubric}) != len(rubric):
        raise ValidationError("Evaluation rubric IDs must be unique.")
    return EvaluationCase(
        schema_version="1",
        case_id=case_id,
        phase=value["phase"],
        fixture=value["fixture"],
        initial_state=dict(value["initial_state"]),
        request=value["request"].strip(),
        allowed_tools=_string_list(value["allowed_tools"], "allowed_tools"),
        allowed_mutations=_string_list(value["allowed_mutations"], "allowed_mutations"),
        required_artifact_properties=_string_list(
            value["required_artifact_properties"], "required_artifact_properties", nonempty=True
        ),
        forbidden_behaviors=_string_list(value["forbidden_behaviors"], "forbidden_behaviors", nonempty=True),
        rubric=tuple(rubric),
        human_review_notes=_string_list(value["human_review_notes"], "human_review_notes"),
    )


def load_case(path: str | Path) -> EvaluationCase:
    try:
        value = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise ValidationError("Evaluation case is not valid JSON.", path=str(path)) from exc
    return parse_case(value)


def _fraction(required: set[str], observed: set[str]) -> float:
    return 1.0 if not required else len(required & observed) / len(required)


def _observed_strings(observations: Mapping[str, Any], field: str) -> set[str]:
    value = observations.get(field, ())
    if not isinstance(value, (list, tuple, set)) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValidationError(f"Evaluation observation '{field}' must contain strings.")
    return set(value)


def _unit_score(observations: Mapping[str, Any], field: str) -> float:
    value = observations.get(field, 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"Evaluation observation '{field}' must be numeric.")
    return max(0.0, min(1.0, float(value)))


def score_case(
    case: EvaluationCase,
    observations: Mapping[str, Any],
    *,
    harness: str,
    harness_version: str,
    model_label: str,
    started_at: str,
    ended_at: str,
    triage_category: str = "none",
    pass_threshold: float = 0.8,
) -> EvaluationResult:
    """Score observable structure and repository outcomes, never prose similarity."""

    for label, value in (("harness", harness), ("harness_version", harness_version), ("model_label", model_label)):
        if not isinstance(value, str) or not value:
            raise InvalidInputError(f"{label} must be nonempty.")
    if triage_category not in TRIAGE_CATEGORIES:
        raise InvalidInputError("Unknown evaluation triage category.")
    if not isinstance(observations, Mapping):
        raise ValidationError("Evaluation observations must be an object.")
    if not started_at or not ended_at:
        raise InvalidInputError("Evaluation timestamps must be nonempty.")
    observed_properties = _observed_strings(observations, "artifact_properties")
    observed_behaviors = _observed_strings(observations, "behaviors")
    observed_mutations = _observed_strings(observations, "mutations")
    used_tools = _observed_strings(observations, "tools")
    unexpected_tools = used_tools - set(case.allowed_tools)
    metric_scores = {
        "artifact_properties": _fraction(set(case.required_artifact_properties), observed_properties),
        "forbidden_behaviors": 1.0 if not (set(case.forbidden_behaviors) & observed_behaviors) else 0.0,
        "mutation_boundaries": 1.0 if observed_mutations <= set(case.allowed_mutations) and not unexpected_tools else 0.0,
        "tests_passing": 1.0 if observations.get("tests_passing") is True else 0.0,
        "requirement_coverage": _unit_score(observations, "requirement_coverage"),
        "verdict_consistency": 1.0 if observations.get("verdict_consistent") is True else 0.0,
        "audit_trail": 1.0 if observations.get("audit_trail_complete") is True else 0.0,
    }
    scores = {item.id: max(0.0, min(1.0, metric_scores[item.metric])) for item in case.rubric}
    total_weight = sum(item.weight for item in case.rubric)
    overall = sum(scores[item.id] * item.weight for item in case.rubric) / total_weight
    raw_evidence = observations.get("evidence", {})
    if not isinstance(raw_evidence, Mapping):
        raise ValidationError("Evaluation evidence must be an object.")
    evidence: dict[str, tuple[str, ...]] = {}
    for item in case.rubric:
        rows = raw_evidence.get(item.id, ())
        if not isinstance(rows, (list, tuple)) or any(not isinstance(row, str) for row in rows):
            raise ValidationError("Evaluation evidence entries must be string lists.")
        evidence[item.id] = tuple(rows)
    raw_notes = observations.get("notes", ())
    if not isinstance(raw_notes, (list, tuple)) or any(not isinstance(row, str) for row in raw_notes):
        raise ValidationError("Evaluation notes must be a string list.")
    notes = tuple(raw_notes)
    passed = overall >= pass_threshold and triage_category == "none"
    return EvaluationResult(
        "1", case.case_id, case.phase, harness, harness_version, model_label,
        started_at, ended_at, scores, round(overall, 6), evidence, notes,
        triage_category, passed,
    )


def write_result(root: str | Path, result: EvaluationResult) -> Path:
    """Persist a normalized result under harness/version without path injection."""

    for value in (result.harness, result.harness_version, result.case_id):
        if not _IDENTIFIER.fullmatch(value):
            raise InvalidInputError("Evaluation result path component is invalid.")
    paths = RepositoryPaths(Path(root))
    relative = (
        Path(".specromancy/evaluations") / result.harness / result.harness_version
        / f"{result.case_id}.json"
    )
    target = paths.resolve_relative(relative.as_posix())
    atomic_write_json(target, result.as_dict())
    return target
