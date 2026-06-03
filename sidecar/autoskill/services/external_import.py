from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from autoskill.core.hashing import sha256_json
from autoskill.core.skillir import SkillIR
from autoskill.db.external_skills import ExternalSkillRecord, ExternalSkillStore


@dataclass(frozen=True)
class ExternalSkillImportMaterialization:
    allowed: bool
    external_skill_id: UUID | None
    blockers: list[str]
    candidate: dict[str, Any] | None = None
    review_action: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "external_skill_id": str(self.external_skill_id) if self.external_skill_id else None,
            "blockers": self.blockers,
            "candidate": self.candidate,
            "review_action": self.review_action,
        }


async def materialize_external_skill_import(
    store: ExternalSkillStore,
    *,
    workspace_key: str,
    external_skill_id: UUID,
    operator_id: str | None = None,
) -> ExternalSkillImportMaterialization:
    records = await store.list_external_skills(workspace_key=workspace_key, limit=500)
    record = next(
        (item for item in records if item.external_skill_id == external_skill_id),
        None,
    )
    if record is None:
        return ExternalSkillImportMaterialization(
            allowed=False,
            external_skill_id=external_skill_id,
            blockers=["external skill not found"],
        )
    blockers = _import_blockers(record)
    approved = await store.list_review_actions(
        workspace_key=workspace_key,
        external_skill_id=external_skill_id,
        action="import",
        status="approved",
        limit=1,
    )
    if not approved:
        blockers.append("external skill import requires approved operator review action")
    if blockers:
        return ExternalSkillImportMaterialization(
            allowed=False,
            external_skill_id=external_skill_id,
            blockers=blockers,
        )

    candidate = _candidate_manifest(record)
    review = await store.record_review_action(
        workspace_key=workspace_key,
        external_skill_id=external_skill_id,
        action="import",
        status="completed",
        operator_id=operator_id or approved[0].operator_id,
        rationale="operator-approved external skill import materialized as staged candidate",
        metadata={
            "materialization": {
                "mode": "stage_only",
                "mutates_external_root": False,
                "candidate_hash": sha256_json(candidate),
                "candidate": candidate,
            }
        },
    )
    return ExternalSkillImportMaterialization(
        allowed=True,
        external_skill_id=external_skill_id,
        blockers=[],
        candidate=candidate,
        review_action=review.to_json(),
    )


def _import_blockers(record: ExternalSkillRecord) -> list[str]:
    blockers: list[str] = []
    if record.status in {"quarantined", "missing", "ignored"}:
        blockers.append(f"external skill status is not importable: {record.status}")
    scanner_status = str(record.risk_summary.get("scanner_status", "unknown"))
    if scanner_status not in {"passed", "clean"}:
        blockers.append(f"external skill scanner status is not passed: {scanner_status}")
    return blockers


def _candidate_manifest(record: ExternalSkillRecord) -> dict[str, Any]:
    imported_slug = f"external-{record.slug}".lower().replace("_", "-")
    original_description = record.description or record.name or record.slug
    description = (
        "Stage external skill import; use when an operator approved a scanned "
        "external skill; not for mutating external-owned roots."
    )
    skill_ir = SkillIR(
        slug=imported_slug,
        name=imported_slug,
        description=description,
        applicability=[
            (
                "An operator approved importing a scanned external skill as a "
                "SkillKernel-owned staged candidate."
            ),
            f"External skill summary: {original_description}",
        ],
        inputs=[
            "Approved external skill inventory record.",
            "Scanner-passed external skill metadata.",
        ],
        preconditions=[
            "An operator import review action is approved.",
            "The external skill scanner status is passed or clean.",
            "The external-owned root remains read-only.",
        ],
        steps=[
            "Preserve the external skill identity as source metadata.",
            "Create only a stage-only SkillKernel candidate manifest.",
            "Run normal scanner, compiler, evaluator, and activation gates before use.",
        ],
        outputs=["A stage-only SkillIR candidate derived from external skill metadata."],
        effects=["No active runtime files or external-owned roots are modified."],
        state_delta=["May create SkillKernel-owned candidate metadata after normal gates."],
        side_effects=["Does not write to or mutate the external skill source root."],
        termination=["Stop after candidate materialization metadata is recorded."],
        idempotency="retry_safe",
        verification=[
            "Confirm scanner, compiler, evaluator, and activation gates pass before activation.",
            "Confirm the candidate manifest keeps mutates_external_root=false.",
        ],
        failure_handling=[
            "Block import when operator approval or scanner-pass evidence is missing.",
            "Leave the external skill inventory read-only when gates fail.",
        ],
        failure_modes=[
            "External skill metadata is stale, quarantined, missing, or scanner-blocked.",
        ],
        do_not_use_when=[
            "The external skill lacks operator import approval.",
            "The external skill is quarantined, missing, ignored, or scanner-blocked.",
        ],
        never=[
            "Do not mutate external-owned skill roots during import materialization.",
            "Do not activate imported runtime files before SkillKernel gates pass.",
        ],
        evidence_ids=[str(record.external_skill_id)],
        risk_notes=["External source remains read-only; import is stage-only."],
    ).model_dump(by_alias=True, mode="json")
    external_source = {
        "kind": "external_skill_import",
        "external_skill_id": str(record.external_skill_id),
        "source": record.source,
        "root_path_hash": record.root_path_hash,
        "file_hash": record.file_hash,
        "original_slug": record.slug,
        "original_name": record.name,
        "original_description_hash": sha256_json({"description": original_description}),
    }
    return {
        "schema": "autoskill.external_import_candidate.v1",
        "mode": "stage_only",
        "mutates_external_root": False,
        "skill_ir": skill_ir,
        "external_source": external_source,
        "support_artifacts": [],
    }
