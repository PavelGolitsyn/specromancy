#!/usr/bin/env python3
"""Small, dependency-free state controller for a Markdown-skill pipeline."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "pipeline.toml"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
TERMINAL_STATUSES = {"completed", "blocked"}


class PipelineError(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            config = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise PipelineError(f"cannot load config {path}: {exc}") from exc
    validate_config(config, path)
    return config


def validate_config(config: dict[str, Any], path: Path) -> None:
    if config.get("schema_version") != 1:
        raise PipelineError("schema_version must be 1")
    if not isinstance(config.get("name"), str) or not config["name"].strip():
        raise PipelineError("name must be a non-empty string")
    initial = config.get("initial")
    states = config.get("states")
    if not isinstance(states, dict) or not states:
        raise PipelineError("states must be a non-empty table")
    if initial not in states:
        raise PipelineError(f"initial state {initial!r} does not exist")
    work_dir = config.get("work_dir")
    if not isinstance(work_dir, str) or not work_dir.strip():
        raise PipelineError("work_dir must be a non-empty relative path")
    if Path(work_dir).is_absolute() or ".." in Path(work_dir).parts:
        raise PipelineError("work_dir must stay inside the workspace")
    maximum = config.get("max_transitions")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
        raise PipelineError("max_transitions must be a positive integer")

    terminal_names: set[str] = set()
    edges: dict[str, set[str]] = {}
    for state_name, state in states.items():
        if not isinstance(state_name, str) or not NAME_RE.fullmatch(state_name):
            raise PipelineError(f"invalid state name {state_name!r}")
        if not isinstance(state, dict):
            raise PipelineError(f"state {state_name!r} must be a table")
        terminal = state.get("terminal")
        skill = state.get("skill")
        transitions = state.get("transitions")
        if terminal is not None:
            if terminal not in TERMINAL_STATUSES:
                raise PipelineError(
                    f"state {state_name!r} terminal must be completed or blocked"
                )
            if skill is not None or transitions is not None:
                raise PipelineError(
                    f"terminal state {state_name!r} cannot have skill or transitions"
                )
            terminal_names.add(state_name)
            edges[state_name] = set()
            continue
        if not isinstance(skill, str) or not skill.endswith("/SKILL.md"):
            raise PipelineError(f"active state {state_name!r} needs a SKILL.md path")
        skill_path = (path.parent / skill).resolve()
        try:
            skill_path.relative_to(path.parent.resolve())
        except ValueError as exc:
            raise PipelineError(
                f"state {state_name!r} skill must stay beside the config tree"
            ) from exc
        if not skill_path.is_file():
            raise PipelineError(f"state {state_name!r} skill not found: {skill_path}")
        if not isinstance(transitions, dict) or not transitions:
            raise PipelineError(f"active state {state_name!r} needs transitions")
        edges[state_name] = set()
        for outcome, target in transitions.items():
            if not isinstance(outcome, str) or not NAME_RE.fullmatch(outcome):
                raise PipelineError(
                    f"state {state_name!r} has invalid outcome {outcome!r}"
                )
            if target not in states:
                raise PipelineError(
                    f"state {state_name!r} outcome {outcome!r} targets unknown {target!r}"
                )
            edges[state_name].add(target)

    if not terminal_names:
        raise PipelineError("at least one terminal state is required")
    reachable = walk({initial}, edges)
    unreachable = set(states) - reachable
    if unreachable:
        raise PipelineError(f"unreachable states: {', '.join(sorted(unreachable))}")

    reverse = {name: set() for name in states}
    for source, targets in edges.items():
        for target in targets:
            reverse[target].add(source)
    can_finish = walk(terminal_names, reverse)
    dead_ends = set(states) - can_finish
    if dead_ends:
        raise PipelineError(
            f"states cannot reach a terminal state: {', '.join(sorted(dead_ends))}"
        )


def walk(start: set[str], edges: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    pending = list(start)
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        pending.extend(edges[current] - seen)
    return seen


def runtime_paths(
    config: dict[str, Any], workspace: Path, run_id: str
) -> tuple[Path, Path, Path]:
    if not RUN_ID_RE.fullmatch(run_id):
        raise PipelineError(
            "run id must start with an alphanumeric character and contain only "
            "letters, digits, dot, underscore, or hyphen"
        )
    run_dir = workspace.resolve() / config["work_dir"] / "runs" / run_id
    return run_dir, run_dir / "state.json", run_dir / "artifacts"


def read_state(state_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"cannot load run state {state_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PipelineError(f"run state {state_path} is not a JSON object")
    return data


def atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def require_matching_pipeline(state: dict[str, Any], config: dict[str, Any]) -> None:
    if state.get("pipeline") != config["name"]:
        raise PipelineError(
            f"run belongs to pipeline {state.get('pipeline')!r}, not {config['name']!r}"
        )
    if state.get("state") not in config["states"]:
        raise PipelineError(f"run references unknown state {state.get('state')!r}")


def command_validate(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    print(f"valid: {config['name']} ({len(config['states'])} states)")


def command_start(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    run_dir, state_path, artifacts = runtime_paths(config, args.workspace, args.run)
    if state_path.exists():
        raise PipelineError(f"run {args.run!r} already exists at {state_path}")
    task = args.task
    if args.task_file:
        try:
            task = args.task_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise PipelineError(f"cannot read task file {args.task_file}: {exc}") from exc
    if not task or not task.strip():
        raise PipelineError("provide a non-empty --task or --task-file")
    artifacts.mkdir(parents=True, exist_ok=True)
    timestamp = now()
    state = {
        "schema_version": 1,
        "pipeline": config["name"],
        "run_id": args.run,
        "task": task.strip(),
        "state": config["initial"],
        "status": "active",
        "transition_count": 0,
        "history": [],
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    atomic_json(state_path, state)
    print(f"started {args.run}: {config['initial']}")
    print(f"run directory: {run_dir}")


def command_status(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    run_dir, state_path, _ = runtime_paths(config, args.workspace, args.run)
    state = read_state(state_path)
    require_matching_pipeline(state, config)
    if args.json:
        print(json.dumps(state, indent=2, sort_keys=True))
        return
    print(f"run: {state['run_id']}")
    print(f"pipeline: {state['pipeline']}")
    print(f"state: {state['state']}")
    print(f"status: {state['status']}")
    print(f"transitions: {state['transition_count']}/{config['max_transitions']}")
    print(f"run directory: {run_dir}")


def command_prompt(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    run_dir, state_path, artifacts = runtime_paths(config, args.workspace, args.run)
    state = read_state(state_path)
    require_matching_pipeline(state, config)
    if state.get("status") != "active":
        raise PipelineError(f"run is {state.get('status')}; there is no active stage")
    state_name = state["state"]
    definition = config["states"][state_name]
    if "terminal" in definition:
        raise PipelineError(f"terminal state {state_name!r} cannot render a prompt")
    skill_path = (args.config.parent / definition["skill"]).resolve()
    skill = skill_path.read_text(encoding="utf-8").strip()
    outcomes = definition["transitions"]
    history = state.get("history", [])
    latest = history[-1]["summary"] if history else "None; this is the first stage."
    print(f"# Pipeline stage: {state_name}\n")
    print(f"Run: `{state['run_id']}`")
    print(f"Pipeline: `{state['pipeline']}`")
    print(f"Workspace: `{args.workspace.resolve()}`")
    print(f"Run directory: `{run_dir}`")
    print(f"Artifact directory: `{artifacts}`\n")
    print("## Original task\n")
    print(state["task"])
    print("\n## Previous transition summary\n")
    print(latest)
    print("\n## Allowed outcomes\n")
    for outcome, target in outcomes.items():
        print(f"- `{outcome}` -> `{target}`")
    print("\n## Stage skill\n")
    print(skill)
    print("\n## Completion protocol\n")
    print("Perform the stage in the workspace. Keep durable handoff material in the")
    print("artifact directory. Then choose exactly one allowed outcome and let the")
    print("orchestrator record it with `pipeline.py advance`. Do not invent a state")
    print("or outcome, and do not edit `state.json` directly.")


def command_advance(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    _, state_path, _ = runtime_paths(config, args.workspace, args.run)
    state = read_state(state_path)
    require_matching_pipeline(state, config)
    if state.get("status") != "active":
        raise PipelineError(f"run is already {state.get('status')}")
    count = state.get("transition_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise PipelineError("run has an invalid transition_count")
    if count >= config["max_transitions"]:
        raise PipelineError(
            "transition limit reached; inspect the run before changing the config or state"
        )
    current = state["state"]
    definition = config["states"][current]
    transitions = definition.get("transitions", {})
    if args.outcome not in transitions:
        allowed = ", ".join(sorted(transitions))
        raise PipelineError(
            f"outcome {args.outcome!r} is not allowed from {current!r}; choose {allowed}"
        )
    if not args.summary.strip():
        raise PipelineError("summary must not be empty")
    target = transitions[args.outcome]
    timestamp = now()
    state["history"].append(
        {
            "from": current,
            "outcome": args.outcome,
            "to": target,
            "summary": args.summary.strip(),
            "artifacts": args.artifact,
            "at": timestamp,
        }
    )
    state["state"] = target
    state["transition_count"] = count + 1
    state["updated_at"] = timestamp
    target_definition = config["states"][target]
    state["status"] = target_definition.get("terminal", "active")
    atomic_json(state_path, state)
    print(f"advanced {args.run}: {current} --{args.outcome}--> {target}")
    print(f"status: {state['status']}")


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help="pipeline TOML file"
    )
    common.add_argument(
        "--workspace", type=Path, default=Path.cwd(), help="target workspace"
    )
    top = argparse.ArgumentParser(description=__doc__)
    subcommands = top.add_subparsers(dest="command", required=True)

    validate = subcommands.add_parser("validate", parents=[common])
    validate.set_defaults(handler=command_validate)

    start = subcommands.add_parser("start", parents=[common])
    start.add_argument("--run", required=True, help="stable run identifier")
    task_group = start.add_mutually_exclusive_group(required=True)
    task_group.add_argument("--task", help="task text")
    task_group.add_argument("--task-file", type=Path, help="UTF-8 task file")
    start.set_defaults(handler=command_start)

    status = subcommands.add_parser("status", parents=[common])
    status.add_argument("--run", required=True)
    status.add_argument("--json", action="store_true")
    status.set_defaults(handler=command_status)

    prompt = subcommands.add_parser("prompt", parents=[common])
    prompt.add_argument("--run", required=True)
    prompt.set_defaults(handler=command_prompt)

    advance = subcommands.add_parser("advance", parents=[common])
    advance.add_argument("--run", required=True)
    advance.add_argument("--outcome", required=True)
    advance.add_argument("--summary", required=True)
    advance.add_argument(
        "--artifact", action="append", default=[], help="workspace-relative artifact path"
    )
    advance.set_defaults(handler=command_advance)
    return top


def main() -> int:
    args = parser().parse_args()
    args.config = args.config.resolve()
    args.workspace = args.workspace.resolve()
    try:
        args.handler(args)
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
