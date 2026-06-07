from __future__ import annotations

import textwrap
from dataclasses import dataclass
from math import ceil
from uuid import UUID

from autoskill.core.hashing import sha256_json, sha256_text
from autoskill.core.skillir import SkillIR, SupportArtifact
from autoskill.db.autonomy import AutonomyControlStore
from autoskill.db.context import ContextGovernanceStore
from autoskill.services.scanner import ScannerFinding, has_blocking_findings, scan_text

DEFAULT_MAX_CONTEXT_TOKENS = 1200
DEFAULT_DESCRIPTION_MAX_CHARS = 160
CONTEXT_COMPILER_VERSION = "autoskill-context-compiler.v1"


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


@dataclass(frozen=True)
class ContextCompilationResult:
    compiled: CompiledSkill
    context_artifact: dict[str, object]
    support_context_artifacts: list[dict[str, object]]
    compile_run: dict[str, object]
    budget_event: dict[str, object]
    semantic_compression_trial: dict[str, object]
    calibration_observation: dict[str, object] | None
    status: str
    reject_reason: str | None
    required_requirements: int
    preserved_requirements: int
    lost_requirements: int
    added_unsupported_requirements: int
    semantic_equivalence_score: float

    def to_json(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reject_reason": self.reject_reason,
            "compiled_sha256": self.compiled.sha256,
            "estimated_tokens": self.compiled.estimated_tokens,
            "max_context_tokens": self.compiled.max_context_tokens,
            "scanner_findings": [
                {
                    "severity": str(finding.severity),
                    "code": finding.code,
                    "message": finding.message,
                }
                for finding in self.compiled.scanner_findings
            ],
            "required_requirements": self.required_requirements,
            "preserved_requirements": self.preserved_requirements,
            "lost_requirements": self.lost_requirements,
            "added_unsupported_requirements": self.added_unsupported_requirements,
            "semantic_equivalence_score": self.semantic_equivalence_score,
            "context_artifact": self.context_artifact,
            "support_context_artifacts": self.support_context_artifacts,
            "compile_run": self.compile_run,
            "budget_event": self.budget_event,
            "semantic_compression_trial": self.semantic_compression_trial,
            "calibration_observation": self.calibration_observation,
        }


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


def _runtime_guards(skill: SkillIR) -> str:
    if not skill.runtime_guards:
        return "- None."
    blocks: list[str] = []
    for guard in skill.runtime_guards:
        caps = ", ".join(guard.required_capabilities) or "none"
        blocks.append(
            "\n".join(
                [
                    f"- `{guard.template_id}` ({guard.mode}): {guard.condition_summary}",
                    f"  - Message: {guard.operator_message}",
                    f"  - Required capabilities: {caps}",
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
            granularity: "{skill.granularity}"
            scope: "{skill.scope}"
            topology_role: "{skill.topology_role}"
            component_policy: "{skill.component_policy}"
            runtime_visibility_policy: "{skill.runtime_visibility_policy}"
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

        ## RUNTIME GUARDS
        {_runtime_guards(skill)}

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


async def compile_skill_with_context_governance(
    skill: SkillIR,
    store: ContextGovernanceStore,
    *,
    workspace_key: str,
    autonomy: AutonomyControlStore | None = None,
    skill_id: UUID | None = None,
    skill_version_id: UUID | None = None,
    candidate_id: UUID | None = None,
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    target_runtime_tokens: int = 350,
    description_max_chars: int = DEFAULT_DESCRIPTION_MAX_CHARS,
    source_object_type: str = "skill_version",
    source_object_id: UUID | None = None,
    compiler_version: str = CONTEXT_COMPILER_VERSION,
    require_probe_evidence: bool = False,
    routing_equivalence_evidence: dict[str, object] | None = None,
    regression_evidence: dict[str, object] | None = None,
) -> ContextCompilationResult:
    """Compile SkillIR and persist v16 context-gate governance records.

    This is a deterministic control-plane helper only. It records artifact,
    budget, and semantic-equivalence evidence; it does not stage or activate
    runtime files.
    """

    compiled = compile_skill(skill, max_context_tokens=max_context_tokens)
    source_object_id = source_object_id or skill_version_id or candidate_id
    requirements = _required_runtime_requirements(skill)
    preserved = [requirement for requirement in requirements if requirement in compiled.skill_md]
    lost_requirements = len(requirements) - len(preserved)
    added_unsupported_requirements = 0
    semantic_equivalence_score = 1.0 if requirements and lost_requirements == 0 else 0.0
    description_over_budget = len(skill.description) > max(1, description_max_chars)
    description_style_errors = description_style_errors_for(skill.description)
    blocking_scanner = has_blocking_findings(compiled.scanner_findings)
    probe_reject_reason = _probe_reject_reason(
        require_probe_evidence=require_probe_evidence,
        routing_equivalence_evidence=routing_equivalence_evidence,
        regression_evidence=regression_evidence,
    )
    reject_reason = _context_reject_reason(
        blocking_scanner=blocking_scanner,
        description_over_budget=description_over_budget,
        description_style_invalid=bool(description_style_errors),
        token_over_budget=compiled.token_over_budget,
        lost_requirements=lost_requirements,
        probe_reject_reason=probe_reject_reason,
    )
    status = "passed" if reject_reason is None else "failed"
    safety_status = "blocked" if blocking_scanner else "passed"
    equivalence_status = (
        "passed" if lost_requirements == 0 and probe_reject_reason is None else "failed"
    )

    artifact = await store.record_artifact(
        workspace_key=workspace_key,
        artifact_kind="skill_md",
        source_object_type=source_object_type,
        source_object_id=source_object_id,
        skill_id=skill_id,
        skill_version_id=skill_version_id,
        text=compiled.skill_md,
        max_tokens=max_context_tokens,
        safety_status=safety_status,
        equivalence_status=equivalence_status,
        shadowing_status="pending",
        metadata={
            "loadability_class": "runtime_on_skill_load",
            "compiler": compiler_version,
            "skill_slug": skill.slug,
            "granularity": skill.granularity,
            "scope": skill.scope,
            "topology_role": skill.topology_role,
            "component_policy": skill.component_policy,
            "runtime_visibility_policy": skill.runtime_visibility_policy,
            "description_char_count": len(skill.description),
            "description_max_chars": max(1, description_max_chars),
            "description_style_status": (
                "failed" if description_style_errors else "passed"
            ),
            "description_style_errors": description_style_errors,
            "required_requirements": len(requirements),
            "preserved_requirements": len(preserved),
            "lost_requirements": lost_requirements,
            "scanner_codes": [finding.code for finding in compiled.scanner_findings],
            "probe_evidence_required": require_probe_evidence,
            "runtime_guard_count": len(skill.runtime_guards),
            "runtime_guard_templates": [
                guard.template_id for guard in skill.runtime_guards
            ],
            "routing_equivalence_evidence": _safe_gate_evidence(
                routing_equivalence_evidence
            ),
            "regression_evidence": _safe_gate_evidence(regression_evidence),
        },
    )
    support_artifacts = await _record_support_context_artifacts(
        skill,
        store,
        workspace_key=workspace_key,
        source_object_type=source_object_type,
        source_object_id=source_object_id,
        skill_id=skill_id,
        skill_version_id=skill_version_id,
        compiler_version=compiler_version,
    )

    manifest = {
        "schema": "autoskill.context-compile-manifest.v1",
        "compiler_version": compiler_version,
        "skill_slug": skill.slug,
        "granularity": skill.granularity,
        "scope": skill.scope,
        "topology_role": skill.topology_role,
        "component_policy": skill.component_policy,
        "runtime_visibility_policy": skill.runtime_visibility_policy,
        "compiled_sha256": compiled.sha256,
        "support_artifact_count": len(support_artifacts),
        "runtime_guard_count": len(skill.runtime_guards),
        "support_artifact_hashes": [
            artifact["text_hash"] for artifact in support_artifacts
        ],
        "loadability_class": "runtime_on_skill_load",
        "token_count": compiled.estimated_tokens,
        "max_tokens": max_context_tokens,
        "status": status,
        "reject_reason": reject_reason,
        "probe_evidence_required": require_probe_evidence,
    }
    compile_run = await store.record_compile_run(
        workspace_key=workspace_key,
        compiler_version=compiler_version,
        input_skillir_hash=sha256_text(skill.model_dump_json(by_alias=True)),
        output_manifest_hash=sha256_json(manifest),
        actual_runtime_tokens=compiled.estimated_tokens,
        status=status,
        skill_id=skill_id,
        skill_version_id=skill_version_id,
        candidate_id=candidate_id,
        context_artifact_id=artifact.context_artifact_id,
        target_runtime_tokens=target_runtime_tokens,
        compression_ratio=_compression_ratio(
            source_tokens=_estimate_tokens(skill.model_dump_json(by_alias=True)),
            candidate_tokens=compiled.estimated_tokens,
        ),
        semantic_equivalence_score=semantic_equivalence_score,
        reject_reason=reject_reason,
        metadata={
            "loadability_class": "runtime_on_skill_load",
            "budget_status": artifact.budget_status,
            "safety_status": safety_status,
            "equivalence_status": equivalence_status,
            "granularity": skill.granularity,
            "scope": skill.scope,
            "topology_role": skill.topology_role,
            "component_policy": skill.component_policy,
            "runtime_visibility_policy": skill.runtime_visibility_policy,
            "description_over_budget": description_over_budget,
            "description_style_status": (
                "failed" if description_style_errors else "passed"
            ),
            "description_style_errors": description_style_errors,
            "model_assist_used": False,
            "probe_evidence_required": require_probe_evidence,
            "probe_reject_reason": probe_reject_reason,
            "support_artifact_count": len(support_artifacts),
            "runtime_guard_count": len(skill.runtime_guards),
            "support_artifact_hashes": [
                artifact["text_hash"] for artifact in support_artifacts
            ],
        },
    )
    budget_event = await store.record_budget_event(
        workspace_key=workspace_key,
        event_type="compile_budget_gate",
        decision="accept" if status == "passed" else "reject_change",
        skill_id=skill_id,
        skill_version_id=skill_version_id,
        context_artifact_id=artifact.context_artifact_id,
        tokens_delta=compiled.estimated_tokens - max(1, target_runtime_tokens),
        evidence={
            "gate": "token_budget_governor",
            "target_runtime_tokens": max(1, target_runtime_tokens),
            "max_context_tokens": max(1, max_context_tokens),
            "actual_runtime_tokens": compiled.estimated_tokens,
            "budget_status": artifact.budget_status,
            "reject_reason": reject_reason,
        },
        metadata={"compiler_version": compiler_version, "skill_slug": skill.slug},
    )
    compression_trial = await store.record_semantic_compression_trial(
        workspace_key=workspace_key,
        skill_id=skill_id,
        source_revision_id=None,
        candidate_revision_id=skill_version_id,
        source_tokens=_estimate_tokens(skill.model_dump_json(by_alias=True)),
        candidate_tokens=compiled.estimated_tokens,
        preserved_requirements=len(preserved),
        lost_requirements=lost_requirements,
        added_unsupported_requirements=added_unsupported_requirements,
        equivalence_score=semantic_equivalence_score,
        status="passed" if equivalence_status == "passed" else "failed",
        candidate_context_artifact_id=artifact.context_artifact_id,
        metadata={
            "compiler_version": compiler_version,
            "skill_slug": skill.slug,
            "method": "deterministic_exact_requirement_render",
            "probe_evidence_required": require_probe_evidence,
            "description_style_status": (
                "failed" if description_style_errors else "passed"
            ),
            "description_style_errors": description_style_errors,
            "routing_equivalence_evidence": _safe_gate_evidence(
                routing_equivalence_evidence
            ),
            "regression_evidence": _safe_gate_evidence(regression_evidence),
        },
    )
    calibration_observation = await _record_context_equivalence_calibration(
        autonomy,
        workspace_key=workspace_key,
        skill=skill,
        compiled=compiled,
        artifact_id=UUID(str(artifact.context_artifact_id)),
        compile_run_id=UUID(str(compile_run.context_compile_run_id)),
        compression_trial_id=UUID(
            str(compression_trial.semantic_compression_trial_id)
        ),
        status=status,
        reject_reason=reject_reason,
        lost_requirements=lost_requirements,
        preserved_requirements=len(preserved),
        required_requirements=len(requirements),
        semantic_equivalence_score=semantic_equivalence_score,
        require_probe_evidence=require_probe_evidence,
        probe_reject_reason=probe_reject_reason,
        routing_equivalence_evidence=routing_equivalence_evidence,
        regression_evidence=regression_evidence,
    )
    return ContextCompilationResult(
        compiled=compiled,
        context_artifact=artifact.to_json(),
        support_context_artifacts=support_artifacts,
        compile_run=compile_run.to_json(),
        budget_event=budget_event.to_json(),
        semantic_compression_trial=compression_trial.to_json(),
        calibration_observation=(
            calibration_observation.to_json() if calibration_observation else None
        ),
        status=status,
        reject_reason=reject_reason,
        required_requirements=len(requirements),
        preserved_requirements=len(preserved),
        lost_requirements=lost_requirements,
        added_unsupported_requirements=added_unsupported_requirements,
        semantic_equivalence_score=semantic_equivalence_score,
    )


async def _record_context_equivalence_calibration(
    autonomy: AutonomyControlStore | None,
    *,
    workspace_key: str,
    skill: SkillIR,
    compiled: CompiledSkill,
    artifact_id: UUID,
    compile_run_id: UUID,
    compression_trial_id: UUID,
    status: str,
    reject_reason: str | None,
    lost_requirements: int,
    preserved_requirements: int,
    required_requirements: int,
    semantic_equivalence_score: float,
    require_probe_evidence: bool,
    probe_reject_reason: str | None,
    routing_equivalence_evidence: dict[str, object] | None,
    regression_evidence: dict[str, object] | None,
):
    if autonomy is None:
        return None
    selected_action = _context_calibration_action(status, reject_reason)
    confidence_components = {
        "schema": "autoskill.context-equivalence-calibration-components.v1",
        "compiler_version": CONTEXT_COMPILER_VERSION,
        "skill_slug": skill.slug,
        "artifact_kind": "skill_md",
        "context_artifact_id": str(artifact_id),
        "context_compile_run_id": str(compile_run_id),
        "semantic_compression_trial_id": str(compression_trial_id),
        "compile_status": status,
        "reject_reason": reject_reason,
        "budget_status": "over_budget" if compiled.token_over_budget else "passed",
        "scanner_blocked": has_blocking_findings(compiled.scanner_findings),
        "scanner_codes": [finding.code for finding in compiled.scanner_findings],
        "estimated_tokens": compiled.estimated_tokens,
        "max_context_tokens": compiled.max_context_tokens,
        "required_requirements": required_requirements,
        "preserved_requirements": preserved_requirements,
        "lost_requirements": lost_requirements,
        "semantic_equivalence_score": semantic_equivalence_score,
        "probe_evidence_required": require_probe_evidence,
        "probe_reject_reason": probe_reject_reason,
        "routing_equivalence_evidence": _safe_gate_evidence(
            routing_equivalence_evidence
        ),
        "regression_evidence": _safe_gate_evidence(regression_evidence),
        "llm_authority": "none",
        "runtime_write_authority": False,
    }
    return await autonomy.record_calibration_observation(
        workspace_key=workspace_key,
        calibration_family="context_budget_semantic_equivalence",
        selected_action=selected_action,
        predicted_confidence=semantic_equivalence_score,
        confidence_components=confidence_components,
        action_risk_tier="T1_internal_record",
    )


def _context_calibration_action(status: str, reject_reason: str | None) -> str:
    if status == "passed":
        return "accept_context_artifact"
    if reject_reason in {"scanner_blocked", "semantic_loss"}:
        return "auto_reject"
    return "compile_more_conservatively"


async def _record_support_context_artifacts(
    skill: SkillIR,
    store: ContextGovernanceStore,
    *,
    workspace_key: str,
    source_object_type: str,
    source_object_id: UUID | None,
    skill_id: UUID | None,
    skill_version_id: UUID | None,
    compiler_version: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for artifact in skill.support_artifacts:
        excerpt = _support_artifact_context_excerpt(artifact)
        findings = scan_text(excerpt)
        safety_status = "blocked" if has_blocking_findings(findings) else "passed"
        record = await store.record_artifact(
            workspace_key=workspace_key,
            artifact_kind="support_excerpt",
            source_object_type=f"{source_object_type}_support_artifact",
            source_object_id=source_object_id,
            skill_id=skill_id,
            skill_version_id=skill_version_id,
            text=excerpt,
            max_tokens=120,
            safety_status=safety_status,
            equivalence_status="passed",
            shadowing_status="pending",
            metadata={
                "loadability_class": f"support_artifact:{artifact.load_policy}",
                "compiler": compiler_version,
                "skill_slug": skill.slug,
                "support_path": artifact.path,
                "support_kind": artifact.kind,
                "support_load_policy": artifact.load_policy,
                "declared_sha256": artifact.sha256,
                "declared_capabilities": list(artifact.capabilities),
                "retrieval_boundary": _support_retrieval_boundary(artifact.load_policy),
                "scanner_codes": [finding.code for finding in findings],
                "source": "skillir_support_artifact_declaration",
            },
        )
        records.append(record.to_json())
    return records


def _support_artifact_context_excerpt(artifact: SupportArtifact) -> str:
    capabilities = ", ".join(sorted(artifact.capabilities)) or "none"
    declared_hash = artifact.sha256 or "not-declared"
    return "\n".join(
        [
            f"path: {artifact.path}",
            f"kind: {artifact.kind}",
            f"load_policy: {artifact.load_policy}",
            f"declared_capabilities: {capabilities}",
            f"declared_sha256: {declared_hash}",
        ]
    )


def _support_retrieval_boundary(load_policy: str) -> str:
    if load_policy == "agent_may_read":
        return "may_render_after_budget_and_scanner_gates"
    if load_policy == "broker_excerpt_only":
        return "broker_summary_only"
    return "not_runtime_context_loadable"


def _estimate_tokens(text: str) -> int:
    # Conservative local estimate; real provider tokenizers can replace this later.
    return ceil(len(text) / 4)


def _required_runtime_requirements(skill: SkillIR) -> list[str]:
    fields = (
        skill.applicability,
        skill.inputs,
        skill.preconditions,
        skill.steps,
        skill.outputs,
        skill.effects,
        skill.verification,
        skill.failure_handling,
        skill.do_not_use_when,
        skill.never,
    )
    return [item.strip() for values in fields for item in values if item.strip()]


def _context_reject_reason(
    *,
    blocking_scanner: bool,
    description_over_budget: bool,
    description_style_invalid: bool,
    token_over_budget: bool,
    lost_requirements: int,
    probe_reject_reason: str | None = None,
) -> str | None:
    if blocking_scanner:
        return "scanner_blocked"
    if description_over_budget:
        return "description_over_budget"
    if description_style_invalid:
        return "description_style_invalid"
    if token_over_budget:
        return "over_context_budget"
    if lost_requirements:
        return "semantic_loss"
    if probe_reject_reason:
        return probe_reject_reason
    return None


def description_style_errors_for(description: str) -> list[str]:
    text = " ".join(description.strip().split())
    lowered = text.lower()
    clauses = [clause.strip() for clause in lowered.split(";") if clause.strip()]
    errors: list[str] = []
    if len(clauses) < 3:
        errors.append("description_requires_action_use_when_not_for_clauses")
    first_clause = clauses[0] if clauses else ""
    if (
        len(first_clause.split()) < 2
        or first_clause.startswith("use when ")
        or first_clause.startswith("not for ")
    ):
        errors.append("description_action_clause_missing")
    use_when = next(
        (clause for clause in clauses if clause.startswith("use when ")),
        None,
    )
    if use_when is None:
        errors.append("description_use_when_clause_missing")
    elif len(use_when.removeprefix("use when ").split()) < 3:
        errors.append("description_use_when_clause_too_broad")
    not_for = next(
        (clause for clause in clauses if clause.startswith("not for ")),
        None,
    )
    if not_for is None:
        errors.append("description_not_for_clause_missing")
    elif len(not_for.removeprefix("not for ").split()) < 3:
        errors.append("description_not_for_clause_too_broad")
    return errors


def _probe_reject_reason(
    *,
    require_probe_evidence: bool,
    routing_equivalence_evidence: dict[str, object] | None,
    regression_evidence: dict[str, object] | None,
) -> str | None:
    if not require_probe_evidence:
        return None
    routing = routing_equivalence_evidence or {}
    regression = regression_evidence or {}
    required = (
        routing.get("positive_routing_passed") is True,
        routing.get("negative_routing_passed") is True,
        routing.get("information_preservation_passed") is True,
        regression.get("regression_passed") is True,
    )
    return None if all(required) else "needs_probe_evidence"


def _safe_gate_evidence(evidence: dict[str, object] | None) -> dict[str, object]:
    if not evidence:
        return {}
    allowed_keys = {
        "positive_routing_passed",
        "negative_routing_passed",
        "information_preservation_passed",
        "regression_passed",
        "probe_set_version",
        "probe_count",
        "passed_count",
        "failed_count",
        "evidence_hash",
        "notes_hash",
    }
    safe: dict[str, object] = {}
    for key in allowed_keys:
        value = evidence.get(key)
        if isinstance(value, bool | int | float | str):
            safe[key] = value
    return safe


def _compression_ratio(*, source_tokens: int, candidate_tokens: int) -> float:
    return candidate_tokens / max(source_tokens, 1)
