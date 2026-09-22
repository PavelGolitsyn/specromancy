"""OpenCode adapter."""

from __future__ import annotations

from pathlib import Path

from .base import CANONICAL_SKILLS, AdapterBase, GeneratedFile, generated_header


class OpenCodeAdapter(AdapterBase):
    name = "opencode"

    def render(self, root: Path) -> tuple[GeneratedFile, ...]:
        self.validate_sources(root)
        outputs: list[GeneratedFile] = []
        for skill in CANONICAL_SKILLS:
            skill_source = f".agents/skills/{skill}/SKILL.md"
            content = f"""---
description: Run the canonical Specromancy {skill} workflow
---

{generated_header(self.name, (skill_source,)).rstrip()}

Load `{skill_source}` and follow it exactly. Treat that skill and the Specromancy CLI as the authorities; do not restate or invent workflow policy here.

Operate on the run ID supplied in `$ARGUMENTS`. If `$ARGUMENTS` is empty, ask for the run ID before running a phase command.
"""
            outputs.append(
                GeneratedFile.text(
                    path=f".opencode/commands/{skill}.md",
                    harness=self.name,
                    sources=(skill_source,),
                    transformation="thin-command-launcher",
                    content=content,
                )
            )
        return tuple(outputs)

    def managed_candidates(self, root: Path) -> tuple[Path, ...]:
        command_root = root / ".opencode" / "commands"
        if not command_root.is_dir():
            return ()
        return tuple(path for path in command_root.rglob("*") if path.is_file())
