"""Cached access to the packaged Stage 0 contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any, Final

from .errors import ValidationError


CONTRACT_PACKAGE: Final = "specromancy.resources.contracts"
CONTRACT_NAMES: Final = (
    "artifact.schema.json",
    "evaluation-case.schema.json",
    "evaluation-result.schema.json",
    "exit-codes.json",
    "pipeline.json",
    "run.schema.json",
)


@dataclass(frozen=True)
class ContractVersions:
    pipeline: str
    schema: str


def _contract_resource(name: str):
    if name not in CONTRACT_NAMES:
        raise ValidationError(
            "Unknown packaged contract.", details={"contract": name}
        )
    return resources.files(CONTRACT_PACKAGE).joinpath(name)


@lru_cache(maxsize=None)
def load_contract(name: str) -> dict[str, Any]:
    """Load one immutable-by-convention JSON contract from package resources."""

    resource = _contract_resource(name)
    try:
        with resource.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(
            "A packaged contract is unreadable or malformed.",
            details={"contract": name},
        ) from exc
    if not isinstance(value, dict):
        raise ValidationError(
            "A packaged contract must contain a JSON object.",
            details={"contract": name},
        )
    return value


def _schema_version(schema: dict[str, Any], property_name: str) -> str:
    try:
        value = schema["properties"][property_name]["const"]
    except (KeyError, TypeError) as exc:
        raise ValidationError("A packaged schema does not declare its version.") from exc
    if not isinstance(value, str) or not value:
        raise ValidationError("A packaged schema has an invalid version.")
    return value


@lru_cache(maxsize=1)
def validate_contracts() -> ContractVersions:
    """Perform startup checks that do not require a third-party JSON Schema engine."""

    pipeline = load_contract("pipeline.json")
    exits = load_contract("exit-codes.json")
    run_schema = load_contract("run.schema.json")
    artifact_schema = load_contract("artifact.schema.json")
    evaluation_case_schema = load_contract("evaluation-case.schema.json")
    evaluation_result_schema = load_contract("evaluation-result.schema.json")

    pipeline_version = pipeline.get("contract_version")
    if not isinstance(pipeline_version, str) or not pipeline_version:
        raise ValidationError("The pipeline contract does not declare a version.")
    if exits.get("contract_version") != pipeline_version:
        raise ValidationError("The exit-code and pipeline contract versions differ.")

    run_version = _schema_version(run_schema, "schema_version")
    artifact_version = _schema_version(artifact_schema, "schema-version")
    if run_version != artifact_version or run_version != pipeline_version:
        raise ValidationError("The packaged pipeline and schema versions differ.")
    for evaluation_schema in (evaluation_case_schema, evaluation_result_schema):
        if _schema_version(evaluation_schema, "schema_version") != pipeline_version:
            raise ValidationError("The packaged evaluation and pipeline versions differ.")

    statuses = pipeline.get("statuses")
    phases = pipeline.get("phases")
    validators = pipeline.get("validators")
    transitions = pipeline.get("transitions")
    if (
        not isinstance(statuses, list)
        or not all(isinstance(status, str) for status in statuses)
        or len(statuses) != len(set(statuses))
    ):
        raise ValidationError("Pipeline statuses must be a unique list.")
    if (
        not isinstance(phases, list)
        or not all(isinstance(phase, str) for phase in phases)
        or len(phases) != len(set(phases))
    ):
        raise ValidationError("Pipeline phases must be a unique list.")
    if not isinstance(validators, dict) or not isinstance(transitions, list):
        raise ValidationError("The pipeline validators or transitions are malformed.")
    for transition in transitions:
        if not isinstance(transition, dict):
            raise ValidationError("A pipeline transition is not an object.")
        sources = (
            [transition["from"]]
            if "from" in transition
            else transition.get("allowed_from")
        )
        if (
            not isinstance(sources, list)
            or not sources
            or any(source not in statuses for source in sources)
            or transition.get("to") not in statuses
        ):
            raise ValidationError("A pipeline transition names an unknown status.")
        if transition.get("phase") not in phases:
            raise ValidationError("A pipeline transition names an unknown phase.")
        if transition.get("validator") not in validators:
            raise ValidationError("A pipeline transition names an unknown validator.")

    exit_rows = exits.get("exit_codes")
    if not isinstance(exit_rows, list):
        raise ValidationError("The exit-code contract is malformed.")
    codes = [row.get("code") for row in exit_rows if isinstance(row, dict)]
    if len(codes) != len(exit_rows) or len(codes) != len(set(codes)):
        raise ValidationError("Contract exit codes must be unique.")
    envelope = exits.get("json_envelope", {})
    required = envelope.get("required") if isinstance(envelope, dict) else None
    if set(required or ()) != {"ok", "command", "message", "data", "errors"}:
        raise ValidationError("The JSON envelope contract is incomplete.")

    return ContractVersions(pipeline=pipeline_version, schema=run_version)


def pipeline_contract() -> dict[str, Any]:
    return load_contract("pipeline.json")


def run_schema() -> dict[str, Any]:
    return load_contract("run.schema.json")


def artifact_schema() -> dict[str, Any]:
    return load_contract("artifact.schema.json")


def exit_code_contract() -> dict[str, Any]:
    return load_contract("exit-codes.json")


def evaluation_case_schema() -> dict[str, Any]:
    return load_contract("evaluation-case.schema.json")


def evaluation_result_schema() -> dict[str, Any]:
    return load_contract("evaluation-result.schema.json")
