from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from uuid import UUID

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace

EVALUATION_FAILURE_STATUSES = {"blocked", "failed"}

TraceStatus = Literal["running", "ok", "error", "timeout", "denied", "quarantined", "rolled_back"]


@dataclass(frozen=True)
class TraceSpanRecord:
    trace_id: UUID
    span_id: UUID
    parent_span_id: UUID | None
    workspace_id: UUID | None
    workspace_key: str | None
    operation_name: str
    operation_kind: str
    status: str
    safe_attributes: dict[str, Any]
    object_refs: list[dict[str, Any]]
    started_at: datetime
    ended_at: datetime | None

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> TraceSpanRecord:
        return cls(
            trace_id=row["trace_id"],
            span_id=row["span_id"],
            parent_span_id=_row_get(row, "parent_span_id"),
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            operation_name=row["operation_name"],
            operation_kind=row["operation_kind"],
            status=row["status"],
            safe_attributes=_json_dict(row["safe_attributes"]),
            object_refs=_json_list(row["object_refs"]),
            started_at=row["started_at"],
            ended_at=_row_get(row, "ended_at"),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "trace_id": str(self.trace_id),
            "span_id": str(self.span_id),
            "parent_span_id": str(self.parent_span_id) if self.parent_span_id else None,
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "operation_name": self.operation_name,
            "operation_kind": self.operation_kind,
            "status": self.status,
            "safe_attributes": self.safe_attributes,
            "object_refs": self.object_refs,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }


@dataclass(frozen=True)
class TraceSummaryRecord:
    trace_id: UUID
    workspace_key: str | None
    span_count: int
    statuses: list[str]
    operation_kinds: list[str]
    object_refs: list[dict[str, Any]]
    started_at: datetime
    last_event_at: datetime

    def to_json(self) -> dict[str, Any]:
        status = "ok"
        if any(item in {"error", "timeout", "denied", "quarantined"} for item in self.statuses):
            status = "degraded"
        elif "running" in self.statuses:
            status = "running"
        return {
            "object_type": "trace",
            "object_id": str(self.trace_id),
            "trace_id": str(self.trace_id),
            "workspace_key": self.workspace_key,
            "span_count": self.span_count,
            "statuses": self.statuses,
            "operation_kinds": self.operation_kinds,
            "object_refs": self.object_refs,
            "started_at": self.started_at.isoformat(),
            "last_event_at": self.last_event_at.isoformat(),
            "status": status,
            "title": f"Trace {self.trace_id}",
            "summary": (
                f"{self.span_count} spans; status={status}; "
                f"operations={len(self.operation_kinds)}"
            ),
            "details_url": f"/admin/traces/{self.trace_id}",
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
            },
        }


class ObservabilityStore(Protocol):
    async def start_span(
        self,
        *,
        workspace_key: str,
        operation_name: str,
        operation_kind: str,
        trace_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        safe_attributes: dict[str, Any] | None = None,
        object_refs: list[dict[str, Any]] | None = None,
    ) -> TraceSpanRecord:
        """Start a content-safe trace span."""

    async def finish_span(
        self,
        *,
        span_id: UUID,
        status: TraceStatus = "ok",
        safe_attributes: dict[str, Any] | None = None,
        object_refs: list[dict[str, Any]] | None = None,
    ) -> TraceSpanRecord | None:
        """Close a trace span."""

    async def link_spans(
        self,
        *,
        from_span_id: UUID,
        to_span_id: UUID,
        link_type: str,
    ) -> bool:
        """Record a trace span link."""

    async def list_trace(
        self,
        *,
        workspace_key: str,
        trace_id: UUID,
        limit: int = 100,
    ) -> list[TraceSpanRecord]:
        """Return spans for one trace."""

    async def list_traces(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[TraceSummaryRecord]:
        """Return bounded content-safe trace summaries."""

    async def operator_metrics(
        self,
        *,
        workspace_key: str | None = None,
        window_minutes: int = 60,
        storage_limit: int = 25,
    ) -> dict[str, Any]:
        """Return a content-safe operator metrics snapshot."""


class NullObservabilityStore:
    async def start_span(
        self,
        *,
        workspace_key: str,
        operation_name: str,
        operation_kind: str,
        trace_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        safe_attributes: dict[str, Any] | None = None,
        object_refs: list[dict[str, Any]] | None = None,
    ) -> TraceSpanRecord:
        from uuid import uuid4

        now = datetime.now(UTC)
        return TraceSpanRecord(
            trace_id=trace_id or uuid4(),
            span_id=uuid4(),
            parent_span_id=parent_span_id,
            workspace_id=None,
            workspace_key=workspace_key,
            operation_name=operation_name,
            operation_kind=operation_kind,
            status="running",
            safe_attributes=safe_attributes or {},
            object_refs=object_refs or [],
            started_at=now,
            ended_at=None,
        )

    async def finish_span(
        self,
        *,
        span_id: UUID,
        status: TraceStatus = "ok",
        safe_attributes: dict[str, Any] | None = None,
        object_refs: list[dict[str, Any]] | None = None,
    ) -> TraceSpanRecord | None:
        return None

    async def link_spans(
        self,
        *,
        from_span_id: UUID,
        to_span_id: UUID,
        link_type: str,
    ) -> bool:
        return True

    async def list_trace(
        self,
        *,
        workspace_key: str,
        trace_id: UUID,
        limit: int = 100,
    ) -> list[TraceSpanRecord]:
        return []

    async def list_traces(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[TraceSummaryRecord]:
        return []

    async def operator_metrics(
        self,
        *,
        workspace_key: str | None = None,
        window_minutes: int = 60,
        storage_limit: int = 25,
    ) -> dict[str, Any]:
        return _empty_operator_metrics(
            workspace_key=workspace_key,
            window_minutes=window_minutes,
            storage_limit=storage_limit,
        )


class AsyncpgObservabilityStore(AsyncpgPoolOwner):
    async def start_span(
        self,
        *,
        workspace_key: str,
        operation_name: str,
        operation_kind: str,
        trace_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        safe_attributes: dict[str, Any] | None = None,
        object_refs: list[dict[str, Any]] | None = None,
    ) -> TraceSpanRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.trace_spans (
                  trace_id,
                  span_id,
                  parent_span_id,
                  workspace_id,
                  operation_name,
                  operation_kind,
                  status,
                  safe_attributes,
                  object_refs
                )
                VALUES (
                  COALESCE($1, gen_random_uuid()),
                  gen_random_uuid(),
                  (
                    SELECT span_id
                    FROM autoskill.trace_spans
                    WHERE span_id = $2
                  ),
                  $3,
                  $4,
                  $5,
                  'running',
                  $6::jsonb,
                  $7::jsonb
                )
                RETURNING *, $8::text AS workspace_key
                """,
                trace_id,
                parent_span_id,
                workspace_id,
                operation_name,
                operation_kind,
                _json(safe_attributes or {}),
                _json(object_refs or []),
                workspace_key,
            )
        return TraceSpanRecord.from_row(row)

    async def finish_span(
        self,
        *,
        span_id: UUID,
        status: TraceStatus = "ok",
        safe_attributes: dict[str, Any] | None = None,
        object_refs: list[dict[str, Any]] | None = None,
    ) -> TraceSpanRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE autoskill.trace_spans ts
                SET ended_at = now(),
                    status = $2,
                    safe_attributes = ts.safe_attributes || $3::jsonb,
                    object_refs = ts.object_refs || $4::jsonb
                FROM autoskill.workspaces w
                WHERE ts.span_id = $1
                  AND w.workspace_id = ts.workspace_id
                RETURNING ts.*, w.external_key AS workspace_key
                """,
                span_id,
                status,
                _json(safe_attributes or {}),
                _json(object_refs or []),
            )
        return TraceSpanRecord.from_row(row) if row else None

    async def link_spans(
        self,
        *,
        from_span_id: UUID,
        to_span_id: UUID,
        link_type: str,
    ) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                INSERT INTO autoskill.trace_span_links (from_span_id, to_span_id, link_type)
                VALUES ($1, $2, $3)
                ON CONFLICT DO NOTHING
                """,
                from_span_id,
                to_span_id,
                link_type,
            )
        return result.endswith("1")

    async def list_trace(
        self,
        *,
        workspace_key: str,
        trace_id: UUID,
        limit: int = 100,
    ) -> list[TraceSpanRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                SELECT ts.*, $3::text AS workspace_key
                FROM autoskill.trace_spans ts
                WHERE ts.workspace_id = $1
                  AND ts.trace_id = $2
                ORDER BY ts.started_at ASC
                LIMIT $4
                """,
                workspace_id,
                trace_id,
                workspace_key,
                max(1, min(limit, 1000)),
            )
        return [TraceSpanRecord.from_row(row) for row in rows]

    async def list_traces(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[TraceSummaryRecord]:
        bounded_limit = max(1, min(limit, 500))
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            workspace_id = await _lookup_workspace_id(conn, workspace_key)
            if workspace_key is not None and workspace_id is None:
                return []
            rows = await conn.fetch(
                """
                SELECT
                  ts.trace_id,
                  $3::text AS workspace_key,
                  count(*)::int AS span_count,
                  array_agg(DISTINCT ts.status ORDER BY ts.status) AS statuses,
                  array_agg(
                    DISTINCT ts.operation_kind ORDER BY ts.operation_kind
                  ) AS operation_kinds,
                  jsonb_agg(ts.object_refs) AS object_ref_sets,
                  min(ts.started_at) AS started_at,
                  max(COALESCE(ts.ended_at, ts.started_at)) AS last_event_at
                FROM autoskill.trace_spans ts
                WHERE ($1::uuid IS NULL OR ts.workspace_id = $1)
                GROUP BY ts.trace_id
                ORDER BY max(COALESCE(ts.ended_at, ts.started_at)) DESC, ts.trace_id DESC
                LIMIT $2
                """,
                workspace_id,
                bounded_limit,
                workspace_key,
            )
        return [_trace_summary_from_row(row) for row in rows]

    async def operator_metrics(
        self,
        *,
        workspace_key: str | None = None,
        window_minutes: int = 60,
        storage_limit: int = 25,
    ) -> dict[str, Any]:
        bounded_window = max(1, min(window_minutes, 24 * 60))
        bounded_storage_limit = max(1, min(storage_limit, 100))
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            workspace_id = await _lookup_workspace_id(conn, workspace_key)
            if workspace_key is not None and workspace_id is None:
                return _empty_operator_metrics(
                    workspace_key=workspace_key,
                    window_minutes=bounded_window,
                    storage_limit=bounded_storage_limit,
                )

            ingest = await conn.fetchrow(
                """
                SELECT
                  count(*) FILTER (
                    WHERE inserted_at >= now() - ($2::int * interval '1 minute')
                  )::int AS events_in_window,
                  count(*)::int AS total_events
                FROM autoskill.raw_events
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                """,
                workspace_id,
                bounded_window,
            )
            redaction_rows = await conn.fetch(
                """
                SELECT redaction_state, count(*)::int AS count
                FROM autoskill.raw_events
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                GROUP BY redaction_state
                """,
                workspace_id,
            )
            latency = await conn.fetchrow(
                """
                SELECT
                  count(*)::int AS span_count,
                  COALESCE(avg(EXTRACT(epoch FROM ended_at - started_at) * 1000), 0)
                    ::double precision AS avg_ms,
                  COALESCE(
                    percentile_cont(0.95) WITHIN GROUP (
                      ORDER BY EXTRACT(epoch FROM ended_at - started_at) * 1000
                    ),
                    0
                  )::double precision AS p95_ms,
                  COALESCE(max(EXTRACT(epoch FROM ended_at - started_at) * 1000), 0)
                    ::double precision AS max_ms
                FROM autoskill.trace_spans
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                  AND ended_at IS NOT NULL
                  AND started_at >= now() - ($2::int * interval '1 minute')
                """,
                workspace_id,
                bounded_window,
            )
            latency_by_kind_rows = await conn.fetch(
                """
                SELECT
                  operation_kind,
                  count(*)::int AS span_count,
                  COALESCE(avg(EXTRACT(epoch FROM ended_at - started_at) * 1000), 0)
                    ::double precision AS avg_ms,
                  COALESCE(
                    percentile_cont(0.95) WITHIN GROUP (
                      ORDER BY EXTRACT(epoch FROM ended_at - started_at) * 1000
                    ),
                    0
                  )::double precision AS p95_ms,
                  COALESCE(max(EXTRACT(epoch FROM ended_at - started_at) * 1000), 0)
                    ::double precision AS max_ms
                FROM autoskill.trace_spans
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                  AND ended_at IS NOT NULL
                  AND started_at >= now() - ($2::int * interval '1 minute')
                GROUP BY operation_kind
                """,
                workspace_id,
                bounded_window,
            )
            job_status_rows = await conn.fetch(
                """
                SELECT status, count(*)::int AS count
                FROM autoskill.jobs j
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                  AND NOT (
                    j.status = 'failed'
                    AND EXISTS (
                      SELECT 1
                      FROM autoskill.jobs newer
                      WHERE newer.workspace_id = j.workspace_id
                        AND newer.job_kind = j.job_kind
                        AND newer.status = 'succeeded'
                        AND newer.updated_at > j.updated_at
                    )
                  )
                GROUP BY status
                """,
                workspace_id,
            )
            job_kind_rows = await conn.fetch(
                """
                SELECT job_kind, status, count(*)::int AS count
                FROM autoskill.jobs j
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                  AND NOT (
                    j.status = 'failed'
                    AND EXISTS (
                      SELECT 1
                      FROM autoskill.jobs newer
                      WHERE newer.workspace_id = j.workspace_id
                        AND newer.job_kind = j.job_kind
                        AND newer.status = 'succeeded'
                        AND newer.updated_at > j.updated_at
                    )
                  )
                GROUP BY job_kind, status
                """,
                workspace_id,
            )
            embedding_backlog = await conn.fetchrow(
                """
                SELECT
                  (
                    SELECT count(*)::int
                    FROM autoskill.jobs
                    WHERE ($1::uuid IS NULL OR workspace_id = $1)
                      AND job_kind = 'embeddings.generate'
                      AND status IN ('queued', 'leased')
                  ) AS embedding_jobs_pending,
                  (
                    SELECT count(*)::int
                    FROM autoskill.evidence_items ei
                    WHERE ($1::uuid IS NULL OR ei.workspace_id = $1)
                      AND NOT EXISTS (
                        SELECT 1
                        FROM autoskill.embeddings e
                        WHERE e.workspace_id = ei.workspace_id
                          AND e.object_type = 'evidence'
                          AND e.object_id = ei.evidence_id
                      )
                  ) AS evidence_items_unembedded,
                  (
                    SELECT count(*)::int
                    FROM autoskill.body_index_documents d
                    WHERE ($1::uuid IS NULL OR d.workspace_id = $1)
                      AND NOT EXISTS (
                        SELECT 1
                        FROM autoskill.embeddings e
                        WHERE e.workspace_id = d.workspace_id
                          AND e.object_type = 'body_index_document'
                          AND e.object_id = d.body_index_document_id
                      )
                  ) AS body_documents_unembedded
                """,
                workspace_id,
            )
            retrieval_rows = await conn.fetch(
                """
                SELECT decision, count(*)::int AS count
                FROM autoskill.retrieval_logs
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                  AND created_at >= now() - ($2::int * interval '1 minute')
                GROUP BY decision
                """,
                workspace_id,
                bounded_window,
            )
            context_row = await conn.fetchrow(
                """
                SELECT
                  count(*) FILTER (
                    WHERE visibility_state IN ('skill_visible', 'sibling_bundle')
                  )::int AS hint_token_ledger_count,
                  COALESCE(
                    sum(token_count) FILTER (
                      WHERE visibility_state IN ('skill_visible', 'sibling_bundle')
                    ),
                    0
                  )::bigint AS hint_token_cost
                FROM autoskill.context_token_ledgers
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                  AND created_at >= now() - ($2::int * interval '1 minute')
                """,
                workspace_id,
                bounded_window,
            )
            context_hints = await conn.fetchrow(
                """
                SELECT
                  count(*) FILTER (
                    WHERE decision = 'skill_hint'
                       OR array_length(rendered_skill_ids, 1) IS NOT NULL
                  )::int AS hint_injections,
                  COALESCE(sum(cardinality(rendered_skill_ids)), 0)::bigint
                    AS rendered_skill_count
                FROM autoskill.retrieval_logs
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                  AND created_at >= now() - ($2::int * interval '1 minute')
                """,
                workspace_id,
                bounded_window,
            )
            skill_rows = await conn.fetch(
                """
                SELECT lifecycle_state, count(*)::int AS count
                FROM autoskill.skills
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                GROUP BY lifecycle_state
                """,
                workspace_id,
            )
            skill_version_rows = await conn.fetch(
                """
                SELECT scanner_status, evaluator_status, count(*)::int AS count
                FROM autoskill.skill_versions sv
                JOIN autoskill.skills s USING (skill_id)
                WHERE ($1::uuid IS NULL OR s.workspace_id = $1)
                GROUP BY scanner_status, evaluator_status
                """,
                workspace_id,
            )
            transaction_rows = await conn.fetch(
                """
                SELECT transaction_kind, status, count(*)::int AS count
                FROM autoskill.evolution_transactions
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                GROUP BY transaction_kind, status
                """,
                workspace_id,
            )
            evaluation_rows = await conn.fetch(
                """
                SELECT status, count(*)::int AS count
                FROM autoskill.evaluations
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                GROUP BY status
                """,
                workspace_id,
            )
            curation_rows = await conn.fetch(
                """
                SELECT action, status, count(*)::int AS count
                FROM autoskill.curation_actions
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                GROUP BY action, status
                """,
                workspace_id,
            )
            revocation_rows = await conn.fetch(
                """
                SELECT request_kind, status, count(*)::int AS count
                FROM autoskill.revocation_requests
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                GROUP BY request_kind, status
                """,
                workspace_id,
            )
            freeze_row = await conn.fetchrow(
                """
                SELECT
                  count(*) FILTER (WHERE lifecycle_state = 'frozen')::int AS frozen_skills,
                  count(*) FILTER (WHERE last_canary_status = 'critical')::int
                    AS critical_canary_skills
                FROM autoskill.skills
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                """,
                workspace_id,
            )
            canary_rows = await conn.fetch(
                """
                SELECT status, count(*)::int AS count
                FROM autoskill.canary_results
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                GROUP BY status
                """,
                workspace_id,
            )
            drift_row = await conn.fetchrow(
                """
                SELECT
                  (
                    SELECT count(*)::int
                    FROM autoskill.environment_contracts
                    WHERE ($1::uuid IS NULL OR workspace_id = $1)
                      AND status = 'violated'
                  ) AS violated_contracts,
                  (
                    SELECT count(*)::int
                    FROM autoskill.drift_events
                    WHERE ($1::uuid IS NULL OR workspace_id = $1)
                  ) AS drift_events
                """,
                workspace_id,
            )
            utility = await conn.fetchrow(
                """
                SELECT
                  count(*)::int AS rollup_count,
                  COALESCE(avg(utility_score), 0)::double precision AS avg_utility,
                  COALESCE(min(utility_score), 0)::double precision AS min_utility,
                  COALESCE(max(utility_score), 0)::double precision AS max_utility,
                  count(*) FILTER (WHERE utility_score < 0)::int AS negative_utility_count,
                  max(computed_at) AS latest_computed_at
                FROM autoskill.skill_utility_rollups
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                """,
                workspace_id,
            )
            audit_row = await conn.fetchrow(
                """
                SELECT count(*)::int AS audit_records, max(occurred_at) AS latest_audit_at
                FROM autoskill.audit_records
                WHERE ($1::uuid IS NULL OR workspace_id = $1)
                """,
                workspace_id,
            )
            storage_rows = await conn.fetch(
                """
                SELECT
                  c.relname AS table_name,
                  pg_table_size(c.oid)::bigint AS table_bytes,
                  pg_indexes_size(c.oid)::bigint AS index_bytes,
                  pg_total_relation_size(c.oid)::bigint AS total_bytes,
                  COALESCE(s.n_live_tup, 0)::bigint AS estimated_rows
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
                WHERE n.nspname = 'autoskill'
                  AND c.relkind = 'r'
                ORDER BY pg_total_relation_size(c.oid) DESC, c.relname ASC
                LIMIT $1
                """,
                bounded_storage_limit,
            )

        return _operator_metrics_payload(
            workspace_key=workspace_key,
            window_minutes=bounded_window,
            storage_limit=bounded_storage_limit,
            ingest=dict(ingest or {}),
            redaction_counts=_counts(redaction_rows, "redaction_state"),
            latency=dict(latency or {}),
            latency_by_operation_kind=_latency_by_operation_kind(latency_by_kind_rows),
            job_status_counts=_counts(job_status_rows, "status"),
            job_kind_counts=_nested_counts(job_kind_rows, "job_kind", "status"),
            embedding_backlog=dict(embedding_backlog or {}),
            retrieval_decisions=_counts(retrieval_rows, "decision"),
            context=dict(context_row or {}),
            context_hints=dict(context_hints or {}),
            skill_lifecycle_counts=_counts(skill_rows, "lifecycle_state"),
            skill_version_counts=[
                {
                    "scanner_status": row["scanner_status"],
                    "evaluator_status": row["evaluator_status"],
                    "count": row["count"],
                }
                for row in skill_version_rows
            ],
            transaction_counts=_nested_counts(transaction_rows, "transaction_kind", "status"),
            evaluation_counts=_counts(evaluation_rows, "status"),
            curation_counts=_nested_counts(curation_rows, "action", "status"),
            revocation_counts=_nested_counts(revocation_rows, "request_kind", "status"),
            freeze=dict(freeze_row or {}),
            canary_counts=_counts(canary_rows, "status"),
            drift=dict(drift_row or {}),
            utility=dict(utility or {}),
            audit=dict(audit_row or {}),
            storage=[
                {
                    "table_name": row["table_name"],
                    "table_bytes": row["table_bytes"],
                    "index_bytes": row["index_bytes"],
                    "total_bytes": row["total_bytes"],
                    "estimated_rows": row["estimated_rows"],
                }
                for row in storage_rows
            ],
        )


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _json_list(value: object) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        parsed = json.loads(value)
        return _json_list(parsed)
    return []


def _trace_summary_from_row(row: asyncpg.Record | dict[str, Any]) -> TraceSummaryRecord:
    object_refs: list[dict[str, Any]] = []
    for ref_set in _json_nested_lists(row["object_ref_sets"]):
        object_refs.extend(ref_set)
    return TraceSummaryRecord(
        trace_id=row["trace_id"],
        workspace_key=_row_get(row, "workspace_key"),
        span_count=int(row["span_count"]),
        statuses=sorted(str(item) for item in row["statuses"]),
        operation_kinds=sorted(str(item) for item in row["operation_kinds"]),
        object_refs=object_refs,
        started_at=row["started_at"],
        last_event_at=row["last_event_at"],
    )


def _json_nested_lists(value: object) -> list[list[dict[str, Any]]]:
    if isinstance(value, list):
        output: list[list[dict[str, Any]]] = []
        for item in value:
            output.append(_json_list(item))
        return output
    if isinstance(value, str):
        parsed = json.loads(value)
        return _json_nested_lists(parsed)
    return []


async def _lookup_workspace_id(conn: asyncpg.Connection, workspace_key: str | None) -> UUID | None:
    if workspace_key is None:
        return None
    return await conn.fetchval(
        "SELECT workspace_id FROM autoskill.workspaces WHERE external_key = $1",
        workspace_key,
    )


def _empty_operator_metrics(
    *,
    workspace_key: str | None,
    window_minutes: int,
    storage_limit: int,
) -> dict[str, Any]:
    return _operator_metrics_payload(
        workspace_key=workspace_key,
        window_minutes=max(1, min(window_minutes, 24 * 60)),
        storage_limit=max(1, min(storage_limit, 100)),
        ingest={"events_in_window": 0, "total_events": 0},
        redaction_counts={},
        latency={"span_count": 0, "avg_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0},
        latency_by_operation_kind={},
        job_status_counts={},
        job_kind_counts={},
        embedding_backlog={
            "embedding_jobs_pending": 0,
            "evidence_items_unembedded": 0,
            "body_documents_unembedded": 0,
        },
        retrieval_decisions={},
        context={"hint_token_ledger_count": 0, "hint_token_cost": 0},
        context_hints={"hint_injections": 0, "rendered_skill_count": 0},
        skill_lifecycle_counts={},
        skill_version_counts=[],
        transaction_counts={},
        evaluation_counts={},
        curation_counts={},
        revocation_counts={},
        freeze={"frozen_skills": 0, "critical_canary_skills": 0},
        canary_counts={},
        drift={"violated_contracts": 0, "drift_events": 0},
        utility={
            "rollup_count": 0,
            "avg_utility": 0.0,
            "min_utility": 0.0,
            "max_utility": 0.0,
            "negative_utility_count": 0,
            "latest_computed_at": None,
        },
        audit={"audit_records": 0, "latest_audit_at": None},
        storage=[],
    )


def _operator_metrics_payload(
    *,
    workspace_key: str | None,
    window_minutes: int,
    storage_limit: int,
    ingest: dict[str, Any],
    redaction_counts: dict[str, int],
    latency: dict[str, Any],
    latency_by_operation_kind: dict[str, dict[str, Any]],
    job_status_counts: dict[str, int],
    job_kind_counts: dict[str, dict[str, int]],
    embedding_backlog: dict[str, Any],
    retrieval_decisions: dict[str, int],
    context: dict[str, Any],
    context_hints: dict[str, Any],
    skill_lifecycle_counts: dict[str, int],
    skill_version_counts: list[dict[str, Any]],
    transaction_counts: dict[str, dict[str, int]],
    evaluation_counts: dict[str, int],
    curation_counts: dict[str, dict[str, int]],
    revocation_counts: dict[str, dict[str, int]],
    freeze: dict[str, Any],
    canary_counts: dict[str, int],
    drift: dict[str, Any],
    utility: dict[str, Any],
    audit: dict[str, Any],
    storage: list[dict[str, Any]],
) -> dict[str, Any]:
    scanner_rejects = sum(
        int(row["count"])
        for row in skill_version_counts
        if row.get("scanner_status") not in {"passed", "pending"}
    )
    evaluator_failures = sum(
        int(row["count"])
        for row in skill_version_counts
        if row.get("evaluator_status") in EVALUATION_FAILURE_STATUSES
    )
    active_skill_count = skill_lifecycle_counts.get("active", 0)
    archived_skill_count = skill_lifecycle_counts.get("archived", 0)
    metrics = {
        "ingest": {
            "events_in_window": int(ingest.get("events_in_window") or 0),
            "total_events": int(ingest.get("total_events") or 0),
            "event_rate_per_minute": (
                int(ingest.get("events_in_window") or 0) / max(1, window_minutes)
            ),
        },
        "redaction_counts": redaction_counts,
        "sidecar_latency_ms": {
            "span_count": int(latency.get("span_count") or 0),
            "avg": float(latency.get("avg_ms") or 0.0),
            "p95": float(latency.get("p95_ms") or 0.0),
            "max": float(latency.get("max_ms") or 0.0),
        },
        "latency_by_operation_kind": latency_by_operation_kind,
        "spool_backlog": {
            "status": "plugin_diagnostics_required",
            "reason": "plugin spool files are outside sidecar database visibility",
        },
        "job_queue_depth": job_status_counts,
        "job_success_failure_by_type": job_kind_counts,
        "embedding_backlog": _int_dict(embedding_backlog),
        "retrieval_recall_audit_score": {
            "status": "run_recall_audit_endpoint",
            "reason": "recall audits are computed on demand and not persisted yet",
        },
        "retrieval_decisions": retrieval_decisions,
        "context_hint_injection_count": int(context_hints.get("hint_injections") or 0),
        "context_hint_rendered_skill_count": int(
            context_hints.get("rendered_skill_count") or 0
        ),
        "context_hint_token_cost": int(context.get("hint_token_cost") or 0),
        "context_hint_token_ledger_count": int(context.get("hint_token_ledger_count") or 0),
        "skill_creation_improvement_counts": {
            key: counts
            for key, counts in transaction_counts.items()
            if key in {"create_skill", "candidate_proposal", "skill_improvement", "repair"}
        },
        "scanner_reject_counts": {"skill_versions": scanner_rejects},
        "evaluation_pass_fail_counts": evaluation_counts,
        "active_skill_count": active_skill_count,
        "skill_lifecycle_counts": skill_lifecycle_counts,
        "archive_promote_counts": {
            key: counts
            for key, counts in curation_counts.items()
            if key in {"archive", "promote_archive", "merge_duplicate", "enforce_active_budget"}
        },
        "rollback_freeze_counts": {
            "revocations": revocation_counts,
            "frozen_skills": int(freeze.get("frozen_skills") or 0),
            "critical_canary_skills": int(freeze.get("critical_canary_skills") or 0),
            "canaries_by_status": canary_counts,
        },
        "drift_violation_counts": _int_dict(drift),
        "utility_deltas": _json_safe(utility),
        "postgres_table_index_growth": storage,
        "audit": _json_safe(audit),
    }
    dashboards = {
        "system_health": {
            "jobs": job_status_counts,
            "latency_ms": metrics["sidecar_latency_ms"],
            "spool_backlog": metrics["spool_backlog"],
        },
        "recent_autonomous_changes": {
            "transactions": transaction_counts,
            "curation": curation_counts,
            "revocations": revocation_counts,
        },
        "active_skills_and_utility": {
            "active_skill_count": active_skill_count,
            "utility": metrics["utility_deltas"],
        },
        "archived_skills_and_promotion_candidates": {
            "archived_skill_count": archived_skill_count,
            "archive_promote_counts": metrics["archive_promote_counts"],
        },
        "scanner_evaluator_failures": {
            "scanner_reject_counts": metrics["scanner_reject_counts"],
            "evaluator_failures": evaluator_failures,
            "evaluations": evaluation_counts,
        },
        "retrieval_context_broker_performance": {
            "retrieval_decisions": retrieval_decisions,
            "context_hint_injection_count": metrics["context_hint_injection_count"],
            "context_hint_token_cost": metrics["context_hint_token_cost"],
            "recall_audit": metrics["retrieval_recall_audit_score"],
        },
        "drift_violations": metrics["drift_violation_counts"],
        "rollback_freeze_events": metrics["rollback_freeze_counts"],
        "storage_growth": storage[:storage_limit],
        "audit_integrity": metrics["audit"],
    }
    return {
        "workspace_id": workspace_key,
        "captured_at": datetime.now(UTC).isoformat(),
        "window_minutes": window_minutes,
        "metrics": metrics,
        "dashboards": dashboards,
    }


def _counts(rows: list[asyncpg.Record], key: str) -> dict[str, int]:
    return {str(row[key]): int(row["count"]) for row in rows}


def _nested_counts(
    rows: list[asyncpg.Record],
    outer_key: str,
    inner_key: str,
) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        outer = str(row[outer_key])
        inner = str(row[inner_key])
        counts.setdefault(outer, {})[inner] = int(row["count"])
    return counts


def _latency_by_operation_kind(rows: list[asyncpg.Record]) -> dict[str, dict[str, Any]]:
    return {
        str(row["operation_kind"]): {
            "span_count": int(row["span_count"] or 0),
            "avg": float(row["avg_ms"] or 0.0),
            "p95": float(row["p95_ms"] or 0.0),
            "max": float(row["max_ms"] or 0.0),
        }
        for row in rows
    }


def _int_dict(values: dict[str, Any]) -> dict[str, int]:
    return {key: int(value or 0) for key, value in values.items()}


def _json_safe(values: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, datetime):
            safe[key] = value.isoformat()
        else:
            safe[key] = value
    return safe


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None
