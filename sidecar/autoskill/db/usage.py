from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.core.hashing import sha256_json
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace

SUCCESS_OUTCOMES = {"skill_helped", "helped", "success", "useful", "passed"}
FAILURE_OUTCOMES = {"skill_hurt", "hurt", "failed", "failure", "wrong_skill"}


@dataclass(frozen=True)
class UsageAggregationResult:
    windows_scanned: int
    windows_created: int
    edges_updated: int
    clusters_upserted: int

    def to_json(self) -> dict[str, int]:
        return {
            "windows_scanned": self.windows_scanned,
            "windows_created": self.windows_created,
            "edges_updated": self.edges_updated,
            "clusters_upserted": self.clusters_upserted,
        }


class UsageStore(Protocol):
    async def aggregate_usage(
        self,
        *,
        workspace_key: str,
        limit: int = 500,
        min_support: int = 2,
    ) -> UsageAggregationResult:
        """Aggregate content-safe usage windows into topology evidence tables."""


class NullUsageStore:
    async def aggregate_usage(
        self,
        *,
        workspace_key: str,
        limit: int = 500,
        min_support: int = 2,
    ) -> UsageAggregationResult:
        return UsageAggregationResult(
            windows_scanned=0,
            windows_created=0,
            edges_updated=0,
            clusters_upserted=0,
        )


class AsyncpgUsageStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def aggregate_usage(
        self,
        *,
        workspace_key: str,
        limit: int = 500,
        min_support: int = 2,
    ) -> UsageAggregationResult:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            rows = await _load_usage_source_rows(conn, workspace_id, limit)
            windows_created = 0
            edges_updated = 0
            for row in rows:
                window = _usage_window_from_row(row)
                if not window["skill_ids"]:
                    continue
                created = await _insert_usage_window(conn, workspace_id, window)
                windows_created += int(created)
                if created:
                    edges_updated += await _upsert_co_usage_edges(
                        conn,
                        workspace_id,
                        skill_ids=window["skill_ids"],
                        outcome=window["outcome"],
                    )
            clusters_upserted = await _upsert_usage_clusters(
                conn,
                workspace_id,
                min_support=max(1, min_support),
            )
        return UsageAggregationResult(
            windows_scanned=len(rows),
            windows_created=windows_created,
            edges_updated=edges_updated,
            clusters_upserted=clusters_upserted,
        )


async def _load_usage_source_rows(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    limit: int,
) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        (
          SELECT
            'retrieval_log' AS source_kind,
            retrieval_log_id AS source_id,
            session_id,
            turn_id,
            rendered_skill_ids AS skill_ids,
            decision AS outcome,
            metadata,
            created_at AS observed_at
          FROM autoskill.retrieval_logs
          WHERE workspace_id = $1
            AND array_length(rendered_skill_ids, 1) IS NOT NULL
        )
        UNION ALL
        (
          SELECT
            'attribution_event' AS source_kind,
            attribution_event_id AS source_id,
            session_id,
            turn_id,
            skill_ids,
            outcome,
            metadata,
            created_at AS observed_at
          FROM autoskill.attribution_events
          WHERE workspace_id = $1
            AND array_length(skill_ids, 1) IS NOT NULL
        )
        ORDER BY observed_at DESC
        LIMIT $2
        """,
        workspace_id,
        max(1, limit),
    )


def _usage_window_from_row(row: asyncpg.Record | dict[str, Any]) -> dict[str, Any]:
    skill_ids = _stable_skill_ids(row["skill_ids"])
    source_kind = str(row["source_kind"])
    source_id = row["source_id"]
    signature = sha256_json(
        {
            "source_kind": source_kind,
            "source_id": str(source_id),
            "skill_ids": [str(skill_id) for skill_id in skill_ids],
            "session_id": row["session_id"],
            "turn_id": row["turn_id"],
        }
    )
    return {
        "session_id": row["session_id"],
        "turn_id": row["turn_id"],
        "skill_ids": skill_ids,
        "sequence_signature_hash": signature,
        "outcome": row["outcome"],
        "metadata": {
            "source_kind": source_kind,
            "source_id": str(source_id),
            "source_metadata": _metadata_dict(row["metadata"]),
        },
        "observed_at": row["observed_at"],
    }


async def _insert_usage_window(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    window: dict[str, Any],
) -> bool:
    row = await conn.fetchrow(
        """
        INSERT INTO autoskill.skill_usage_windows (
          skill_usage_window_id,
          workspace_id,
          session_id,
          turn_id,
          skill_ids,
          sequence_signature_hash,
          outcome,
          metadata,
          observed_at
        )
        SELECT
          gen_random_uuid(),
          $1,
          $2,
          $3,
          $4::uuid[],
          $5,
          $6,
          $7::jsonb,
          $8
        WHERE NOT EXISTS (
          SELECT 1
          FROM autoskill.skill_usage_windows
          WHERE workspace_id = $1
            AND sequence_signature_hash = $5
        )
        RETURNING skill_usage_window_id
        """,
        workspace_id,
        window["session_id"],
        window["turn_id"],
        window["skill_ids"],
        window["sequence_signature_hash"],
        window["outcome"],
        _json(window["metadata"]),
        window["observed_at"],
    )
    return row is not None


async def _upsert_co_usage_edges(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    *,
    skill_ids: list[UUID],
    outcome: str | None,
) -> int:
    pairs = _skill_pairs(skill_ids)
    success = 1 if outcome in SUCCESS_OUTCOMES else 0
    failure = 1 if outcome in FAILURE_OUTCOMES else 0
    sequence = 1 if len(skill_ids) > 1 else 0
    for left, right in pairs:
        await conn.execute(
            """
            INSERT INTO autoskill.skill_co_usage_edges (
              skill_co_usage_edge_id,
              workspace_id,
              left_skill_id,
              right_skill_id,
              co_usage_count,
              success_count,
              failure_count,
              sequence_count,
              last_seen_at
            )
            VALUES (gen_random_uuid(), $1, $2, $3, 1, $4, $5, $6, now())
            ON CONFLICT (workspace_id, left_skill_id, right_skill_id)
            DO UPDATE SET
              co_usage_count = autoskill.skill_co_usage_edges.co_usage_count + 1,
              success_count = autoskill.skill_co_usage_edges.success_count + $4,
              failure_count = autoskill.skill_co_usage_edges.failure_count + $5,
              sequence_count = autoskill.skill_co_usage_edges.sequence_count + $6,
              last_seen_at = now()
            """,
            workspace_id,
            left,
            right,
            success,
            failure,
            sequence,
        )
    return len(pairs)


async def _upsert_usage_clusters(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    *,
    min_support: int,
) -> int:
    rows = await conn.fetch(
        """
        SELECT left_skill_id, right_skill_id, co_usage_count, success_count, failure_count
        FROM autoskill.skill_co_usage_edges
        WHERE workspace_id = $1
          AND co_usage_count >= $2
        ORDER BY co_usage_count DESC, left_skill_id, right_skill_id
        LIMIT 100
        """,
        workspace_id,
        min_support,
    )
    upserted = 0
    for row in rows:
        skill_ids = [row["left_skill_id"], row["right_skill_id"]]
        cluster_key = "compose:" + ":".join(str(skill_id) for skill_id in skill_ids)
        await conn.execute(
            """
            INSERT INTO autoskill.skill_usage_clusters (
              skill_usage_cluster_id,
              workspace_id,
              cluster_key,
              skill_ids,
              support_count,
              recommended_operation,
              status,
              metadata
            )
            VALUES (
              gen_random_uuid(),
              $1,
              $2,
              $3::uuid[],
              $4,
              'compose',
              'observed',
              $5::jsonb
            )
            ON CONFLICT (workspace_id, cluster_key)
            DO UPDATE SET
              skill_ids = EXCLUDED.skill_ids,
              support_count = EXCLUDED.support_count,
              recommended_operation = EXCLUDED.recommended_operation,
              metadata = EXCLUDED.metadata,
              updated_at = now()
            """,
            workspace_id,
            cluster_key,
            skill_ids,
            row["co_usage_count"],
            _json(
                {
                    "source": "usage.aggregate",
                    "success_count": row["success_count"],
                    "failure_count": row["failure_count"],
                }
            ),
        )
        upserted += 1
    return upserted


def _stable_skill_ids(values: list[UUID] | tuple[UUID, ...] | None) -> list[UUID]:
    seen: set[UUID] = set()
    stable: list[UUID] = []
    for value in values or []:
        if value in seen:
            continue
        seen.add(value)
        stable.append(value)
    return stable


def _skill_pairs(skill_ids: list[UUID]) -> list[tuple[UUID, UUID]]:
    sorted_ids = sorted(set(skill_ids), key=str)
    return [
        (left, right)
        for index, left in enumerate(sorted_ids)
        for right in sorted_ids[index + 1 :]
    ]


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True)


def _metadata_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        decoded = json.loads(value)
        if isinstance(decoded, dict):
            return decoded
    return {}
