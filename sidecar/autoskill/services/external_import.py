from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from autoskill.core.hashing import sha256_json
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
    description = record.description or record.name or record.slug
    skill_ir = {
        "schema_version": "skillir.v1",
        "slug": imported_slug,
        "name": record.name or record.slug,
        "description": description,
        "granularity": "external",
        "source": {
            "kind": "external_skill_import",
            "external_skill_id": str(record.external_skill_id),
            "source": record.source,
            "root_path_hash": record.root_path_hash,
            "file_hash": record.file_hash,
        },
        "runtime_interface": {
            "when": [description],
            "do": [
                "Use this staged import only after SkillKernel scanner, compiler, "
                "and evaluator gates pass."
            ],
            "outputs": [],
            "effects": [],
            "never": [
                "Do not mutate the external-owned skill root during import materialization."
            ],
        },
    }
    return {
        "schema": "autoskill.external_import_candidate.v1",
        "mode": "stage_only",
        "mutates_external_root": False,
        "skill_ir": skill_ir,
        "support_artifacts": [],
    }
