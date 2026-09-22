"""Claude Code adapter."""

from __future__ import annotations

from pathlib import Path

from .base import AdapterBase, GeneratedFile, copy_skill_outputs, generated_header
from ..io import read_text


class ClaudeAdapter(AdapterBase):
    name = "claude"

    def render(self, root: Path) -> tuple[GeneratedFile, ...]:
        self.validate_sources(root)
        source = "AGENTS.md"
        instructions = GeneratedFile.text(
            path="CLAUDE.md",
            harness=self.name,
            sources=(source,),
            transformation="normalized-mirror-with-provenance",
            content=generated_header(self.name, (source,)) + read_text(root / source),
        )
        return (instructions, *copy_skill_outputs(root, self.name))

    def managed_candidates(self, root: Path) -> tuple[Path, ...]:
        candidates = [root / "CLAUDE.md"]
        skill_root = root / ".claude" / "skills"
        if skill_root.is_dir():
            candidates.extend(path for path in skill_root.rglob("*") if path.is_file())
        return tuple(candidates)
