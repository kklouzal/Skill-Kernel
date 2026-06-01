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
    promoted: int
    merged: int
    actions: list[CurationActionRecord]

    def to_json(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "archived": self.archived,
            "promoted": self.promoted,
            "merged": self.merged,
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
        promotion_min_retrieval: int = 3,
        max_promote: int = 3,
        active_budget: int | None = None,
        max_merge: int = 5,
    ) -> CurationRunResult:
        """Promote recurring archived skills, archive weak active skills, and merge duplicates."""


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
        promotion_min_retrieval: int = 3,
        max_promote: int = 3,
        active_budget: int | None = None,
        max_merge: int = 5,
    ) -> CurationRunResult:
        return CurationRunResult(scanned=0, archived=0, promoted=0, merged=0, actions=[])


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
        promotion_min_retrieval: int = 3,
        max_promote: int = 3,
        active_budget: int | None = None,
        max_merge: int = 5,
    ) -> CurationRunResult:
        rollups = await self.run_utility_rollup(workspace_key=workspace_key)
        pool = await self._get_pool()
        actions: list[CurationActionRecord] = []
        archived = 0
        promoted = 0
        merged = 0
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            rollup_by_skill = {rollup.skill_id: rollup for rollup in rollups.rollups}

            for rollup in sorted(
                rollups.rollups,
                key=lambda item: (item.utility_score, item.slug or ""),
                reverse=True,
            ):
                if promoted >= max_promote:
                    break
                if rollup.lifecycle_state != "archived":
                    continue
                if rollup.features.retrieval_count < promotion_min_retrieval:
                    continue
                if rollup.features.canary_failure_count or rollup.features.hurt_count:
                    continue
                if await _set_lifecycle_state(
                    conn,
                    workspace_id,
                    rollup.skill_id,
                    from_state="archived",
                    to_state="active",
                ):
                    actions.append(
                        await _insert_curation_action(
                            conn,
                            workspace_id=workspace_id,
                            skill_id=rollup.skill_id,
                            action="promote_archive",
                            status="applied",
                            reason="archived skill demand recurred",
                            features={
                                **rollup.features.to_json(),
                                "utility_score": rollup.utility_score,
                                "promotion_min_retrieval": promotion_min_retrieval,
                            },
                        )
                    )
                    promoted += 1

            duplicate_actions = await _archive_duplicate_edges(
                conn,
                workspace_id=workspace_id,
                rollup_by_skill=rollup_by_skill,
                max_merge=min(max_merge, max_archive),
            )
            actions.extend(duplicate_actions)
            archived += len(duplicate_actions)
            merged += len(duplicate_actions)

            archive_actions = await _archive_low_utility(
                conn,
                workspace_id=workspace_id,
                rollups=rollups.rollups,
                archive_threshold=archive_threshold,
                max_archive=max(0, max_archive - archived),
            )
            actions.extend(archive_actions)
            archived += len(archive_actions)

            if active_budget is not None and active_budget > 0:
                budget_actions = await _enforce_active_budget(
                    conn,
                    workspace_id=workspace_id,
                    rollup_by_skill=rollup_by_skill,
                    active_budget=active_budget,
                    max_archive=max(0, max_archive - archived),
                )
                actions.extend(budget_actions)
                archived += len(budget_actions)
        return CurationRunResult(
            scanned=rollups.scanned,
            archived=archived,
            promoted=promoted,
            merged=merged,
            actions=actions,
        )


async def _archive_low_utility(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    rollups: list[SkillUtilityRollupRecord],
    archive_threshold: float,
    max_archive: int,
) -> list[CurationActionRecord]:
    actions: list[CurationActionRecord] = []
    for rollup in sorted(rollups, key=lambda item: (item.utility_score, item.slug or "")):
        if len(actions) >= max_archive:
            break
        if rollup.lifecycle_state != "active":
            continue
        if rollup.utility_score > archive_threshold:
            continue
        if not await _set_lifecycle_state(
            conn,
            workspace_id,
            rollup.skill_id,
            from_state="active",
            to_state="archived",
        ):
            continue
        actions.append(
            await _insert_curation_action(
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
        )
    return actions


async def _archive_duplicate_edges(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    rollup_by_skill: dict[UUID, SkillUtilityRollupRecord],
    max_merge: int,
) -> list[CurationActionRecord]:
    if max_merge <= 0:
        return []
    rows = await conn.fetch(
        """
        SELECT
          e.from_skill_id,
          e.to_skill_id,
          from_skill.slug AS from_slug,
          to_skill.slug AS to_slug
        FROM autoskill.skill_edges e
        JOIN autoskill.skills from_skill
          ON from_skill.skill_id = e.from_skill_id
         AND from_skill.workspace_id = e.workspace_id
        JOIN autoskill.skills to_skill
          ON to_skill.skill_id = e.to_skill_id
         AND to_skill.workspace_id = e.workspace_id
        WHERE e.workspace_id = $1
          AND e.edge_kind IN ('duplicate', 'duplicate_of')
          AND from_skill.lifecycle_state = 'active'
          AND to_skill.lifecycle_state = 'active'
        ORDER BY from_skill.slug ASC, to_skill.slug ASC
        LIMIT $2
        """,
        workspace_id,
        max_merge * 3,
    )
    actions: list[CurationActionRecord] = []
    archived_skill_ids: set[UUID] = set()
    for row in rows:
        if len(actions) >= max_merge:
            break
        left = row["from_skill_id"]
        right = row["to_skill_id"]
        if left in archived_skill_ids or right in archived_skill_ids:
            continue
        left_rollup = rollup_by_skill.get(left)
        right_rollup = rollup_by_skill.get(right)
        left_score = left_rollup.utility_score if left_rollup else 0.0
        right_score = right_rollup.utility_score if right_rollup else 0.0
        if (left_score, row["from_slug"]) >= (right_score, row["to_slug"]):
            keep_id, keep_slug = left, row["from_slug"]
            archive_id, archive_slug, archive_rollup = right, row["to_slug"], right_rollup
        else:
            keep_id, keep_slug = right, row["to_slug"]
            archive_id, archive_slug, archive_rollup = left, row["from_slug"], left_rollup
        if not await _set_lifecycle_state(
            conn,
            workspace_id,
            archive_id,
            from_state="active",
            to_state="archived",
        ):
            continue
        archived_skill_ids.add(archive_id)
        features = archive_rollup.features.to_json() if archive_rollup else {}
        actions.append(
            await _insert_curation_action(
                conn,
                workspace_id=workspace_id,
                skill_id=archive_id,
                action="merge_duplicate",
                status="applied",
                reason="explicit duplicate edge archived lower-utility skill",
                features={
                    **features,
                    "utility_score": archive_rollup.utility_score if archive_rollup else 0.0,
                    "archived_slug": archive_slug,
                    "kept_skill_id": str(keep_id),
                    "kept_slug": keep_slug,
                },
            )
        )
    return actions


async def _enforce_active_budget(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    rollup_by_skill: dict[UUID, SkillUtilityRollupRecord],
    active_budget: int,
    max_archive: int,
) -> list[CurationActionRecord]:
    rows = await conn.fetch(
        """
        SELECT s.skill_id, s.slug, COALESCE(r.utility_score, 0)::float AS utility_score
        FROM autoskill.skills s
        LEFT JOIN autoskill.skill_utility_rollups r
          ON r.workspace_id = s.workspace_id
         AND r.skill_id = s.skill_id
        WHERE s.workspace_id = $1
          AND s.lifecycle_state = 'active'
        ORDER BY COALESCE(r.utility_score, 0) DESC, s.updated_at DESC, s.slug ASC
        OFFSET $2
        LIMIT $3
        """,
        workspace_id,
        active_budget,
        max_archive,
    )
    actions: list[CurationActionRecord] = []
    for row in rows:
        skill_id = row["skill_id"]
        rollup = rollup_by_skill.get(skill_id)
        if not await _set_lifecycle_state(
            conn,
            workspace_id,
            skill_id,
            from_state="active",
            to_state="archived",
        ):
            continue
        features = rollup.features.to_json() if rollup else {}
        actions.append(
            await _insert_curation_action(
                conn,
                workspace_id=workspace_id,
                skill_id=skill_id,
                action="enforce_active_budget",
                status="applied",
                reason="active skill budget exceeded",
                features={
                    **features,
                    "utility_score": rollup.utility_score if rollup else row["utility_score"],
                    "active_budget": active_budget,
                },
            )
        )
    return actions


async def _set_lifecycle_state(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    skill_id: UUID,
    *,
    from_state: str,
    to_state: str,
) -> bool:
    result = await conn.execute(
        """
        UPDATE autoskill.skills
        SET lifecycle_state = $4,
            updated_at = now()
        WHERE workspace_id = $1
          AND skill_id = $2
          AND lifecycle_state = $3
        """,
        workspace_id,
        skill_id,
        from_state,
        to_state,
    )
    return _command_count(result) > 0


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


def _command_count(command_tag: str) -> int:
    try:
        return int(command_tag.rsplit(" ", 1)[1])
    except (IndexError, ValueError):
        return 0


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None
