from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class ActivationReadiness:
    allowed: bool
    skill_version_id: UUID
    executor_profile_id: UUID | None
    scanner_status: str | None
    evaluator_status: str | None
    latest_evaluation_status: str | None
    compatibility_status: str | None
    context_compile_run_id: UUID | None
    context_artifact_id: UUID | None
    context_compile_status: str | None
    context_safety_status: str | None
    context_equivalence_status: str | None
    context_budget_status: str | None
    blockers: list[str]

    def to_json(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "skill_version_id": str(self.skill_version_id),
            "executor_profile_id": (
                str(self.executor_profile_id) if self.executor_profile_id else None
            ),
            "scanner_status": self.scanner_status,
            "evaluator_status": self.evaluator_status,
            "latest_evaluation_status": self.latest_evaluation_status,
            "compatibility_status": self.compatibility_status,
            "context_compile_run_id": (
                str(self.context_compile_run_id) if self.context_compile_run_id else None
            ),
            "context_artifact_id": (
                str(self.context_artifact_id) if self.context_artifact_id else None
            ),
            "context_compile_status": self.context_compile_status,
            "context_safety_status": self.context_safety_status,
            "context_equivalence_status": self.context_equivalence_status,
            "context_budget_status": self.context_budget_status,
            "blockers": self.blockers,
        }


class ActivationGateStore(Protocol):
    async def check_activation_readiness(
        self,
        *,
        workspace_key: str,
        skill_version_id: UUID,
        executor_profile_id: UUID | None = None,
        require_context_compile_proof: bool = False,
        context_compile_run_id: UUID | None = None,
        context_artifact_id: UUID | None = None,
        compiled_text_hash: str | None = None,
        context_output_manifest_hash: str | None = None,
    ) -> ActivationReadiness:
        """Return deterministic activation readiness for a staged skill version."""


class NullActivationGateStore:
    async def check_activation_readiness(
        self,
        *,
        workspace_key: str,
        skill_version_id: UUID,
        executor_profile_id: UUID | None = None,
        require_context_compile_proof: bool = False,
        context_compile_run_id: UUID | None = None,
        context_artifact_id: UUID | None = None,
        compiled_text_hash: str | None = None,
        context_output_manifest_hash: str | None = None,
    ) -> ActivationReadiness:
        return ActivationReadiness(
            allowed=True,
            skill_version_id=skill_version_id,
            executor_profile_id=executor_profile_id,
            scanner_status="passed",
            evaluator_status="passed",
            latest_evaluation_status="passed",
            compatibility_status="compatible" if executor_profile_id else None,
            context_compile_run_id=context_compile_run_id,
            context_artifact_id=context_artifact_id,
            context_compile_status="passed",
            context_safety_status="passed",
            context_equivalence_status="passed",
            context_budget_status="passed",
            blockers=[],
        )


class AsyncpgActivationGateStore(AsyncpgPoolOwner):
    async def check_activation_readiness(
        self,
        *,
        workspace_key: str,
        skill_version_id: UUID,
        executor_profile_id: UUID | None = None,
        require_context_compile_proof: bool = False,
        context_compile_run_id: UUID | None = None,
        context_artifact_id: UUID | None = None,
        compiled_text_hash: str | None = None,
        context_output_manifest_hash: str | None = None,
    ) -> ActivationReadiness:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                SELECT
                  sv.scanner_status,
                  sv.evaluator_status,
                  latest_ev.status AS latest_evaluation_status,
                  compat.status AS compatibility_status,
                  ccr.context_compile_run_id,
                  ca.context_artifact_id,
                  ccr.status AS context_compile_status,
                  ca.safety_status AS context_safety_status,
                  ca.equivalence_status AS context_equivalence_status,
                  ca.budget_status AS context_budget_status
                FROM autoskill.skill_versions sv
                JOIN autoskill.skills s ON s.skill_id = sv.skill_id
                LEFT JOIN LATERAL (
                  SELECT ev.status
                  FROM autoskill.evaluations ev
                  WHERE ev.workspace_id = $1
                    AND ev.skill_version_id = sv.skill_version_id
                    AND ev.category = 'proposal_gate'
                    AND (
                      $3::uuid IS NULL
                      OR ev.executor_profile_id IS NULL
                      OR ev.executor_profile_id = $3
                    )
                  ORDER BY ev.created_at DESC
                  LIMIT 1
                ) latest_ev ON true
                LEFT JOIN autoskill.skill_profile_compatibility compat
                  ON compat.workspace_id = $1
                 AND compat.skill_version_id = sv.skill_version_id
                 AND compat.executor_profile_id = $3
                LEFT JOIN autoskill.context_compile_runs ccr
                  ON ccr.workspace_id = $1
                 AND ccr.skill_version_id = sv.skill_version_id
                 AND ccr.context_compile_run_id = $4
                 AND ($5::uuid IS NULL OR ccr.context_artifact_id = $5)
                 AND ($6::text IS NULL OR ccr.output_manifest_hash = $6)
                LEFT JOIN autoskill.context_artifacts ca
                  ON ca.workspace_id = $1
                 AND ca.skill_version_id = sv.skill_version_id
                 AND ca.context_artifact_id = COALESCE($5::uuid, ccr.context_artifact_id)
                 AND ca.artifact_kind = 'skill_md'
                 AND ($7::text IS NULL OR ca.text_hash = $7)
                WHERE s.workspace_id = $1
                  AND sv.skill_version_id = $2
                """,
                workspace_id,
                skill_version_id,
                executor_profile_id,
                context_compile_run_id,
                context_artifact_id,
                context_output_manifest_hash,
                compiled_text_hash,
            )
        if row is None:
            return ActivationReadiness(
                allowed=False,
                skill_version_id=skill_version_id,
                executor_profile_id=executor_profile_id,
                scanner_status=None,
                evaluator_status=None,
                latest_evaluation_status=None,
                compatibility_status=None,
                context_compile_run_id=context_compile_run_id,
                context_artifact_id=context_artifact_id,
                context_compile_status=None,
                context_safety_status=None,
                context_equivalence_status=None,
                context_budget_status=None,
                blockers=["skill-version-not-found"],
            )
        blockers = _activation_blockers(
            row,
            executor_profile_id=executor_profile_id,
            require_context_compile_proof=require_context_compile_proof,
            context_compile_run_id=context_compile_run_id,
            context_artifact_id=context_artifact_id,
            compiled_text_hash=compiled_text_hash,
            context_output_manifest_hash=context_output_manifest_hash,
        )
        return ActivationReadiness(
            allowed=not blockers,
            skill_version_id=skill_version_id,
            executor_profile_id=executor_profile_id,
            scanner_status=row["scanner_status"],
            evaluator_status=row["evaluator_status"],
            latest_evaluation_status=row["latest_evaluation_status"],
            compatibility_status=row["compatibility_status"],
            context_compile_run_id=row["context_compile_run_id"],
            context_artifact_id=row["context_artifact_id"],
            context_compile_status=row["context_compile_status"],
            context_safety_status=row["context_safety_status"],
            context_equivalence_status=row["context_equivalence_status"],
            context_budget_status=row["context_budget_status"],
            blockers=blockers,
        )


def _activation_blockers(
    row: asyncpg.Record,
    *,
    executor_profile_id: UUID | None,
    require_context_compile_proof: bool,
    context_compile_run_id: UUID | None,
    context_artifact_id: UUID | None,
    compiled_text_hash: str | None,
    context_output_manifest_hash: str | None,
) -> list[str]:
    blockers: list[str] = []
    if row["scanner_status"] != "passed":
        blockers.append("scanner-not-passed")
    if row["evaluator_status"] != "passed":
        blockers.append("evaluator-not-passed")
    if row["latest_evaluation_status"] != "passed":
        blockers.append("proposal-gate-not-passed")
    if executor_profile_id is not None and row["compatibility_status"] != "compatible":
        blockers.append("executor-profile-not-compatible")
    if not require_context_compile_proof:
        return blockers
    if (
        context_compile_run_id is None
        or context_artifact_id is None
        or not compiled_text_hash
        or not context_output_manifest_hash
    ):
        blockers.append("context-compile-proof-missing")
        return blockers
    if row["context_compile_run_id"] is None:
        blockers.append("context-compile-run-not-found")
    elif row["context_compile_status"] != "passed":
        blockers.append("context-compile-not-passed")
    if row["context_artifact_id"] is None:
        blockers.append("context-artifact-not-found")
    else:
        if row["context_safety_status"] != "passed":
            blockers.append("context-safety-not-passed")
        if row["context_equivalence_status"] != "passed":
            blockers.append("context-equivalence-not-passed")
        if row["context_budget_status"] != "passed":
            blockers.append("context-budget-not-passed")
    return blockers
