import contextlib
import io
import json
import os
import subprocess
import tempfile
from pathlib import Path
import unittest

from specromancy.cli import main
from specromancy.contracts import pipeline_contract
from specromancy.events import load_events, replay_events, verify_event_projection
from specromancy.errors import ConcurrencyError, InvalidInputError, ValidationError
from specromancy.locking import inspect_run_lock
from specromancy.orchestrator import (
    cancel_run,
    exhaust_review_cycles,
    recover_lock,
    resume_run,
)
from specromancy.paths import RepositoryPaths
from specromancy.run import initialize_run, load_manifest


class StateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        subprocess.run(["git", "init", "--quiet"], cwd=self.root, check=True)
        (self.root / ".gitignore").write_text(".specromancy/runs/\n", encoding="utf-8")
        (self.root / "README.md").write_text("# Fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(
            [
                "git", "-c", "user.name=Tests", "-c", "user.email=tests@example.invalid",
                "commit", "--quiet", "-m", "fixture",
            ],
            cwd=self.root,
            check=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _init(self, run_id: str) -> RepositoryPaths:
        initialize_run(
            self.root,
            run_id=run_id,
            title="State fixture",
            request_text="# Request\n\nUpdate the fixture.",
        )
        return RepositoryPaths(self.root)

    def test_initialization_is_durable_and_reinitialization_fails(self) -> None:
        paths = self._init("20260922-init")
        manifest = load_manifest(paths, "20260922-init")
        projection = verify_event_projection(paths, "20260922-init", manifest)
        self.assertEqual(projection.status, "initialized")
        self.assertEqual(manifest["requirements"][0]["id"], "REQ-001")
        with self.assertRaises(InvalidInputError):
            self._init("20260922-init")

    def test_resume_rejects_edited_artifact_and_changed_head(self) -> None:
        artifact_run = "20260922-edited"
        paths = self._init(artifact_run)
        paths.run_artifact(artifact_run, "request.md").write_text(
            "edited outside the CLI\n", encoding="utf-8"
        )
        with self.assertRaises(ValidationError):
            resume_run(self.root, artifact_run)

        head_run = "20260922-head"
        self._init(head_run)
        (self.root / "concurrent.txt").write_text("commit\n", encoding="utf-8")
        subprocess.run(["git", "add", "concurrent.txt"], cwd=self.root, check=True)
        subprocess.run(
            [
                "git", "-c", "user.name=Tests", "-c", "user.email=tests@example.invalid",
                "commit", "--quiet", "-m", "concurrent",
            ],
            cwd=self.root,
            check=True,
        )
        with self.assertRaises(ConcurrencyError):
            resume_run(self.root, head_run)

    def test_repair_cycle_exhaustion_transitions_to_blocked(self) -> None:
        run_id = "20260922-exhausted"
        paths = self._init(run_id)
        manifest = load_manifest(paths, run_id)
        by_id = {row["id"]: row for row in pipeline_contract()["transitions"]}
        identifiers = [
            "research.start", "research.complete", "plan.start", "plan.complete",
            "plan.approve", "implementation.start", "implementation.complete",
            "review.start", "review.request_changes",
        ]
        for _ in range(manifest["max_review_cycles"]):
            identifiers.extend(
                [
                    "implementation.start_repair", "implementation.complete",
                    "review.start", "review.request_changes",
                ]
            )
        events = list(load_events(paths.run_events(run_id)))
        status = "initialized"
        for identifier in identifiers:
            row = by_id[identifier]
            event = {
                "schema_version": "1", "event_type": "transition", "run_id": run_id,
                "phase": row["phase"], "occurred_at": manifest["created_at"],
                "action": row["action"], "transition_id": identifier,
                "from_status": status, "to_status": row["to"],
            }
            events.append(event)
            status = row["to"]
        paths.run_events(run_id).write_text(
            "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
            encoding="utf-8",
        )
        manifest.update(
            status="changes_requested",
            current_phase=None,
            review_cycle=manifest["max_review_cycles"],
        )
        paths.run_manifest(run_id).write_text(json.dumps(manifest), encoding="utf-8")
        blocked = exhaust_review_cycles(self.root, run_id)
        self.assertEqual(blocked["status"], "blocked")
        verify_event_projection(paths, run_id, blocked)

    def test_cancellation_is_available_from_every_nonterminal_status(self) -> None:
        contract = pipeline_contract()
        transitions = [row for row in contract["transitions"] if row["id"] != "run.cancel"]
        adjacency: dict[str, list[dict]] = {}
        for row in transitions:
            sources = [row["from"]] if "from" in row else row.get("allowed_from", [])
            for source in sources:
                adjacency.setdefault(source, []).append(row)

        def path_to(target: str) -> list[dict]:
            queue: list[tuple[str, list[dict]]] = [("initialized", [])]
            seen = {"initialized"}
            while queue:
                status, path = queue.pop(0)
                if status == target:
                    return path
                for row in adjacency.get(status, []):
                    if row["to"] not in seen and row["to"] not in {"blocked", "cancelled", "passed"}:
                        seen.add(row["to"])
                        queue.append((row["to"], [*path, row]))
            raise AssertionError(f"no path to {target}")

        phases = contract["status_current_phase"]
        for index, status in enumerate(
            item for item in contract["statuses"] if item not in contract["terminal_statuses"]
        ):
            run_id = f"20260922-cancel-{index:02d}"
            paths = self._init(run_id)
            manifest = load_manifest(paths, run_id)
            events = list(load_events(paths.run_events(run_id)))
            cycle = 0
            for row in path_to(status):
                source = events[-1].get("to_status", events[-1].get("status"))
                event = {
                    "schema_version": "1", "event_type": "transition", "run_id": run_id,
                    "phase": row["phase"], "occurred_at": manifest["created_at"],
                    "action": row["action"], "transition_id": row["id"],
                    "from_status": source, "to_status": row["to"],
                }
                events.append(event)
                if row["id"] == "implementation.start_repair":
                    cycle += 1
            paths.run_events(run_id).write_text(
                "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
                encoding="utf-8",
            )
            manifest.update(status=status, current_phase=phases[status], review_cycle=cycle)
            paths.run_manifest(run_id).write_text(json.dumps(manifest), encoding="utf-8")
            cancelled = cancel_run(self.root, run_id, reason="contract cancellation test")
            self.assertEqual(cancelled["status"], "cancelled")
            verify_event_projection(paths, run_id, cancelled)

    def test_concurrent_processes_cannot_both_cancel(self) -> None:
        run_id = "20260922-race"
        self._init(run_id)
        source_root = str(Path(__file__).parents[2] / "src")
        environment = {**os.environ, "PYTHONPATH": source_root}
        argv = [
            os.environ.get("PYTHON", "python3"), "-m", "specromancy", "cancel", run_id,
            "--reason", "race", "--repo", str(self.root), "--format", "json",
        ]
        processes = [
            subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment)
            for _ in range(2)
        ]
        completed = [process.communicate(timeout=10) + (process.returncode,) for process in processes]
        codes = sorted(item[2] for item in completed)
        self.assertEqual(codes[0], 0)
        self.assertIn(codes[1], {3, 8})
        for stdout, _, _ in completed:
            json.loads(stdout)

    def test_abrupt_exit_leaves_recoverable_lock(self) -> None:
        run_id = "20260922-stale"
        self._init(run_id)
        source_root = str(Path(__file__).parents[2] / "src")
        script = (
            "import os; from pathlib import Path; "
            "from specromancy.paths import RepositoryPaths; "
            "from specromancy.locking import RunLock; "
            f"lock=RunLock(RepositoryPaths(Path({str(self.root)!r})), {run_id!r}, 'crash'); "
            "lock.__enter__(); os._exit(0)"
        )
        subprocess.run(
            [os.environ.get("PYTHON", "python3"), "-c", script],
            check=True,
            env={**os.environ, "PYTHONPATH": source_root},
        )
        self.assertIsNotNone(inspect_run_lock(self.root, run_id))
        recovered = recover_lock(self.root, run_id)
        self.assertEqual(recovered["run_id"], run_id)
        self.assertIsNone(inspect_run_lock(self.root, run_id))
        self.assertEqual(resume_run(self.root, run_id)["status"], "initialized")

    def test_json_errors_remain_machine_readable(self) -> None:
        run_id = "20260922-errors"
        self._init(run_id)
        cancel_run(self.root, run_id, reason="done")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(("cancel", run_id, "--reason", "again", "--repo", str(self.root), "--format", "json"))
        envelope = json.loads(output.getvalue())
        self.assertEqual(code, 3)
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["errors"][0]["code"], "INVALID_TRANSITION")


if __name__ == "__main__":
    unittest.main()
