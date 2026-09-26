from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


class CliRepository:
    """A real temporary Git repository driven through fresh CLI processes."""

    def __init__(self, *, replacement: bool = False) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self._git("init", "--quiet")
        self._git("config", "user.email", "contract@example.invalid")
        self._git("config", "user.name", "Contract Test")
        if replacement:
            shutil.copytree(
                ROOT / "tests" / "fixtures" / "replacement-pipeline",
                self.root,
                dirs_exist_ok=True,
            )
            self.pipeline = self.root / "pipeline.toml"
        else:
            shutil.copytree(ROOT / ".agents", self.root / ".agents")
            (self.root / "specromancy" / "templates").mkdir(parents=True)
            for source in (ROOT / "specromancy" / "templates").glob("*.md"):
                shutil.copy2(source, self.root / "specromancy" / "templates" / source.name)
            source = (ROOT / "specromancy" / "pipeline.toml").read_text(
                encoding="utf-8"
            )
            source = source.replace(
                '["python", "-m", "unittest", "discover"]',
                json.dumps([sys.executable, "-c", "pass"]),
            )
            self.pipeline = self.root / "specromancy" / "pipeline.toml"
            self.pipeline.write_text(source, encoding="utf-8")
        (self.root / "tracked.txt").write_text("baseline\n", encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "--quiet", "-m", "fixture")

    def close(self) -> None:
        self.temporary.cleanup()

    def _git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr)
        return result

    def command(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "specromancy",
                "--json",
                "--root",
                str(self.root),
                "--pipeline",
                str(self.pipeline),
                *arguments,
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def payload(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        stream = result.stdout if result.stdout.strip() else result.stderr
        return json.loads(stream)

    def initialize(self, description: str = "Exercise the contract") -> str:
        result = self.command("init", description)
        payload = self.payload(result)
        if result.returncode != 8:
            raise AssertionError((result.returncode, payload))
        return str(payload["action"]["run_id"])

    def start_and_write(self, run_id: str, phase: str, content: str) -> Path:
        started = self.command("phase", run_id, phase)
        if started.returncode != 8:
            raise AssertionError((started.returncode, started.stderr))
        output = Path(self.payload(started)["action"]["output"]["absolute_path"])
        output.write_text(content, encoding="utf-8")
        return output


DEFAULT_ARTIFACTS = {
    "research": (
        "# Research\n## Summary\nKnown.\n## Evidence\nRepository.\n"
        "## Open Questions\nNone.\n"
    ),
    "plan": (
        "# Plan\n## Scope\nSmall.\n## Requirement Mapping\nMapped.\n"
        "## Intended Files\ntracked.txt\n## Tests\nContract.\n"
        "## Verification\nFull suite.\n## Risks and Approvals\nNone.\n"
    ),
    "implement": (
        "# Implementation\n## Changes\nApplied.\n## Deviations\nNone.\n"
        "## Verification\nPassed.\n"
    ),
    "review": (
        "# Review\n## Verdict\nRecorded.\n## Findings\nNone.\n"
        "## Verification\nPassed.\n"
    ),
}


def advance_to(repo: CliRepository, run_id: str, target: str) -> None:
    for phase in ("research", "plan", "implement", "review"):
        if phase == target:
            return
        repo.start_and_write(run_id, phase, DEFAULT_ARTIFACTS[phase])
        arguments = ["validate", run_id, phase]
        if phase == "review":
            arguments.extend(("--outcome", "approved"))
        result = repo.command(*arguments)
        if result.returncode not in (0, 8):
            raise AssertionError((result.returncode, result.stderr))
