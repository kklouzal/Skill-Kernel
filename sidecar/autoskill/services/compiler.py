from __future__ import annotations

import textwrap
from dataclasses import dataclass
from math import ceil

from autoskill.core.hashing import sha256_text
from autoskill.core.skillir import SkillIR
from autoskill.services.scanner import ScannerFinding, has_blocking_findings, scan_text

DEFAULT_MAX_CONTEXT_TOKENS = 1200


@dataclass(frozen=True)
class CompiledSkill:
    skill_md: str
    sha256: str
    scanner_findings: list[ScannerFinding]
    estimated_tokens: int
    max_context_tokens: int

    @property
    def ok(self) -> bool:
        return (
            not has_blocking_findings(self.scanner_findings)
            and self.estimated_tokens <= self.max_context_tokens
        )

    @property
    def token_over_budget(self) -> bool:
        return self.estimated_tokens > self.max_context_tokens


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

        ## OUTPUTS
        {_bullets(skill.outputs)}

        ## EFFECTS
        {_bullets(skill.effects)}

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


def compile_skill(
    skill: SkillIR,
    *,
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
) -> CompiledSkill:
    content = render_skill_md(skill)
    # Generated runtime text is only the prompt-facing projection. Scan the full
    # SkillIR too, because non-rendered fields can still affect routing and future
    # generated artifacts.
    skill_ir_text = skill.model_dump_json(by_alias=True)
    findings = [*scan_text(content), *scan_text(skill_ir_text)]
    return CompiledSkill(
        skill_md=content,
        sha256=sha256_text(content),
        scanner_findings=findings,
        estimated_tokens=_estimate_tokens(content),
        max_context_tokens=max(1, max_context_tokens),
    )


def _estimate_tokens(text: str) -> int:
    # Conservative local estimate; real provider tokenizers can replace this later.
    return ceil(len(text) / 4)
