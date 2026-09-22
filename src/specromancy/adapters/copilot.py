"""GitHub Copilot adapter."""

from __future__ import annotations

from pathlib import Path

from .base import (
    CANONICAL_SKILLS,
    AdapterBase,
    GeneratedFile,
    generated_header,
)
from ..io import read_text


class CopilotAdapter(AdapterBase):
    name = "copilot"

    def render(self, root: Path) -> tuple[GeneratedFile, ...]:
        self.validate_sources(root)
        source = "AGENTS.md"
        outputs = [
            GeneratedFile.text(
                path=".github/copilot-instructions.md",
                harness=self.name,
                sources=(source,),
                transformation="normalized-mirror-with-provenance",
                content=generated_header(self.name, (source,)) + read_text(root / source),
            )
        ]
        for skill in CANONICAL_SKILLS:
            skill_source = f".agents/skills/{skill}/SKILL.md"
            content = f"""---
description: Run the canonical Specromancy {skill} workflow
---

{generated_header(self.name, (skill_source,)).rstrip()}

Load [`{skill_source}`](../../{skill_source}) and follow it exactly. Treat that file and the Specromancy CLI as the authorities; do not restate or invent workflow policy here.

Use the run ID supplied by the user. If it is missing, ask for it before running a phase command.
"""
            outputs.append(
                GeneratedFile.text(
                    path=f".github/prompts/{skill}.prompt.md",
                    harness=self.name,
                    sources=(skill_source,),
                    transformation="thin-prompt-launcher",
                    content=content,
                )
            )
        return tuple(outputs)

    def managed_candidates(self, root: Path) -> tuple[Path, ...]:
        candidates = [root / ".github" / "copilot-instructions.md"]
        prompt_root = root / ".github" / "prompts"
        if prompt_root.is_dir():
            candidates.extend(path for path in prompt_root.rglob("*") if path.is_file())
        return tuple(candidates)
