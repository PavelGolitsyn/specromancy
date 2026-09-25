"""Load declarative pipelines into immutable, validated domain objects."""

from __future__ import annotations

import hashlib
import json
import math
import re
import string
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from .contracts import RESERVED_COMMANDS
from .errors import SpecromancyError
from .exit_codes import ExitCode
from .graph import validate_graph


IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SUPPORTED_SCHEMA_VERSION = 1
MUTATION_POLICIES = frozenset({"read-only", "repository-write", "allowlist"})
VALIDATOR_TYPES = frozenset({"markdown", "json", "file"})
DEFAULT_PIPELINE_PATH = Path(__file__).with_name("pipeline.toml")
_MISSING = object()


class PipelineConfigError(SpecromancyError):
    """An expected pipeline error with a stable diagnostic code."""

    def __init__(
        self,
        diagnostic_code: str,
        message: str,
        *,
        path: Path,
        phase: str | None = None,
        field: str | None = None,
        value: Any = _MISSING,
        remediation: str,
    ) -> None:
        details: dict[str, Any] = {
            "error_code": diagnostic_code,
            "path": str(path),
            "remediation": remediation,
        }
        if phase is not None:
            details["phase"] = phase
        if field is not None:
            details["field"] = field
        if value is not _MISSING:
            details["value"] = _json_value(value)
        super().__init__(ExitCode.INVALID_PIPELINE, message, details)
        self.diagnostic_code = diagnostic_code


@dataclass(frozen=True, slots=True)
class ValidationCommand:
    """A deterministic command invoked without a shell."""

    argv: tuple[str, ...]
    timeout_seconds: float = 300.0
    required: bool = True


@dataclass(frozen=True, slots=True)
class ValidatorConfig:
    """Rules for validating a phase's primary output."""

    type: str
    required_headings: tuple[str, ...] = ()
    declared_path: str | None = None
    resolved_path: Path | None = None
    heading_occurrence: str = "exactly-once"
    json_schema: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class TransitionConfig:
    outcome: str
    target: str | None = None
    max_traversals: int | None = None


@dataclass(frozen=True, slots=True)
class PhaseConfig:
    id: str
    skill: str
    skill_path: Path
    inputs: tuple[str, ...]
    output_name: str
    output_template: str | None
    output_template_path: Path | None
    mutation: str
    allowlist: tuple[str, ...]
    completion_criteria: tuple[str, ...]
    validator: ValidatorConfig
    commands: tuple[ValidationCommand, ...]
    approval_conditions: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    transitions: tuple[TransitionConfig, ...]
    max_visits: int | None = None

    @property
    def validation_commands(self) -> tuple[ValidationCommand, ...]:
        """Descriptive alias used by action-packet code in later stages."""

        return self.commands


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    schema_version: int
    id: str
    version: int
    start: str
    terminal_outcomes: tuple[str, ...]
    artifact_pattern: str
    allow_non_git: bool
    phases: tuple[PhaseConfig, ...]
    path: Path
    repository_root: Path
    canonical_json: str
    config_hash: str

    def phase(self, phase_id: str) -> PhaseConfig:
        """Return a configured phase by id."""

        for phase in self.phases:
            if phase.id == phase_id:
                return phase
        raise KeyError(phase_id)

    @property
    def phase_ids(self) -> tuple[str, ...]:
        return tuple(phase.id for phase in self.phases)

    @property
    def hash(self) -> str:
        """Compatibility-friendly shorthand for the canonical config hash."""

        return self.config_hash


def _json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return repr(value)


def _discover_root(path: Path) -> Path | None:
    for candidate in (path.parent, *path.parent.parents):
        if (candidate / ".git").exists():
            return candidate.resolve()
    return None


class _Loader:
    def __init__(self, path: Path, repository_root: Path) -> None:
        self.path = path
        self.repository_root = repository_root

    def fail(
        self,
        diagnostic_code: str,
        message: str,
        *,
        phase: str | None = None,
        field: str | None = None,
        value: Any = _MISSING,
        remediation: str,
    ) -> NoReturn:
        raise PipelineConfigError(
            diagnostic_code,
            message,
            path=self.path,
            phase=phase,
            field=field,
            value=value,
            remediation=remediation,
        )

    def require_mapping(
        self, value: Any, field: str, *, phase: str | None = None
    ) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            self.fail(
                "invalid-field-type",
                f"{field} must be a table",
                phase=phase,
                field=field,
                value=value,
                remediation="replace it with a TOML table",
            )
        return value

    def require_string(
        self, value: Any, field: str, *, phase: str | None = None
    ) -> str:
        if not isinstance(value, str) or not value.strip():
            self.fail(
                "invalid-field-type",
                f"{field} must be a non-empty string",
                phase=phase,
                field=field,
                value=value,
                remediation="provide a non-empty string",
            )
        return value

    def require_identifier(
        self, value: Any, field: str, *, phase: str | None = None
    ) -> str:
        identifier = self.require_string(value, field, phase=phase)
        if not IDENTIFIER_PATTERN.fullmatch(identifier):
            self.fail(
                "invalid-identifier",
                f"{field} has invalid identifier {identifier!r}",
                phase=phase,
                field=field,
                value=identifier,
                remediation="use lowercase words separated by single hyphens",
            )
        return identifier

    def require_integer(
        self,
        value: Any,
        field: str,
        *,
        phase: str | None = None,
        minimum: int | None = None,
    ) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            self.fail(
                "invalid-field-type",
                f"{field} must be an integer",
                phase=phase,
                field=field,
                value=value,
                remediation="provide an integer value",
            )
        if minimum is not None and value < minimum:
            self.fail(
                "invalid-bound",
                f"{field} must be at least {minimum}",
                phase=phase,
                field=field,
                value=value,
                remediation=f"set {field} to {minimum} or greater",
            )
        return value

    def string_list(
        self,
        value: Any,
        field: str,
        *,
        phase: str | None = None,
        allow_empty: bool = True,
        identifiers: bool = False,
    ) -> tuple[str, ...]:
        if not isinstance(value, list):
            self.fail(
                "invalid-field-type",
                f"{field} must be a list of strings",
                phase=phase,
                field=field,
                value=value,
                remediation="provide a TOML array of strings",
            )
        parsed: list[str] = []
        for item in value:
            parsed.append(
                self.require_identifier(item, field, phase=phase)
                if identifiers
                else self.require_string(item, field, phase=phase)
            )
        if not parsed and not allow_empty:
            self.fail(
                "empty-field",
                f"{field} must contain at least one value",
                phase=phase,
                field=field,
                value=[],
                remediation="add at least one entry",
            )
        if len(set(parsed)) != len(parsed):
            self.fail(
                "duplicate-value",
                f"{field} contains duplicate values",
                phase=phase,
                field=field,
                value=parsed,
                remediation="remove duplicate entries",
            )
        return tuple(parsed)

    def existing_path(
        self,
        declared: str,
        field: str,
        *,
        phase: str | None = None,
        base: Path | None = None,
    ) -> Path:
        if not _safe_declared_path(declared, allow_parent=True):
            self.fail(
                "unsafe-path",
                f"{field} must be a safe repository-relative path",
                phase=phase,
                field=field,
                value=declared,
                remediation="use a relative path that resolves inside the repository",
            )
        candidate = ((base or self.path.parent) / declared).resolve()
        if not candidate.is_relative_to(self.repository_root):
            self.fail(
                "unsafe-path",
                f"{field} resolves outside the repository",
                phase=phase,
                field=field,
                value=declared,
                remediation="choose a file inside the repository",
            )
        if not candidate.is_file():
            self.fail(
                "missing-file",
                f"referenced file does not exist: {declared}",
                phase=phase,
                field=field,
                value=declared,
                remediation="create the referenced file or correct the path",
            )
        return candidate

    def parse(self, raw: Mapping[str, Any]) -> PipelineConfig:
        allowed_top = {
            "schema_version",
            "id",
            "version",
            "start",
            "terminal_outcomes",
            "artifact_pattern",
            "allow_non_git",
            "phases",
        }
        self.check_unknown(raw, allowed_top)
        schema_version = self.require_integer(
            raw.get("schema_version"), "schema_version", minimum=1
        )
        if schema_version != SUPPORTED_SCHEMA_VERSION:
            self.fail(
                "unsupported-schema-version",
                f"schema_version {schema_version} is not supported",
                field="schema_version",
                value=schema_version,
                remediation=f"set schema_version to {SUPPORTED_SCHEMA_VERSION}",
            )
        pipeline_id = self.require_identifier(raw.get("id"), "id")
        version = self.require_integer(raw.get("version"), "version", minimum=1)
        start = self.require_identifier(raw.get("start"), "start")
        terminal_outcomes = self.string_list(
            raw.get("terminal_outcomes"),
            "terminal_outcomes",
            allow_empty=False,
            identifiers=True,
        )
        artifact_pattern = self.require_string(
            raw.get("artifact_pattern"), "artifact_pattern"
        )
        allow_non_git = raw.get("allow_non_git", False)
        if not isinstance(allow_non_git, bool):
            self.fail(
                "invalid-field-type",
                "allow_non_git must be a boolean",
                field="allow_non_git",
                value=allow_non_git,
                remediation="use true or false",
            )
        _validate_output_pattern(
            artifact_pattern, "artifact_pattern", self.fail, output_name="output.md"
        )
        raw_phases = raw.get("phases")
        if not isinstance(raw_phases, list) or not raw_phases:
            self.fail(
                "invalid-field-type",
                "phases must be a non-empty array of tables",
                field="phases",
                value=raw_phases,
                remediation="declare one or more [[phases]] tables",
            )
        phases = tuple(self.parse_phase(item) for item in raw_phases)
        for phase in phases:
            if phase.id in terminal_outcomes:
                self.fail(
                    "terminal-outcome-phase",
                    f"terminal outcome {phase.id!r} cannot also be a phase id",
                    phase=phase.id,
                    field="id",
                    value=phase.id,
                    remediation="rename the phase or terminal outcome",
                )
        validate_graph(phases, start, frozenset(terminal_outcomes), self.fail)
        canonical = _canonical_document(
            schema_version,
            pipeline_id,
            version,
            start,
            terminal_outcomes,
            artifact_pattern,
            allow_non_git,
            phases,
        )
        canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        config_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        return PipelineConfig(
            schema_version=schema_version,
            id=pipeline_id,
            version=version,
            start=start,
            terminal_outcomes=terminal_outcomes,
            artifact_pattern=artifact_pattern,
            allow_non_git=allow_non_git,
            phases=phases,
            path=self.path,
            repository_root=self.repository_root,
            canonical_json=canonical_json,
            config_hash=config_hash,
        )

    def check_unknown(
        self,
        raw: Mapping[str, Any],
        allowed: set[str],
        *,
        phase: str | None = None,
    ) -> None:
        unknown = sorted(set(raw) - allowed)
        if unknown:
            self.fail(
                "unknown-field",
                f"unknown configuration field: {unknown[0]}",
                phase=phase,
                field=unknown[0],
                value=raw[unknown[0]],
                remediation="remove the field or use a supported field name",
            )

    def parse_phase(self, value: Any) -> PhaseConfig:
        raw = self.require_mapping(value, "phases")
        phase_id = self.require_identifier(raw.get("id"), "id")
        allowed = {
            "id",
            "skill",
            "inputs",
            "output_name",
            "output_template",
            "mutation",
            "allowlist",
            "mutation_allowlist",
            "completion_criteria",
            "validator",
            "validator_path",
            "required_headings",
            "heading_occurrence",
            "commands",
            "validation_commands",
            "approval_conditions",
            "stop_conditions",
            "transitions",
            "max_visits",
        }
        self.check_unknown(raw, allowed, phase=phase_id)
        if phase_id in RESERVED_COMMANDS:
            self.fail(
                "reserved-phase-id",
                f"phase id {phase_id!r} shadows a reserved CLI command",
                phase=phase_id,
                field="id",
                value=phase_id,
                remediation="choose a phase id that is not a CLI command",
            )
        skill = self.require_identifier(raw.get("skill"), "skill", phase=phase_id)
        skill_path = self.existing_path(
            f".agents/skills/{skill}/SKILL.md",
            "skill",
            phase=phase_id,
            base=self.repository_root,
        )
        inputs = self.string_list(raw.get("inputs"), "inputs", phase=phase_id)
        _validate_inputs(inputs, phase_id, self.fail)
        output_name = self.require_string(
            raw.get("output_name"), "output_name", phase=phase_id
        )
        _validate_output_pattern(
            output_name, "output_name", self.fail, phase=phase_id
        )
        output_template_raw = raw.get("output_template")
        output_template: str | None = None
        output_template_path: Path | None = None
        if output_template_raw is not None:
            output_template = self.require_string(
                output_template_raw, "output_template", phase=phase_id
            )
            output_template_path = self.existing_path(
                output_template, "output_template", phase=phase_id
            )
        mutation = self.require_string(raw.get("mutation"), "mutation", phase=phase_id)
        if mutation not in MUTATION_POLICIES:
            self.fail(
                "invalid-mutation-policy",
                f"phase {phase_id!r} uses unsupported mutation policy {mutation!r}",
                phase=phase_id,
                field="mutation",
                value=mutation,
                remediation=f"choose one of {', '.join(sorted(MUTATION_POLICIES))}",
            )
        if "allowlist" in raw and "mutation_allowlist" in raw:
            self.fail(
                "conflicting-fields",
                "allowlist and mutation_allowlist cannot both be declared",
                phase=phase_id,
                field="allowlist",
                value=raw["allowlist"],
                remediation="declare only allowlist",
            )
        allowlist_value = raw.get("allowlist", raw.get("mutation_allowlist", []))
        allowlist = self.string_list(
            allowlist_value, "allowlist", phase=phase_id, allow_empty=mutation != "allowlist"
        )
        for pattern in allowlist:
            if not _safe_declared_path(pattern, allow_glob=True):
                self.fail(
                    "unsafe-path",
                    f"allowlist pattern escapes the repository: {pattern!r}",
                    phase=phase_id,
                    field="allowlist",
                    value=pattern,
                    remediation="use repository-relative glob patterns without parent segments",
                )
        if mutation != "allowlist" and allowlist:
            self.fail(
                "unexpected-allowlist",
                f"mutation policy {mutation!r} cannot declare an allowlist",
                phase=phase_id,
                field="allowlist",
                value=allowlist,
                remediation="remove allowlist or use mutation = 'allowlist'",
            )
        completion_criteria = self.string_list(
            raw.get("completion_criteria"),
            "completion_criteria",
            phase=phase_id,
            allow_empty=False,
        )
        validator = self.parse_validator(raw, phase_id)
        commands = self.parse_commands(raw, phase_id)
        approval_conditions = self.string_list(
            raw.get("approval_conditions"),
            "approval_conditions",
            phase=phase_id,
            identifiers=True,
        )
        stop_conditions = self.string_list(
            raw.get("stop_conditions"),
            "stop_conditions",
            phase=phase_id,
            identifiers=True,
        )
        transitions_raw = raw.get("transitions")
        if not isinstance(transitions_raw, list):
            self.fail(
                "invalid-field-type",
                "transitions must be an array of tables",
                phase=phase_id,
                field="transitions",
                value=transitions_raw,
                remediation="declare one or more [[phases.transitions]] tables",
            )
        transitions = tuple(
            self.parse_transition(item, phase_id) for item in transitions_raw
        )
        max_visits = None
        if "max_visits" in raw:
            max_visits = self.require_integer(
                raw["max_visits"], "max_visits", phase=phase_id, minimum=1
            )
        return PhaseConfig(
            id=phase_id,
            skill=skill,
            skill_path=skill_path,
            inputs=inputs,
            output_name=output_name,
            output_template=output_template,
            output_template_path=output_template_path,
            mutation=mutation,
            allowlist=allowlist,
            completion_criteria=completion_criteria,
            validator=validator,
            commands=commands,
            approval_conditions=approval_conditions,
            stop_conditions=stop_conditions,
            transitions=transitions,
            max_visits=max_visits,
        )

    def parse_validator(
        self, phase_raw: Mapping[str, Any], phase_id: str
    ) -> ValidatorConfig:
        raw = phase_raw.get("validator")
        required_headings_raw: Any = phase_raw.get("required_headings", [])
        heading_occurrence_raw: Any = phase_raw.get(
            "heading_occurrence", "exactly-once"
        )
        declared_path_raw: Any = phase_raw.get("validator_path")
        if isinstance(raw, str):
            validator_type = self.require_string(raw, "validator", phase=phase_id)
        elif isinstance(raw, Mapping):
            self.check_unknown(
                raw,
                {
                    "type",
                    "required_headings",
                    "heading_occurrence",
                    "path",
                    "schema",
                },
                phase=phase_id,
            )
            validator_type = self.require_string(
                raw.get("type"), "validator.type", phase=phase_id
            )
            if "required_headings" in raw:
                if "required_headings" in phase_raw:
                    self.fail(
                        "conflicting-fields",
                        "required_headings is declared twice",
                        phase=phase_id,
                        field="required_headings",
                        value=required_headings_raw,
                        remediation="declare headings either beside or inside validator",
                    )
                required_headings_raw = raw["required_headings"]
            if "heading_occurrence" in raw:
                if "heading_occurrence" in phase_raw:
                    self.fail(
                        "conflicting-fields",
                        "heading_occurrence is declared twice",
                        phase=phase_id,
                        field="heading_occurrence",
                        value=heading_occurrence_raw,
                        remediation="declare it either beside or inside validator",
                    )
                heading_occurrence_raw = raw["heading_occurrence"]
            if "path" in raw and "schema" in raw:
                self.fail(
                    "conflicting-fields",
                    "validator path and schema cannot both be declared",
                    phase=phase_id,
                    field="validator.path",
                    value=raw["path"],
                    remediation="declare one validator file path",
                )
            nested_path = raw.get("path", raw.get("schema"))
            if nested_path is not None:
                if declared_path_raw is not None:
                    self.fail(
                        "conflicting-fields",
                        "validator path is declared twice",
                        phase=phase_id,
                        field="validator_path",
                        value=declared_path_raw,
                        remediation="declare the path either beside or inside validator",
                    )
                declared_path_raw = nested_path
        else:
            self.fail(
                "invalid-field-type",
                "validator must be a type string or table",
                phase=phase_id,
                field="validator",
                value=raw,
                remediation="use markdown, json, or file",
            )
        if validator_type not in VALIDATOR_TYPES:
            self.fail(
                "invalid-validator",
                f"phase {phase_id!r} uses unsupported validator {validator_type!r}",
                phase=phase_id,
                field="validator",
                value=validator_type,
                remediation=f"choose one of {', '.join(sorted(VALIDATOR_TYPES))}",
            )
        required_headings = self.string_list(
            required_headings_raw,
            "required_headings",
            phase=phase_id,
        )
        if validator_type != "markdown" and required_headings:
            self.fail(
                "invalid-validator-rule",
                "required_headings is supported only by the markdown validator",
                phase=phase_id,
                field="required_headings",
                value=required_headings,
                remediation="remove the headings or use validator = 'markdown'",
            )
        heading_occurrence = self.require_string(
            heading_occurrence_raw, "heading_occurrence", phase=phase_id
        )
        if heading_occurrence not in {"exactly-once", "at-least-once"}:
            self.fail(
                "invalid-heading-occurrence",
                "heading_occurrence must be exactly-once or at-least-once",
                phase=phase_id,
                field="heading_occurrence",
                value=heading_occurrence,
                remediation="choose exactly-once or at-least-once",
            )
        if validator_type != "markdown" and heading_occurrence_raw != "exactly-once":
            self.fail(
                "invalid-validator-rule",
                "heading_occurrence is supported only by the markdown validator",
                phase=phase_id,
                field="heading_occurrence",
                value=heading_occurrence,
                remediation="remove the setting or use validator = 'markdown'",
            )
        declared_path: str | None = None
        resolved_path: Path | None = None
        json_schema: Mapping[str, Any] | None = None
        if declared_path_raw is not None:
            declared_path = self.require_string(
                declared_path_raw, "validator_path", phase=phase_id
            )
            resolved_path = self.existing_path(
                declared_path, "validator_path", phase=phase_id
            )
            if validator_type != "json":
                self.fail(
                    "invalid-validator-rule",
                    "a validator schema path is supported only by the JSON validator",
                    phase=phase_id,
                    field="validator_path",
                    value=declared_path,
                    remediation="remove the path or use validator = 'json'",
                )
            from .validation import SchemaDefinitionError, load_json_schema

            try:
                json_schema = load_json_schema(resolved_path)
            except SchemaDefinitionError as exc:
                self.fail(
                    "unsupported-json-schema",
                    f"invalid JSON validator schema at {exc.location}: {exc}",
                    phase=phase_id,
                    field="validator_path",
                    value=declared_path,
                    remediation="use only type, required, properties, items, enum, pattern, and additionalProperties",
                )
        return ValidatorConfig(
            type=validator_type,
            required_headings=required_headings,
            heading_occurrence=heading_occurrence,
            declared_path=declared_path,
            resolved_path=resolved_path,
            json_schema=json_schema,
        )

    def parse_commands(
        self, raw: Mapping[str, Any], phase_id: str
    ) -> tuple[ValidationCommand, ...]:
        if "commands" in raw and "validation_commands" in raw:
            self.fail(
                "conflicting-fields",
                "commands and validation_commands cannot both be declared",
                phase=phase_id,
                field="commands",
                value=raw["commands"],
                remediation="declare only commands",
            )
        values = raw.get("commands", raw.get("validation_commands", []))
        if not isinstance(values, list):
            self.fail(
                "invalid-field-type",
                "commands must be an array of tables or argument arrays",
                phase=phase_id,
                field="commands",
                value=values,
                remediation="use command tables with an argv string array",
            )
        commands: list[ValidationCommand] = []
        for value in values:
            if isinstance(value, list):
                command_raw: Mapping[str, Any] = {"argv": value}
            else:
                command_raw = self.require_mapping(value, "commands", phase=phase_id)
            self.check_unknown(
                command_raw, {"argv", "timeout_seconds", "required"}, phase=phase_id
            )
            argv = self.string_list(
                command_raw.get("argv"), "commands.argv", phase=phase_id, allow_empty=False
            )
            timeout_raw = command_raw.get("timeout_seconds", 300)
            if (
                not isinstance(timeout_raw, (int, float))
                or isinstance(timeout_raw, bool)
                or not math.isfinite(timeout_raw)
                or timeout_raw <= 0
            ):
                self.fail(
                    "invalid-command-timeout",
                    "command timeout_seconds must be positive",
                    phase=phase_id,
                    field="commands.timeout_seconds",
                    value=timeout_raw,
                    remediation="set a positive timeout in seconds",
                )
            required = command_raw.get("required", True)
            if not isinstance(required, bool):
                self.fail(
                    "invalid-field-type",
                    "commands.required must be a boolean",
                    phase=phase_id,
                    field="commands.required",
                    value=required,
                    remediation="use true or false",
                )
            commands.append(
                ValidationCommand(argv, float(timeout_raw), required)
            )
        return tuple(commands)

    def parse_transition(self, value: Any, phase_id: str) -> TransitionConfig:
        raw = self.require_mapping(value, "transitions", phase=phase_id)
        self.check_unknown(
            raw, {"outcome", "target", "max_traversals"}, phase=phase_id
        )
        outcome = self.require_identifier(
            raw.get("outcome"), "transitions.outcome", phase=phase_id
        )
        target = None
        if "target" in raw:
            target = self.require_identifier(
                raw["target"], "transitions.target", phase=phase_id
            )
        max_traversals = None
        if "max_traversals" in raw:
            max_traversals = self.require_integer(
                raw["max_traversals"],
                "transitions.max_traversals",
                phase=phase_id,
                minimum=1,
            )
        return TransitionConfig(outcome, target, max_traversals)


def _safe_declared_path(
    value: str, *, allow_glob: bool = False, allow_parent: bool = False
) -> bool:
    if not value or "\\" in value or value.startswith("/"):
        return False
    if re.match(r"^[A-Za-z]:", value):
        return False
    parts = Path(value).parts
    if (".." in parts and not allow_parent) or "." in parts:
        return False
    if not allow_glob and any(character in value for character in "*?["):
        return False
    return True


def _validate_output_pattern(
    pattern: str,
    field: str,
    fail: Any,
    *,
    phase: str | None = None,
    output_name: str = "output.md",
) -> None:
    allowed_fields = {"visit", "phase", "output_name"}
    try:
        parsed = tuple(string.Formatter().parse(pattern))
        for _, name, _, conversion in parsed:
            if name is not None and name not in allowed_fields:
                raise ValueError(f"unknown placeholder {name!r}")
            if conversion:
                raise ValueError("conversions are not supported")
        rendered = pattern.format(visit=1, phase=phase or "phase", output_name=output_name)
    except (KeyError, IndexError, ValueError) as exc:
        fail(
            "invalid-output-pattern",
            f"{field} is not a valid output pattern: {exc}",
            phase=phase,
            field=field,
            value=pattern,
            remediation="use only {visit}, {phase}, and {output_name} placeholders",
        )
    if not _safe_declared_path(rendered):
        fail(
            "unsafe-output-path",
            f"{field} can resolve outside a run directory",
            phase=phase,
            field=field,
            value=pattern,
            remediation="use a relative output path without parent segments",
        )


def _validate_inputs(inputs: tuple[str, ...], phase: str, fail: Any) -> None:
    for reference in inputs:
        if reference == "request":
            continue
        if reference.startswith("latest:"):
            producer = reference.removeprefix("latest:")
            if IDENTIFIER_PATTERN.fullmatch(producer):
                continue
        if reference.startswith("visit:"):
            ordinal = reference.removeprefix("visit:")
            if ordinal.isascii() and ordinal.isdigit() and int(ordinal) >= 1:
                continue
        fail(
            "invalid-input-reference",
            f"phase {phase!r} has invalid input reference {reference!r}",
            phase=phase,
            field="inputs",
            value=reference,
            remediation="use request, latest:<phase>, or visit:<positive-number>",
        )


def _canonical_document(
    schema_version: int,
    pipeline_id: str,
    version: int,
    start: str,
    terminal_outcomes: tuple[str, ...],
    artifact_pattern: str,
    allow_non_git: bool,
    phases: tuple[PhaseConfig, ...],
) -> dict[str, Any]:
    return {
        "allow_non_git": allow_non_git,
        "artifact_pattern": artifact_pattern,
        "id": pipeline_id,
        "phases": [
            {
                "allowlist": list(phase.allowlist),
                "approval_conditions": list(phase.approval_conditions),
                "commands": [
                    {
                        "argv": list(command.argv),
                        "required": command.required,
                        "timeout_seconds": command.timeout_seconds,
                    }
                    for command in phase.commands
                ],
                "completion_criteria": list(phase.completion_criteria),
                "id": phase.id,
                "inputs": list(phase.inputs),
                "max_visits": phase.max_visits,
                "mutation": phase.mutation,
                "output_name": phase.output_name,
                "output_template": phase.output_template,
                "skill": phase.skill,
                "stop_conditions": list(phase.stop_conditions),
                "transitions": [
                    {
                        "max_traversals": transition.max_traversals,
                        "outcome": transition.outcome,
                        "target": transition.target,
                    }
                    for transition in sorted(
                        phase.transitions, key=lambda item: item.outcome
                    )
                ],
                "validator": {
                    "heading_occurrence": phase.validator.heading_occurrence,
                    "path": phase.validator.declared_path,
                    "required_headings": list(phase.validator.required_headings),
                    "type": phase.validator.type,
                },
            }
            for phase in phases
        ],
        "schema_version": schema_version,
        "start": start,
        "terminal_outcomes": sorted(terminal_outcomes),
        "version": version,
    }


def load_pipeline(
    path: str | Path = DEFAULT_PIPELINE_PATH,
    repository_root: str | Path | None = None,
    *,
    root: str | Path | None = None,
) -> PipelineConfig:
    """Load and fully validate a pipeline TOML file.

    ``root`` is accepted as a concise alias for ``repository_root``. Supplying
    both is rejected to keep path authority unambiguous.
    """

    source = Path(path).expanduser()
    try:
        source = source.resolve(strict=True)
    except OSError as exc:
        unresolved = source.resolve()
        raise PipelineConfigError(
            "pipeline-not-found",
            f"cannot read pipeline configuration: {unresolved}",
            path=unresolved,
            field="pipeline",
            value=str(unresolved),
            remediation="provide the path to an existing pipeline TOML file",
        ) from exc
    if not source.is_file():
        raise PipelineConfigError(
            "pipeline-not-file",
            f"pipeline configuration is not a file: {source}",
            path=source,
            field="pipeline",
            value=str(source),
            remediation="provide the path to a regular TOML file",
        )
    if repository_root is not None and root is not None:
        raise TypeError("pass repository_root or root, not both")
    requested_root = repository_root if repository_root is not None else root
    if requested_root is None:
        discovered = _discover_root(source)
        if discovered is None:
            raise PipelineConfigError(
                "repository-root-not-found",
                "could not discover a repository root for the pipeline",
                path=source,
                field="repository_root",
                remediation="pass repository_root for non-Git fixture repositories",
            )
        resolved_root = discovered
    else:
        resolved_root = Path(requested_root).expanduser().resolve()
    if not resolved_root.is_dir():
        raise PipelineConfigError(
            "invalid-repository-root",
            f"repository root is not a directory: {resolved_root}",
            path=source,
            field="repository_root",
            value=str(resolved_root),
            remediation="pass an existing repository directory",
        )
    if not source.is_relative_to(resolved_root):
        raise PipelineConfigError(
            "pipeline-outside-repository",
            "pipeline configuration resolves outside the repository",
            path=source,
            field="pipeline",
            value=str(source),
            remediation="place the pipeline inside the repository",
        )
    try:
        with source.open("rb") as stream:
            raw = tomllib.load(stream)
    except tomllib.TOMLDecodeError as exc:
        raise PipelineConfigError(
            "invalid-toml",
            f"pipeline configuration is not valid TOML: {exc}",
            path=source,
            field="pipeline",
            remediation="correct the TOML syntax",
        ) from exc
    except OSError as exc:
        raise PipelineConfigError(
            "pipeline-unreadable",
            f"cannot read pipeline configuration: {exc}",
            path=source,
            field="pipeline",
            remediation="make the file readable and try again",
        ) from exc
    return _Loader(source, resolved_root).parse(raw)


def load_config(
    path: str | Path = DEFAULT_PIPELINE_PATH,
    repository_root: str | Path | None = None,
) -> PipelineConfig:
    """Backward-compatible descriptive alias for :func:`load_pipeline`."""

    return load_pipeline(path, repository_root)


def canonicalize_pipeline(pipeline: PipelineConfig) -> str:
    return pipeline.canonical_json


def hash_pipeline(pipeline: PipelineConfig) -> str:
    return pipeline.config_hash


def require_pipeline_hash(pipeline: PipelineConfig, expected_hash: str) -> None:
    """Reject configuration drift for a persisted in-progress run."""

    if pipeline.config_hash != expected_hash:
        raise PipelineConfigError(
            "pipeline-hash-mismatch",
            "pipeline configuration changed after the run was created",
            path=pipeline.path,
            field="config_hash",
            value={"expected": expected_hash, "actual": pipeline.config_hash},
            remediation="restore the original pipeline or start a new run",
        )
