from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from specromancy.config import load_pipeline
from specromancy.run_store import RunStore


ROOT = Path(__file__).resolve().parents[3]
RUN_ID = "20260925T120000Z-a1b2c3d4"


class RecoveryContractTests(unittest.TestCase):
    def test_fresh_process_reconstructs_a_run_using_only_disk_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()
            skill = root / ".agents" / "skills" / "compose" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                "---\nname: compose\ndescription: Fixture.\n---\n", encoding="utf-8"
            )
            pipeline_path = root / "pipeline.toml"
            pipeline_path.write_text(
                textwrap.dedent(
                    """
                    schema_version = 1
                    id = "recovery"
                    version = 1
                    start = "compose"
                    terminal_outcomes = ["done"]
                    artifact_pattern = "artifacts/{visit:03}-{phase}.md"
                    allow_non_git = true
                    [[phases]]
                    id = "compose"
                    skill = "compose"
                    inputs = ["request"]
                    output_name = "{visit:03}-result.md"
                    mutation = "read-only"
                    completion_criteria = ["Write."]
                    validator = "file"
                    approval_conditions = []
                    stop_conditions = []
                    max_visits = 1
                    [[phases.transitions]]
                    outcome = "done"
                    """
                ),
                encoding="utf-8",
            )
            pipeline = load_pipeline(pipeline_path, root)
            store = RunStore(root)
            store.create(pipeline, "recover me", run_id=RUN_ID)
            visit = store.start_visit(RUN_ID, pipeline, "compose")
            store.write_visit_output(RUN_ID, visit["ordinal"], "result\n")
            store.complete_visit(RUN_ID, visit["ordinal"], outcome="done")

            program = (
                "import json,sys; "
                "from specromancy.run_store import RunStore; "
                "print(json.dumps(RunStore(sys.argv[1]).load(sys.argv[2]), sort_keys=True))"
            )
            result = subprocess.run(
                [sys.executable, "-c", program, str(root), RUN_ID],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["run_id"], RUN_ID)
            self.assertEqual(manifest["visits"][0]["status"], "completed")
            self.assertEqual(manifest["visits"][0]["output"]["sha256"], visit_hash(store))


def visit_hash(store: RunStore) -> str:
    return store.load(RUN_ID)["visits"][0]["output"]["sha256"]


if __name__ == "__main__":
    unittest.main()
