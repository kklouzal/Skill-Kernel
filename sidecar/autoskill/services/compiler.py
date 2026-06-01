from __future__ import annotations

import textwrap
from dataclasses import dataclass

from autoskill.core.hashing import sha256_text
from autoskill.core.skillir import SkillIR
from autoskill.services.scanner import ScannerFinding, has_blocking_findings, scan_text


@dataclass(frozen=True)
class CompiledSkill:
    skill_md: str
    sha256: str
    scanner_findings: list[ScannerFinding]

    @property
    def ok(self) -> bool:
        return not has_blocking_findings(self.scanner_findings)


def _bullets(items: list[str]) -> str:
    if not items:
        return "- None."
    return "\n".join(f"- {item.strip()}" for item in items)


def _tool_templates(skill: SkillIR) -> str:
    if not skill.tool_templates:
        return "- None."
    blocks: list[str] = []
    for template in skill.tool_templates:
        caps = ", ".join(template.required_capabilities) or "none"
        blocks.append(
            "\n".join(
                [
                    f"- `{template.name}`: {template.purpose}",
                    f"  - Required capabilities: {caps}",
                    f"  - Template: `{template.template}`",
                ]
            )
        )
    return "\n".join(blocks)


def render_skill_md(skill: SkillIR) -> str:
    frontmatter = textwrap.dedent(
        f"""\
        ---
        name: {skill.name}
        description: "{skill.description}"
        metadata:
          openclaw:
            owner: autoskill
            skill_id: "{skill.skill_id}"
            skillir_schema: "{skill.schema_}"
            compiler_version: "{skill.compiler_version}"
        ---
        """
    )
    body = textwrap.dedent(
        f"""\
        # {skill.name}

        ## WHEN
        {_bullets(skill.applicability)}

        ## INPUTS
        {_bullets(skill.inputs)}

        ## PRECONDITIONS
        {_bullets(skill.preconditions)}

        ## DO
        {_bullets(skill.steps)}

        ## TOOL TEMPLATES
        {_tool_templates(skill)}

        ## VERIFY
        {_bullets(skill.verification)}

        ## FAIL
        {_bullets(skill.failure_handling)}

        ## DO NOT USE WHEN
        {_bullets(skill.do_not_use_when)}

        ## NEVER
        {_bullets(skill.never)}
        """
    )
    return f"{frontmatter}\n{body}".strip() + "\n"


def compile_skill(skill: SkillIR) -> CompiledSkill:
    content = render_skill_md(skill)
    findings = scan_text(content)
    return CompiledSkill(skill_md=content, sha256=sha256_text(content), scanner_findings=findings)

