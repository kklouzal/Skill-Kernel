from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.core.hashing import sha256_json
from autoskill.db.attribution import SKILL_NEGATIVE_OUTCOMES, SKILL_POSITIVE_OUTCOMES
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace

SUCCESS_OUTCOMES = SKILL_POSITIVE_OUTCOMES | {"helped", "success", "useful", "passed"}
FAILURE_OUTCOMES = SKILL_NEGATIVE_OUTCOMES | {"hurt", "failed", "failure", "wrong_skill"}
CONTEXT_WASTE_OUTCOMES = {
    "false_positive",
    "false_positive_load",
    "ignored",
    "ignored_load",
    "skill_ignored",
    "unused",
}


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


@dataclass(frozen=True)
class UsageTopologyRecommendation:
    skill_usage_cluster_id: UUID | None
    cluster_key: str
    skill_ids: list[UUID]
    evidence_ids: list[UUID]
    recommended_operation: str
    support_count: int
    success_count: int
    failure_count: int
    sequence_count: int
    operation_score: float
    blockers: list[str]
    metadata: dict[str, Any]

    @property
    def accepted(self) -> bool:
        return not self.blockers

    def to_json(self) -> dict[str, Any]:
        return {
            "skill_usage_cluster_id": (
                str(self.skill_usage_cluster_id)
                if self.skill_usage_cluster_id
                else None
            ),
            "cluster_key": self.cluster_key,
            "skill_ids": [str(skill_id) for skill_id in self.skill_ids],
            "evidence_ids": [str(evidence_id) for evidence_id in self.evidence_ids],
            "recommended_operation": self.recommended_operation,
            "support_count": self.support_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "sequence_count": self.sequence_count,
            "operation_score": self.operation_score,
            "accepted": self.accepted,
            "blockers": self.blockers,
            "metadata": self.metadata,
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

    async def recommend_topology_operations(
        self,
        *,
        workspace_key: str,
        limit: int = 25,
        min_support: int = 3,
        min_success_count: int = 1,
        max_failure_ratio: float = 0.25,
        min_sequence_count: int = 1,
    ) -> list[UsageTopologyRecommendation]:
        """Rank observed usage clusters as topology-operation candidates."""


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

    async def recommend_topology_operations(
        self,
        *,
        workspace_key: str,
        limit: int = 25,
        min_support: int = 3,
        min_success_count: int = 1,
        max_failure_ratio: float = 0.25,
        min_sequence_count: int = 1,
    ) -> list[UsageTopologyRecommendation]:
        return []


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
            clusters_upserted += await _upsert_single_skill_usage_clusters(
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

    async def recommend_topology_operations(
        self,
        *,
        workspace_key: str,
        limit: int = 25,
        min_support: int = 3,
        min_success_count: int = 1,
        max_failure_ratio: float = 0.25,
        min_sequence_count: int = 1,
    ) -> list[UsageTopologyRecommendation]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            workspace_id = await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                SELECT
                  skill_usage_cluster_id,
                  cluster_key,
                  skill_ids,
                  evidence_ids,
                  support_count,
                  recommended_operation,
                  status,
                  metadata
                FROM autoskill.skill_usage_clusters
                WHERE workspace_id = $1
                  AND status IN ('observed', 'candidate')
                ORDER BY support_count DESC, updated_at DESC, cluster_key ASC
                LIMIT $2
                """,
                workspace_id,
                max(1, min(limit, 100)),
            )
            skill_snapshots = await _load_usage_skill_snapshots(
                conn,
                workspace_id,
                _skill_ids_from_cluster_rows(rows),
            )
        recommendations = [
            _topology_recommendation_from_row(
                row,
                skill_snapshots=skill_snapshots,
                min_support=max(1, min_support),
                min_success_count=max(0, min_success_count),
                max_failure_ratio=max(0.0, min(max_failure_ratio, 1.0)),
                min_sequence_count=max(0, min_sequence_count),
            )
            for row in rows
        ]
        return sorted(
            recommendations,
            key=lambda item: (
                bool(item.blockers),
                -item.operation_score,
                item.cluster_key,
            ),
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
        UNION ALL
        (
          SELECT
            'context_token_ledger' AS source_kind,
            context_token_ledger_id AS source_id,
            session_id,
            turn_id,
            ARRAY[skill_id] AS skill_ids,
            outcome,
            metadata || jsonb_build_object(
              'visibility_state', visibility_state,
              'token_count', token_count
            ) AS metadata,
            created_at AS observed_at
          FROM autoskill.context_token_ledgers
          WHERE workspace_id = $1
            AND skill_id IS NOT NULL
            AND outcome IS NOT NULL
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
        SELECT
          left_skill_id,
          right_skill_id,
          co_usage_count,
          success_count,
          failure_count,
          sequence_count
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
                    "sequence_count": row["sequence_count"],
                    "topology_signal": "recurring_co_usage",
                }
            ),
        )
        upserted += 1
    return upserted


async def _upsert_single_skill_usage_clusters(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    *,
    min_support: int,
) -> int:
    rows = await conn.fetch(
        """
        SELECT
          skill_ids[1] AS skill_id,
          count(*)::int AS support_count,
          count(*) FILTER (WHERE outcome = ANY($3::text[]))::int AS success_count,
          count(*) FILTER (WHERE outcome = ANY($4::text[]))::int AS failure_count,
          count(*) FILTER (WHERE outcome = ANY($5::text[]))::int AS context_signal_count,
          COALESCE(
            sum(
              CASE
                WHEN outcome = ANY($5::text[])
                THEN COALESCE((metadata #>> '{source_metadata,token_count}')::int, 0)
                ELSE 0
              END
            ),
            0
          )::int AS token_waste,
          avg(
            CASE
              WHEN jsonb_typeof(
                metadata #> '{source_metadata,marginal_value,context_value_per_token}'
              ) = 'number'
              THEN (
                metadata #>> '{source_metadata,marginal_value,context_value_per_token}'
              )::double precision
              ELSE NULL
            END
          ) AS avg_context_value_per_token,
          min(
            CASE
              WHEN jsonb_typeof(
                metadata #> '{source_metadata,marginal_value,context_value_per_token}'
              ) = 'number'
              THEN (
                metadata #>> '{source_metadata,marginal_value,context_value_per_token}'
              )::double precision
              ELSE NULL
            END
          ) AS min_context_value_per_token,
          array_agg(
            jsonb_build_object(
              'source_kind', metadata #>> '{source_kind}',
              'source_id', metadata #>> '{source_id}',
              'outcome', outcome,
              'token_count', metadata #>> '{source_metadata,token_count}',
              'context_value_per_token',
                metadata #>> '{source_metadata,marginal_value,context_value_per_token}'
            )
            ORDER BY observed_at DESC
          ) FILTER (
            WHERE outcome = ANY($4::text[]) OR outcome = ANY($5::text[])
          ) AS negative_sources
        FROM autoskill.skill_usage_windows
        WHERE workspace_id = $1
          AND cardinality(skill_ids) = 1
        GROUP BY skill_ids[1]
        HAVING count(*) >= $2
           AND (
             count(*) FILTER (WHERE outcome = ANY($4::text[])) > 0
             OR count(*) FILTER (WHERE outcome = ANY($5::text[])) > 0
           )
        ORDER BY count(*) DESC, skill_ids[1]
        LIMIT 100
        """,
        workspace_id,
        min_support,
        list(SUCCESS_OUTCOMES),
        list(FAILURE_OUTCOMES),
        list(CONTEXT_WASTE_OUTCOMES),
    )
    upserted = 0
    for row in rows:
        skill_id = row["skill_id"]
        failure_count = int(row["failure_count"] or 0)
        context_signal_count = int(row["context_signal_count"] or 0)
        token_waste = int(row["token_waste"] or 0)
        avg_context_value_per_token = _optional_float(
            row["avg_context_value_per_token"]
        )
        min_context_value_per_token = _optional_float(
            row["min_context_value_per_token"]
        )
        operation = "decompose" if context_signal_count >= max(1, failure_count) else "improve"
        cluster_key = f"{operation}:{skill_id}"
        context_actions = []
        if context_signal_count:
            context_actions.append("broker_abstain")
            context_actions.append("tighten_description")
        if token_waste:
            context_actions.append("decompose_skill")
        if (
            avg_context_value_per_token is not None
            and avg_context_value_per_token < 0
        ):
            context_actions.append("context_value_recheck")
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
              ARRAY[$3]::uuid[],
              $4,
              $5,
              'observed',
              $6::jsonb
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
            skill_id,
            row["support_count"],
            operation,
            _json(
                {
                    "source": "usage.aggregate",
                    "success_count": row["success_count"],
                    "failure_count": failure_count,
                    "sequence_count": 0,
                    "context_signal_count": context_signal_count,
                    "token_waste": token_waste,
                    "avg_context_value_per_token": avg_context_value_per_token,
                    "min_context_value_per_token": min_context_value_per_token,
                    "topology_signal": (
                        "context_waste_or_false_positive"
                        if operation == "decompose"
                        else "repeated_negative_outcome"
                    ),
                    "subject_skill_ids": [str(skill_id)],
                    "suggested_context_actions": context_actions,
                    "negative_sources": _json_object_list(row["negative_sources"])[:10],
                }
            ),
        )
        upserted += 1
    return upserted


async def _load_usage_skill_snapshots(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    skill_ids: list[UUID],
) -> dict[UUID, dict[str, Any]]:
    if not skill_ids:
        return {}
    rows = await conn.fetch(
        """
        SELECT
          s.skill_id,
          s.slug,
          s.name,
          s.lifecycle_state,
          s.source,
          s.active_version_id,
          sv.skill_version_id,
          sv.version,
          sv.skill_ir,
          COALESCE(
            array_agg(DISTINCT d.document_kind)
              FILTER (WHERE d.body_index_document_id IS NOT NULL),
            '{}'::text[]
          ) AS document_kinds,
          count(DISTINCT d.body_index_document_id)::int AS body_index_document_count
        FROM autoskill.skills s
        LEFT JOIN autoskill.skill_versions sv
          ON sv.skill_version_id = s.active_version_id
        LEFT JOIN autoskill.body_index_documents d
          ON d.skill_id = s.skill_id
         AND (
           s.active_version_id IS NULL
           OR d.skill_version_id = s.active_version_id
         )
        WHERE s.workspace_id = $1
          AND s.skill_id = ANY($2::uuid[])
        GROUP BY
          s.skill_id,
          s.slug,
          s.name,
          s.lifecycle_state,
          s.source,
          s.active_version_id,
          sv.skill_version_id,
          sv.version,
          sv.skill_ir
        """,
        workspace_id,
        skill_ids,
    )
    return {row["skill_id"]: _usage_skill_snapshot(row) for row in rows}


def _usage_skill_snapshot(row: asyncpg.Record) -> dict[str, Any]:
    skill_ir = _metadata_dict(row["skill_ir"])
    return {
        "skill_id": str(row["skill_id"]),
        "slug": row["slug"],
        "name": row["name"],
        "lifecycle_state": row["lifecycle_state"],
        "source": row["source"],
        "active_version_id": (
            str(row["active_version_id"]) if row["active_version_id"] else None
        ),
        "skill_version_id": (
            str(row["skill_version_id"]) if row["skill_version_id"] else None
        ),
        "version": row["version"],
        "description": _compact_text(skill_ir.get("description")),
        "effects": _effect_payload_from_skill_ir(skill_ir),
        "contracts": {
            "environment_contract_count": len(
                _json_object_list(skill_ir.get("environment_contracts"))
            ),
            "runtime_guard_count": len(
                _json_object_list(skill_ir.get("runtime_guards"))
            ),
            "support_artifact_count": len(
                _json_object_list(skill_ir.get("support_artifacts"))
            ),
        },
        "body_index": {
            "document_kinds": sorted(row["document_kinds"] or []),
            "document_count": row["body_index_document_count"],
        },
    }


def _effect_payload_from_skill_ir(skill_ir: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in (
        "outputs",
        "effects",
        "state_delta",
        "side_effects",
        "termination",
        "unsafe_when",
        "failure_modes",
    ):
        values = _string_list(skill_ir.get(key))
        if values:
            payload[key] = values
    idempotency = skill_ir.get("idempotency")
    if isinstance(idempotency, str) and idempotency:
        payload["idempotency"] = idempotency
    return payload


def _skill_ids_from_cluster_rows(rows: list[asyncpg.Record]) -> list[UUID]:
    seen: set[UUID] = set()
    ordered: list[UUID] = []
    for row in rows:
        for skill_id in _stable_skill_ids(row["skill_ids"]):
            if skill_id in seen:
                continue
            seen.add(skill_id)
            ordered.append(skill_id)
    return ordered


def _topology_recommendation_from_row(
    row: asyncpg.Record | dict[str, Any],
    *,
    skill_snapshots: dict[UUID, dict[str, Any]] | None = None,
    min_support: int,
    min_success_count: int,
    max_failure_ratio: float,
    min_sequence_count: int,
) -> UsageTopologyRecommendation:
    metadata = _metadata_dict(row["metadata"])
    skill_ids = _stable_skill_ids(row["skill_ids"])
    evidence_ids = _stable_skill_ids(row["evidence_ids"])
    support_count = int(row["support_count"] or 0)
    success_count = int(metadata.get("success_count") or 0)
    failure_count = int(metadata.get("failure_count") or 0)
    sequence_count = int(metadata.get("sequence_count") or 0)
    context_signal_count = int(metadata.get("context_signal_count") or 0)
    token_waste = int(metadata.get("token_waste") or 0)
    avg_context_value_per_token = _optional_float(
        metadata.get("avg_context_value_per_token")
    )
    min_context_value_per_token = _optional_float(
        metadata.get("min_context_value_per_token")
    )
    failure_ratio = failure_count / support_count if support_count else 0.0
    operation = str(row["recommended_operation"] or "")
    snapshots = [
        skill_snapshots[skill_id]
        for skill_id in skill_ids
        if skill_snapshots and skill_id in skill_snapshots
    ]
    if operation in {"improve", "decompose"}:
        operation_score = float(
            support_count
            + (failure_count * 2)
            + (context_signal_count * 2)
            + success_count
            + min(token_waste / 250.0, 4.0)
            + (
                abs(avg_context_value_per_token) * 10.0
                if avg_context_value_per_token is not None
                and avg_context_value_per_token < 0
                else 0.0
            )
        )
    else:
        operation_score = float(
            support_count
            + (success_count * 2)
            + sequence_count
            - (failure_count * 3)
        )
    blockers: list[str] = []
    if support_count < min_support:
        blockers.append("usage cluster support below threshold")
    if operation not in {"improve", "compose", "decompose"}:
        blockers.append("usage cluster operation is not topology-primary")
    if operation == "compose" and len(skill_ids) < 2:
        blockers.append("compose recommendation requires at least two skills")
    if operation == "compose":
        if success_count < min_success_count:
            blockers.append("usage cluster lacks successful outcome evidence")
        if failure_ratio > max_failure_ratio:
            blockers.append("usage cluster failure ratio above threshold")
        if sequence_count < min_sequence_count:
            blockers.append("usage cluster lacks stable sequence evidence")
    if operation == "improve" and failure_count + context_signal_count <= 0:
        blockers.append("improve recommendation lacks negative outcome evidence")
    if operation == "decompose" and context_signal_count <= 0:
        blockers.append("decompose recommendation lacks context-waste evidence")

    return UsageTopologyRecommendation(
        skill_usage_cluster_id=_row_get(row, "skill_usage_cluster_id"),
        cluster_key=str(row["cluster_key"]),
        skill_ids=skill_ids,
        evidence_ids=evidence_ids,
        recommended_operation=operation,
        support_count=support_count,
        success_count=success_count,
        failure_count=failure_count,
        sequence_count=sequence_count,
        operation_score=operation_score,
        blockers=blockers,
        metadata={
            "source": metadata.get("source", "skill_usage_clusters"),
            "topology_signal": metadata.get("topology_signal"),
            "failure_ratio": failure_ratio,
            "context_signal_count": context_signal_count,
            "token_waste": token_waste,
            "avg_context_value_per_token": avg_context_value_per_token,
            "min_context_value_per_token": min_context_value_per_token,
            "subject_skill_ids": metadata.get("subject_skill_ids", []),
            "skill_snapshots": snapshots,
            "suggested_context_actions": metadata.get("suggested_context_actions", []),
            "negative_sources": metadata.get("negative_sources", []),
            "thresholds": {
                "min_support": min_support,
                "min_success_count": min_success_count,
                "max_failure_ratio": max_failure_ratio,
                "min_sequence_count": min_sequence_count,
            },
        },
    )


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


def _json_object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    objects: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            objects.append(item)
            continue
        if isinstance(item, str):
            try:
                decoded = json.loads(item)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                objects.append(decoded)
    return objects


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _compact_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None
