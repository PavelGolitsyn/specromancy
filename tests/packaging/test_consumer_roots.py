"""Self-contained smoke suite: copy this file outside the checkout to test a wheel.

No producer fixtures, build tools, downloads, or source-path injection are used.
Run with the installed environment's Python; subprocesses use its console script.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path

from specromancy_engine import Engine, EngineError, ExitCode, RunStore, load_pipeline, load_registry
from specromancy_engine.cli import main
from specromancy_engine.schema_validation import load_json_schema


SCHEMAS = {"event.schema.json", "run.schema.json", "pipeline.schema.json", "pipelines.schema.json"}


def snapshot(root: Path, *, exclude_runs: bool = False) -> dict:
    """Capture content, modes, and links, including Git metadata and empty dirs."""
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if exclude_runs and (relative in {".specromancy", ".specromancy/runs"}
                             or relative.startswith(".specromancy/runs/")):
            continue
        mode = path.lstat().st_mode
        content = (os.readlink(path) if path.is_symlink() else
                   hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
        result[relative] = (mode, content)
    return result


def write_consumer(root: Path, phase: str, *, allow_non_git: bool = False) -> None:
    resources = {
        "workflow/pipelines.toml": 'schema_version = 1\n[[pipelines]]\nid = "shared"\npath = "pipelines/flow.toml"\n',
        "workflow/pipelines/flow.toml": (
            f'schema_version = 1\nid = "shared"\nversion = 1\nstart = "{phase}"\n'
            'terminal_outcomes = ["done"]\nartifact_pattern = "artifacts/{visit:03}-{phase}.json"\n'
            f'allow_non_git = {str(allow_non_git).lower()}\n'
            f'[[phases]]\nid = "{phase}"\nskill = "compose"\ninputs = ["request"]\n'
            'output_name = "result.json"\noutput_template = "../templates/result.json"\n'
            'mutation = "read-only"\ncompletion_criteria = ["Record the consumer result."]\n'
            'validator = {type = "json", path = "../schemas/result.json"}\n'
            'approval_conditions = []\nstop_conditions = []\n'
            '[[phases.transitions]]\noutcome = "done"\n'
        ),
        ".agents/skills/compose/SKILL.md": f"---\nname: compose\ndescription: Record {phase}.\n---\nUse {phase} resources.\n",
        "workflow/templates/result.json": json.dumps({"consumer": phase}) + "\n",
        "workflow/schemas/result.json": json.dumps({
            "type": "object", "required": ["consumer"],
            "properties": {"consumer": {"enum": [phase]}}, "additionalProperties": False,
        }),
        "request.md": f"Request for {phase}\n",
    }
    for name, content in resources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    (root / "nested/deeper").mkdir(parents=True, exist_ok=True)


class ConsumerRootTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.outside = self.base / "unrelated"
        self.outside.mkdir()
        self.home = self.base / "empty-home"
        self.home.mkdir()
        self.env = os.environ.copy()
        for name in tuple(self.env):
            if name.startswith("PYTHON") or name.startswith("GIT_"):
                self.env.pop(name)
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                        XDG_CONFIG_HOME=str(self.home), PYTHONNOUSERSITE="1",
                        PYTHONDONTWRITEBYTECODE="1", GIT_CONFIG_NOSYSTEM="1")
        self.console = Path(sys.executable).parent / ("specromancy.exe" if os.name == "nt" else "specromancy")
        self.assertTrue(self.console.is_file(), "install the checkout or wheel before testing")
        git = shutil.which("git")
        self.assertIsNotNone(git)
        # Only the environment's scripts and Git's directory; no producer bin/.
        self.env["PATH"] = os.pathsep.join((str(self.console.parent), str(Path(git).parent)))
        self.first, self.second = self.base / "amber", self.base / "blue"
        self.first.mkdir()
        self.git("init", "--quiet", str(self.first))
        self.git("-C", str(self.first), "-c", "user.name=Consumer Test",
                 "-c", "user.email=consumer@example.invalid", "-c", "commit.gpgsign=false",
                 "commit", "--quiet", "--allow-empty", "-m", "Test worktree seed")
        self.git("-C", str(self.first), "worktree", "add", "--quiet", "--detach", str(self.second))
        write_consumer(self.first, "amber")
        write_consumer(self.second, "blue")

    def git(self, *args: str) -> None:
        result = subprocess.run(["git", *args], cwd=self.outside, env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def command(self, cwd: Path, *args: str, expected: int = 0, module: bool = False) -> dict:
        argv = [sys.executable, "-m", "specromancy_engine"] if module else [str(self.console)]
        result = subprocess.run([*argv, "--json", *args], cwd=cwd, env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertFalse(result.stdout and result.stderr, result.stdout + result.stderr)
        return json.loads(result.stdout or result.stderr)

    def assert_action(self, action: dict, root: Path, phase: str) -> None:
        self.assertEqual(action["phase"], phase)
        self.assertEqual(Path(action["skill"]["absolute_path"]), root / ".agents/skills/compose/SKILL.md")
        self.assertIn(f"Use {phase} resources.", Path(action["skill"]["absolute_path"]).read_text())
        self.assertEqual(Path(action["template"]["absolute_path"]), root / "workflow/templates/result.json")
        self.assertEqual(json.loads(Path(action["template"]["absolute_path"]).read_text()), {"consumer": phase})
        self.assertEqual(Path(action["inputs"][0]["absolute_path"]).read_text(), f"Request for {phase}\n")
        run_root = root / ".specromancy/runs" / action["run_id"]
        self.assertTrue(Path(action["output"]["absolute_path"]).is_relative_to(run_root))
        self.assertEqual(action["final_validation_command"][:3], ["specromancy", "--root", str(root)])

    def test_cli_discovers_both_git_markers_and_keeps_consumers_isolated(self) -> None:
        self.assertTrue((self.first / ".git").is_dir())
        self.assertTrue((self.second / ".git").is_file())
        before = snapshot(self.base, exclude_runs=False)
        # Exclude only each consumer's run storage when comparing all other files.
        protected = [snapshot(root, exclude_runs=True) for root in (self.first, self.second)]
        actions = []
        for root, phase in ((self.first, "amber"), (self.second, "blue")):
            for cwd in (root, root / "nested/deeper"):
                action = self.command(cwd, "init", "--description-file", "request.md",
                                      "--pipeline", "shared", expected=8)["action"]
                self.assert_action(action, root, phase)
                actions.append((root, phase, action))
        for root, phase, action in reversed(actions):
            run_id = action["run_id"]
            status = self.command(self.outside, "--root", str(root), "status", run_id, module=True)["status"]
            self.assertEqual(status["pipeline"]["id"], "shared")
            self.command(root / "nested/deeper", phase, run_id, expected=8)
            Path(action["output"]["absolute_path"]).write_text(json.dumps({"consumer": phase}), encoding="utf-8")
            result = subprocess.run(action["final_validation_command"], cwd=self.outside,
                                    env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            completed = self.command(root, "status", run_id)["status"]
            self.assertEqual(completed["terminal_result"]["outcome"], "done")
            other = self.second if root == self.first else self.first
            self.command(self.outside, "--root", str(other), "status", run_id, expected=ExitCode.NOT_FOUND)
        for root, original in zip((self.first, self.second), protected):
            self.assertEqual(snapshot(root, exclude_runs=True), original)
        self.assertEqual(snapshot(self.home), {})
        self.assertEqual(snapshot(self.outside), {})
        after = snapshot(self.base)
        self.assertEqual({key: after[key] for key in before}, before)
        self.assertTrue(all(key.split("/")[0] in {"amber", "blue"} and
                            (key.endswith("/.specromancy") or "/.specromancy/runs" in key)
                            for key in after.keys() - before.keys()))

    def test_public_api_and_in_process_cli_do_not_cache_same_pipeline_id(self) -> None:
        registries = [load_registry(root) for root in (self.first, self.second)]
        pipelines = [registry.load("shared") for registry in registries]
        self.assertNotEqual(pipelines[0].config_hash, pipelines[1].config_hash)
        protected = [snapshot(root, exclude_runs=True) for root in (self.first, self.second)]
        runs = []
        for pipeline in pipelines:
            root, phase = pipeline.repository_root, pipeline.start
            self.assertEqual(load_pipeline(pipeline.path, repository_root=root), pipeline)
            schema = load_json_schema(pipeline.phase(phase).validator.resolved_path)
            self.assertEqual(schema["properties"]["consumer"]["enum"], [phase])
            engine = Engine(pipeline, RunStore(root))
            action = engine.initialize((root / "request.md").read_text())["action"]
            self.assert_action(action, root, phase)
            runs.append((engine, action))
        # Interleave retained registry/engine objects and repeated CLI calls in one process.
        for registry, (engine, action) in reversed(list(zip(registries, runs))):
            root, phase, run_id = engine.pipeline.repository_root, engine.pipeline.start, action["run_id"]
            self.assertEqual(registry.load("shared").start, phase)
            stdout, stderr = io.StringIO(), io.StringIO()
            code = main(["--root", str(root), "--json", "status", run_id], stdout=stdout, stderr=stderr)
            self.assertEqual(code, 0, stderr.getvalue())
            self.assertEqual(json.loads(stdout.getvalue())["status"]["pipeline"]["sha256"], engine.pipeline.config_hash)
            engine.start_phase(run_id, phase)
            output = Path(action["output"]["absolute_path"])
            output.write_text(json.dumps({"consumer": "wrong-project"}), encoding="utf-8")
            with self.assertRaises(EngineError) as raised:
                engine.validate(run_id, phase)
            self.assertEqual(raised.exception.code, ExitCode.VALIDATION_FAILED)
            output.write_text(json.dumps({"consumer": phase}), encoding="utf-8")
            self.assertEqual(engine.validate(run_id, phase)["code"], 0)
            stored = RunStore(root).load(run_id)
            self.assertEqual(stored["pipeline"]["path"], "workflow/pipelines/flow.toml")
            self.assertEqual(stored["pipeline"]["sha256"], engine.pipeline.config_hash)
            restored = Engine(load_pipeline(root / stored["pipeline"]["path"], repository_root=root), RunStore(root))
            self.assertEqual(restored.status(run_id)["status"]["terminal_result"]["outcome"], "done")
        for root, original in zip((self.first, self.second), protected):
            self.assertEqual(snapshot(root, exclude_runs=True), original)

    def test_explicit_non_git_roots_and_failure_diagnostics(self) -> None:
        root = self.base / "non-git"
        write_consumer(root, "standalone", allow_non_git=True)
        before = snapshot(self.base)
        for cwd in (self.outside, root, root / "nested/deeper"):
            payload = self.command(cwd, "init", "Request", "--pipeline", "shared", expected=2)
            self.assertEqual(payload["message"], "could not find a repository root; pass --root PATH")
        for path, suffix in ((self.base / "absent", "does not exist"), (root / "request.md", "is not a directory")):
            payload = self.command(self.first, "--root", str(path), "init", "Request", "--pipeline", "shared", expected=2)
            self.assertIn(suffix, payload["message"])
            self.assertEqual(payload["details"]["root"], str(path))
        payload = self.command(self.outside, "--root", str(root), "init", "Request", expected=2)
        self.assertEqual(payload["message"], "init requires --pipeline ID; there is no default pipeline")
        self.assertEqual(snapshot(self.base), before)
        action = self.command(self.outside, "--root", str(root), "init", "--description-file", "request.md",
                              "--pipeline", "shared", expected=8)["action"]
        self.assert_action(action, root, "standalone")
        denied = self.base / "git-required"
        write_consumer(denied, "denied")
        payload = self.command(self.outside, "--root", str(denied), "init", "Request", "--pipeline", "shared", expected=ExitCode.INVALID_PIPELINE)
        self.assertEqual(payload["details"]["error_code"], "git-worktree-required")
        self.assertFalse((denied / ".specromancy").exists())

    def test_saved_provenance_survives_registry_retargeting_but_registry_is_mandatory(self) -> None:
        action = self.command(self.first, "init", "Request", "--pipeline", "shared", expected=8)["action"]
        root, run_id = self.first, action["run_id"]
        registry = root / "workflow/pipelines.toml"
        # Change only test-owned config; existing runs must use their saved path.
        other = root / "workflow/pipelines/other.toml"
        other.write_bytes((root / "workflow/pipelines/flow.toml").read_bytes().replace(b'"amber"', b'"other"'))
        registry.write_text(registry.read_text().replace("flow.toml", "other.toml"))
        resumed = self.command(self.outside, "--root", str(root), "resume", run_id, expected=8)["action"]
        self.assertEqual(resumed["phase"], "amber")
        fresh = self.command(root, "init", "New request", "--pipeline", "shared", expected=8)["action"]
        self.assertEqual(fresh["phase"], "other")
        self.command(root, "--pipeline", "wrong", "status", run_id, expected=2)
        registry.unlink()
        before = snapshot(self.base)
        for args in (("status", run_id), ("init", "Request", "--pipeline", "shared")):
            payload = self.command(root, *args, expected=ExitCode.INVALID_PIPELINE)
            self.assertEqual(payload["details"]["error_code"], "invalid-registry")
            self.assertEqual(payload["details"]["path"], str(registry))
        self.assertEqual(snapshot(self.base), before)


class PackageResourceTests(unittest.TestCase):
    def test_all_four_published_schemas_are_readable_json(self) -> None:
        resources = files("specromancy_engine").joinpath("schemas")
        self.assertEqual({item.name for item in resources.iterdir() if item.name.endswith(".json")}, SCHEMAS)
        for name in sorted(SCHEMAS):
            with self.subTest(name=name):
                schema = json.loads(files("specromancy_engine").joinpath("schemas", name).read_text(encoding="utf-8"))
                self.assertIsInstance(schema, dict)
                self.assertEqual(schema["type"], "object")
                self.assertIn("$schema", schema)


if __name__ == "__main__":
    unittest.main()
