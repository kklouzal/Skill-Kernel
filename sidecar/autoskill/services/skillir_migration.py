from __future__ import annotations

from typing import Any
from uuid import UUID

from autoskill.core.hashing import sha256_json
from autoskill.core.skillir import SkillIR
from autoskill.services.candidates import CandidateProposalResult, CandidateSkillProposal
from autoskill.services.compiler import compile_skill, description_style_errors_for
from autoskill.services.probes import plan_candidate_probes
from pydantic import ValidationError

MIGRATION_COMPILER_VERSION = "autoskill-compiler.v1.migration"

_SEMANTIC_FIELDS = (
    "schema",
    "skill_id",
    "slug",
    "name",
    "description",
    "applicability",
    "inputs",
    "preconditions",
    "steps",
    "outputs",
    "effects",
    "state_delta",
    "side_effects",
    "termination",
    "idempotency",
    "unsafe_when",
    "tool_templates",
    "verification",
    "failure_handling",
    "failure_modes",
    "do_not_use_when",
    "never",
    "dependencies",
    "conflicts",
    "environment_contracts",
    "runtime_guards",
    "support_artifacts",
    "evidence_ids",
    "required_capabilities",
)


def propose_skill_ir_migration(
    *,
    source_skill_ir: SkillIR | dict[str, Any],
    source_revision_id: UUID,
    migration_reason: str,
    compiler_version: str = MIGRATION_COMPILER_VERSION,
) -> CandidateProposalResult:
    """Build a gated, inactive candidate revision for a deterministic SkillIR migration."""
    reason = " ".join(migration_reason.split())
    source = _parse_source_skill_ir(source_skill_ir)
    candidate_slug = source.slug if source else _candidate_slug_from_payload(source_skill_ir)
    if source is None:
        return _skipped(candidate_slug, "source SkillIR is invalid")
    if not reason:
        return _skipped(candidate_slug, "migration reason is required")
    if not compiler_version.strip():
        return _skipped(candidate_slug, "compiler version is required")

    style_errors = description_style_errors_for(source.description)
    if style_errors:
        return _skipped(
            candidate_slug,
            f"description_style_invalid: {', '.join(style_errors)}",
        )

    source_payload = source.model_dump(by_alias=True, mode="json")
    source_semantics = _semantic_payload(source)
    source_semantic_hash = sha256_json(source_semantics)
    source_skillir_hash = sha256_json(source_payload)
    migrated = source.model_copy(
        update={
            "version": source.version + 1,
            "compiler_version": compiler_version.strip(),
            "risk_notes": [
                *source.risk_notes,
                f"SkillIR migration from {source_revision_id}: {reason}",
            ],
        }
    )
    migrated_semantics = _semantic_payload(migrated)
    migrated_semantic_hash = sha256_json(migrated_semantics)
    if source_semantics != migrated_semantics:
        changed = [
            field
            for field in _SEMANTIC_FIELDS
            if source_semantics.get(field) != migrated_semantics.get(field)
        ]
        return _skipped(
            candidate_slug,
            f"semantic_preservation_failed: {', '.join(changed)}",
        )

    compiled = compile_skill(migrated)
    migration_identity = sha256_json(
        {
            "schema": "autoskill.skillir-migration.v1",
            "source_revision_id": str(source_revision_id),
            "source_skillir_hash": source_skillir_hash,
            "compiler_version": compiler_version.strip(),
            "migration_reason": reason,
        }
    )
    proposal = CandidateSkillProposal(
        candidate_slug=migrated.slug,
        recommendation="propose_migration",
        evidence_ids=migrated.evidence_ids,
        skipped_reason=None,
        skillir=migrated,
        compiled_runtime_text=compiled.skill_md,
        compiled_sha256=compiled.sha256,
        scanner_findings=[
            {
                "severity": str(finding.severity),
                "code": finding.code,
                "message": finding.message,
            }
            for finding in compiled.scanner_findings
        ],
        probe_plan=plan_candidate_probes(migrated),
        metadata={
            "proposal_kind": "skill_ir_migration",
            "migration_identity": migration_identity,
            "source_revision_id": str(source_revision_id),
            "source_skillir_hash": source_skillir_hash,
            "source_semantic_hash": source_semantic_hash,
            "candidate_semantic_hash": migrated_semantic_hash,
            "compiler_version": compiler_version.strip(),
            "migration_reason": reason,
            "semantic_preservation": {
                "status": "passed",
                "preserved_fields": list(_SEMANTIC_FIELDS),
            },
            "rollback_action": {
                "reactivate_source_revision_id": str(source_revision_id),
                "archive_candidate_revision": True,
            },
        },
    )
    return CandidateProposalResult(
        scanned=1,
        proposed=1,
        skipped=0,
        proposals=[proposal],
    )


def _parse_source_skill_ir(payload: SkillIR | dict[str, Any]) -> SkillIR | None:
    if isinstance(payload, SkillIR):
        return payload
    try:
        return SkillIR.model_validate(payload)
    except ValidationError:
        return None


def _candidate_slug_from_payload(payload: SkillIR | dict[str, Any]) -> str:
    if isinstance(payload, SkillIR):
        return payload.slug
    slug = payload.get("slug") if isinstance(payload, dict) else None
    return slug if isinstance(slug, str) and slug else "unknown-skillir-migration"


def _semantic_payload(skill: SkillIR) -> dict[str, Any]:
    payload = skill.model_dump(by_alias=True, mode="json")
    return {field: payload.get(field) for field in _SEMANTIC_FIELDS}


def _skipped(candidate_slug: str, reason: str) -> CandidateProposalResult:
    return CandidateProposalResult(
        scanned=1,
        proposed=0,
        skipped=1,
        proposals=[
            CandidateSkillProposal(
                candidate_slug=candidate_slug,
                recommendation="skip_migration",
                evidence_ids=[],
                skipped_reason=reason,
                skillir=None,
                compiled_runtime_text=None,
                compiled_sha256=None,
                scanner_findings=[],
                probe_plan=[],
                metadata={
                    "proposal_kind": "skill_ir_migration",
                    "fail_closed": True,
                    "reason": reason,
                },
            )
        ],
    )
