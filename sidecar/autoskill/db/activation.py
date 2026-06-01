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
            "blockers": self.blockers,
        }


class ActivationGateStore(Protocol):
    async def check_activation_readiness(
        self,
        *,
        workspace_key: str,
        skill_version_id: UUID,
        executor_profile_id: UUID | None = None,
    ) -> ActivationReadiness:
        """Return deterministic activation readiness for a staged skill version."""


class NullActivationGateStore:
    async def check_activation_readiness(
        self,
        *,
        workspace_key: str,
        skill_version_id: UUID,
        executor_profile_id: UUID | None = None,
    ) -> ActivationReadiness:
        return ActivationReadiness(
            allowed=True,
            skill_version_id=skill_version_id,
            executor_profile_id=executor_profile_id,
            scanner_status="passed",
            evaluator_status="passed",
            latest_evaluation_status="passed",
            compatibility_status="compatible" if executor_profile_id else None,
            blockers=[],
        )


class AsyncpgActivationGateStore(AsyncpgPoolOwner):
    async def check_activation_readiness(
        self,
        *,
        workspace_key: str,
        skill_version_id: UUID,
        executor_profile_id: UUID | None = None,
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
                  compat.status AS compatibility_status
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
                WHERE s.workspace_id = $1
                  AND sv.skill_version_id = $2
                """,
                workspace_id,
                skill_version_id,
                executor_profile_id,
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
                blockers=["skill-version-not-found"],
            )
        blockers = _activation_blockers(row, executor_profile_id=executor_profile_id)
        return ActivationReadiness(
            allowed=not blockers,
            skill_version_id=skill_version_id,
            executor_profile_id=executor_profile_id,
            scanner_status=row["scanner_status"],
            evaluator_status=row["evaluator_status"],
            latest_evaluation_status=row["latest_evaluation_status"],
            compatibility_status=row["compatibility_status"],
            blockers=blockers,
        )


def _activation_blockers(
    row: asyncpg.Record,
    *,
    executor_profile_id: UUID | None,
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
    return blockers
