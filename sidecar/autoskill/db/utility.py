from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace
from autoskill.services.utility import SkillUtilityFeatures, compute_utility_score


@dataclass(frozen=True)
class SkillUtilityRollupRecord:
    skill_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    slug: str | None
    lifecycle_state: str | None
    utility_score: float
    features: SkillUtilityFeatures
    computed_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> SkillUtilityRollupRecord:
        features = SkillUtilityFeatures.from_mapping(_json_dict(row["features"]))
        return cls(
            skill_id=row["skill_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            slug=_row_get(row, "slug"),
            lifecycle_state=_row_get(row, "lifecycle_state"),
            utility_score=float(row["utility_score"]),
            features=features,
            computed_at=row["computed_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "skill_id": str(self.skill_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "slug": self.slug,
            "lifecycle_state": self.lifecycle_state,
            "utility_score": self.utility_score,
            "features": self.features.to_json(),
            "computed_at": self.computed_at.isoformat(),
        }


@dataclass(frozen=True)
class CurationActionRecord:
    curation_action_id: UUID
    skill_id: UUID | None
    action: str
    status: str
    reason: str
    features: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> CurationActionRecord:
        return cls(
            curation_action_id=row["curation_action_id"],
            skill_id=_row_get(row, "skill_id"),
            action=row["action"],
            status=row["status"],
            reason=row["reason"],
            features=_json_dict(row["features"]),
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "curation_action_id": str(self.curation_action_id),
            "skill_id": str(self.skill_id) if self.skill_id else None,
            "action": self.action,
            "status": self.status,
            "reason": self.reason,
            "features": self.features,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class UtilityRollupResult:
    scanned: int
    rollups: list[SkillUtilityRollupRecord]

    def to_json(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "rollups": [rollup.to_json() for rollup in self.rollups],
        }


@dataclass(frozen=True)
class CurationRunResult:
    scanned: int
    archived: int
    actions: list[CurationActionRecord]

    def to_json(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "archived": self.archived,
            "actions": [action.to_json() for action in self.actions],
        }


class UtilityStore(Protocol):
    async def run_utility_rollup(
        self,
        *,
        workspace_key: str,
        limit: int = 250,
    ) -> UtilityRollupResult:
        """Compute deterministic utility rollups for skills."""

    async def run_curation(
        self,
        *,
        workspace_key: str,
        archive_threshold: float = -1.0,
        max_archive: int = 5,
    ) -> CurationRunResult:
        """Archive active low-utility skills and log curation actions."""


class NullUtilityStore:
    async def run_utility_rollup(
        self,
        *,
        workspace_key: str,
        limit: int = 250,
    ) -> UtilityRollupResult:
        return UtilityRollupResult(scanned=0, rollups=[])

    async def run_curation(
        self,
        *,
        workspace_key: str,
        archive_threshold: float = -1.0,
        max_archive: int = 5,
    ) -> CurationRunResult:
        return CurationRunResult(scanned=0, archived=0, actions=[])


class AsyncpgUtilityStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def run_utility_rollup(
        self,
        *,
        workspace_key: str,
        limit: int = 250,
    ) -> UtilityRollupResult:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            skills = await _load_skill_feature_rows(conn, workspace_id, limit)
            rollups: list[SkillUtilityRollupRecord] = []
            for row in skills:
                features = SkillUtilityFeatures.from_mapping(dict(row))
                score = compute_utility_score(features)
                rollup = await _upsert_rollup(
                    conn,
                    workspace_id=workspace_id,
                    workspace_key=workspace_key,
                    skill_id=row["skill_id"],
                    slug=row["slug"],
                    lifecycle_state=row["lifecycle_state"],
                    features=features,
                    utility_score=score,
                )
                rollups.append(rollup)
        return UtilityRollupResult(scanned=len(skills), rollups=rollups)

    async def run_curation(
        self,
        *,
        workspace_key: str,
        archive_threshold: float = -1.0,
        max_archive: int = 5,
    ) -> CurationRunResult:
        rollups = await self.run_utility_rollup(workspace_key=workspace_key)
        pool = await self._get_pool()
        actions: list[CurationActionRecord] = []
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            for rollup in rollups.rollups:
                if len(actions) >= max_archive:
                    break
                if rollup.lifecycle_state != "active":
                    continue
                if rollup.utility_score > archive_threshold:
                    continue
                await conn.execute(
                    """
                    UPDATE autoskill.skills
                    SET lifecycle_state = 'archived',
                        updated_at = now()
                    WHERE workspace_id = $1
                      AND skill_id = $2
                      AND lifecycle_state = 'active'
                    """,
                    workspace_id,
                    rollup.skill_id,
                )
                action = await _insert_curation_action(
                    conn,
                    workspace_id=workspace_id,
                    skill_id=rollup.skill_id,
                    action="archive",
                    status="applied",
                    reason="utility below archive threshold",
                    features={
                        **rollup.features.to_json(),
                        "utility_score": rollup.utility_score,
                        "archive_threshold": archive_threshold,
                    },
                )
                actions.append(action)
        return CurationRunResult(
            scanned=rollups.scanned,
            archived=len(actions),
            actions=actions,
        )


async def _load_skill_feature_rows(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    limit: int,
) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT
          s.skill_id,
          s.slug,
          s.lifecycle_state,
          COALESCE(helped.count, 0)::int AS helped_count,
          COALESCE(hurt.count, 0)::int AS hurt_count,
          COALESCE(shadow.count, 0)::int AS shadow_count,
          COALESCE(retrieved.count, 0)::int AS retrieval_count,
          COALESCE(canary_failed.count, 0)::int AS canary_failure_count
        FROM autoskill.skills s
        LEFT JOIN LATERAL (
          SELECT count(*)::int AS count
          FROM autoskill.attribution_events ae
          WHERE ae.workspace_id = s.workspace_id
            AND s.skill_id = ANY(ae.skill_ids)
            AND ae.outcome IN ('skill_helped', 'helped', 'success')
        ) helped ON true
        LEFT JOIN LATERAL (
          SELECT count(*)::int AS count
          FROM autoskill.attribution_events ae
          WHERE ae.workspace_id = s.workspace_id
            AND s.skill_id = ANY(ae.skill_ids)
            AND ae.outcome IN ('skill_hurt', 'hurt', 'failed')
        ) hurt ON true
        LEFT JOIN LATERAL (
          SELECT count(*)::int AS count
          FROM autoskill.attribution_events ae
          WHERE ae.workspace_id = s.workspace_id
            AND s.skill_id = ANY(ae.skill_ids)
            AND ae.outcome IN ('skill_shadowed', 'shadowed', 'wrong_skill')
        ) shadow ON true
        LEFT JOIN LATERAL (
          SELECT count(*)::int AS count
          FROM autoskill.retrieval_logs rl
          WHERE rl.workspace_id = s.workspace_id
            AND s.skill_id = ANY(rl.rendered_skill_ids)
        ) retrieved ON true
        LEFT JOIN LATERAL (
          SELECT count(*)::int AS count
          FROM autoskill.canary_results cr
          WHERE cr.workspace_id = s.workspace_id
            AND cr.skill_id = s.skill_id
            AND (cr.critical OR cr.status IN ('failed', 'critical'))
        ) canary_failed ON true
        WHERE s.workspace_id = $1
        ORDER BY s.updated_at DESC, s.slug ASC
        LIMIT $2
        """,
        workspace_id,
        max(1, min(limit, 1000)),
    )


async def _upsert_rollup(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    workspace_key: str,
    skill_id: UUID,
    slug: str,
    lifecycle_state: str,
    features: SkillUtilityFeatures,
    utility_score: float,
) -> SkillUtilityRollupRecord:
    row = await conn.fetchrow(
        """
        INSERT INTO autoskill.skill_utility_rollups (
          skill_utility_rollup_id,
          workspace_id,
          skill_id,
          helped_count,
          hurt_count,
          shadow_count,
          retrieval_count,
          canary_failure_count,
          utility_score,
          features
        )
        VALUES (
          gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb
        )
        ON CONFLICT (workspace_id, skill_id) DO UPDATE
        SET helped_count = EXCLUDED.helped_count,
            hurt_count = EXCLUDED.hurt_count,
            shadow_count = EXCLUDED.shadow_count,
            retrieval_count = EXCLUDED.retrieval_count,
            canary_failure_count = EXCLUDED.canary_failure_count,
            utility_score = EXCLUDED.utility_score,
            features = EXCLUDED.features,
            computed_at = now()
        RETURNING *, $10::text AS workspace_key, $11::text AS slug, $12::text AS lifecycle_state
        """,
        workspace_id,
        skill_id,
        features.helped_count,
        features.hurt_count,
        features.shadow_count,
        features.retrieval_count,
        features.canary_failure_count,
        utility_score,
        _json(features.to_json()),
        workspace_key,
        slug,
        lifecycle_state,
    )
    return SkillUtilityRollupRecord.from_row(row)


async def _insert_curation_action(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    skill_id: UUID | None,
    action: str,
    status: str,
    reason: str,
    features: dict[str, Any],
) -> CurationActionRecord:
    row = await conn.fetchrow(
        """
        INSERT INTO autoskill.curation_actions (
          curation_action_id,
          workspace_id,
          skill_id,
          action,
          status,
          reason,
          features
        )
        VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6::jsonb)
        RETURNING *
        """,
        workspace_id,
        skill_id,
        action,
        status,
        reason,
        _json(features),
    )
    return CurationActionRecord.from_row(row)


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None
