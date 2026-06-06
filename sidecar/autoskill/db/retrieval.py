from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID, uuid4

import asyncpg

from autoskill.core.hashing import sha256_text
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class RetrievalCandidate:
    object_type: str
    object_id: UUID
    skill_id: UUID | None
    summary: str
    rank: float
    metadata: dict[str, Any]

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> RetrievalCandidate:
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return cls(
            object_type=row["object_type"],
            object_id=row["object_id"],
            skill_id=_row_get(row, "skill_id"),
            summary=row["summary"],
            rank=float(row["rank"]),
            metadata=metadata,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "object_type": self.object_type,
            "object_id": str(self.object_id),
            "skill_id": str(self.skill_id) if self.skill_id else None,
            "summary": self.summary,
            "rank": self.rank,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class RetrievalResult:
    retrieval_log_id: UUID | None
    decision: str
    candidates: list[RetrievalCandidate]


@dataclass(frozen=True)
class RetrievalLog:
    retrieval_log_id: UUID
    trace_id: UUID | None
    span_id: UUID | None
    parent_span_id: UUID | None
    session_id: str | None
    turn_id: str | None
    broker_policy_version_id: UUID | None
    decision: str
    candidate_skill_ids: list[UUID]
    rendered_skill_ids: list[UUID]
    no_skill_control: bool
    metadata: dict[str, Any]
    created_at: Any

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> RetrievalLog:
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return cls(
            retrieval_log_id=row["retrieval_log_id"],
            trace_id=_row_get(row, "trace_id"),
            span_id=_row_get(row, "span_id"),
            parent_span_id=_row_get(row, "parent_span_id"),
            session_id=_row_get(row, "session_id"),
            turn_id=_row_get(row, "turn_id"),
            broker_policy_version_id=_row_get(row, "broker_policy_version_id"),
            decision=row["decision"],
            candidate_skill_ids=list(row["candidate_skill_ids"] or []),
            rendered_skill_ids=list(row["rendered_skill_ids"] or []),
            no_skill_control=bool(row["no_skill_control"]),
            metadata=metadata,
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "retrieval_log_id": str(self.retrieval_log_id),
            "trace_id": str(self.trace_id) if self.trace_id else None,
            "span_id": str(self.span_id) if self.span_id else None,
            "parent_span_id": str(self.parent_span_id) if self.parent_span_id else None,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "broker_policy_version_id": (
                str(self.broker_policy_version_id) if self.broker_policy_version_id else None
            ),
            "decision": self.decision,
            "candidate_skill_ids": [str(skill_id) for skill_id in self.candidate_skill_ids],
            "rendered_skill_ids": [str(skill_id) for skill_id in self.rendered_skill_ids],
            "no_skill_control": self.no_skill_control,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
            if hasattr(self.created_at, "isoformat")
            else str(self.created_at),
        }


class RetrievalStore(Protocol):
    async def lexical_query(
        self,
        *,
        workspace_key: str,
        query: str,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
        record_decision: bool = True,
    ) -> RetrievalResult:
        """Run deterministic lexical retrieval and optionally log the decision."""

    async def semantic_query(
        self,
        *,
        workspace_key: str,
        embedding_model: str,
        embedding: list[float],
        embedding_profile_id: UUID | None = None,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
    ) -> RetrievalResult:
        """Run deterministic vector retrieval and log the decision."""

    async def expand_skill_graph(
        self,
        *,
        workspace_key: str,
        skill_ids: list[UUID],
        edge_kinds: list[str] | None = None,
        limit: int = 25,
    ) -> list[RetrievalCandidate]:
        """Hydrate body-level candidates connected to selected skills."""

    async def record_context_hint(
        self,
        *,
        retrieval_log_id: UUID | None,
        rendered_skill_ids: list[UUID],
        decision: str,
        suppressed: list[dict[str, object]],
        reason_codes: list[str],
        metadata: dict[str, Any] | None = None,
        broker_policy_version_id: UUID | None = None,
    ) -> None:
        """Attach broker rendering telemetry to a retrieval log."""

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        """Remove retrieval body-index documents derived from revoked objects."""

    async def invalidate_logs(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        """Mark retrieval logs affected by revoked objects."""

    async def list_recent_logs(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[RetrievalLog]:
        """Return content-safe retrieval/broker decisions for operator drill-down."""

    async def get_log(
        self,
        *,
        workspace_key: str | None = None,
        retrieval_log_id: UUID,
    ) -> RetrievalLog | None:
        """Return one content-safe retrieval/broker decision for operator drill-down."""

    async def replay_context_for_log(
        self,
        *,
        workspace_key: str,
        retrieval_log_id: UUID,
        limit: int = 8,
    ) -> list[RetrievalCandidate]:
        """Return content-safe candidate summaries for replay intent synthesis."""


class NullRetrievalStore:
    async def lexical_query(
        self,
        *,
        workspace_key: str,
        query: str,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
        record_decision: bool = True,
    ) -> RetrievalResult:
        return RetrievalResult(retrieval_log_id=None, decision="no_candidates", candidates=[])

    async def semantic_query(
        self,
        *,
        workspace_key: str,
        embedding_model: str,
        embedding: list[float],
        embedding_profile_id: UUID | None = None,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
    ) -> RetrievalResult:
        return RetrievalResult(retrieval_log_id=None, decision="no_candidates", candidates=[])

    async def expand_skill_graph(
        self,
        *,
        workspace_key: str,
        skill_ids: list[UUID],
        edge_kinds: list[str] | None = None,
        limit: int = 25,
    ) -> list[RetrievalCandidate]:
        return []

    async def record_context_hint(
        self,
        *,
        retrieval_log_id: UUID | None,
        rendered_skill_ids: list[UUID],
        decision: str,
        suppressed: list[dict[str, object]],
        reason_codes: list[str],
        metadata: dict[str, Any] | None = None,
        broker_policy_version_id: UUID | None = None,
    ) -> None:
        return None

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        return 0

    async def invalidate_logs(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        return 0

    async def list_recent_logs(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[RetrievalLog]:
        return []

    async def get_log(
        self,
        *,
        workspace_key: str | None = None,
        retrieval_log_id: UUID,
    ) -> RetrievalLog | None:
        return None

    async def replay_context_for_log(
        self,
        *,
        workspace_key: str,
        retrieval_log_id: UUID,
        limit: int = 8,
    ) -> list[RetrievalCandidate]:
        return []


class AsyncpgRetrievalStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def lexical_query(
        self,
        *,
        workspace_key: str,
        query: str,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
        record_decision: bool = True,
    ) -> RetrievalResult:
        if not query.strip():
            return RetrievalResult(retrieval_log_id=None, decision="empty_query", candidates=[])

        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = (
                await ensure_workspace(conn, workspace_key)
                if record_decision
                else await _get_workspace_id(conn, workspace_key)
            )
            if workspace_id is None:
                return RetrievalResult(
                    retrieval_log_id=None,
                    decision="no_candidates",
                    candidates=[],
                )
            rows = await conn.fetch(
                """
                WITH q AS (
                  SELECT plainto_tsquery('simple', $2) AS query
                ),
                evidence_candidates AS (
                  SELECT
                    'evidence_item'::text AS object_type,
                    e.evidence_id AS object_id,
                    NULL::uuid AS skill_id,
                    e.summary,
                    ts_rank(to_tsvector('simple', e.summary), q.query)::float AS rank,
                    jsonb_build_object(
                      'kind', e.kind,
                      'maturity', e.maturity,
                      'trust', e.trust,
                      'taint', e.taint,
                      'source_event_id', e.source_event_id
                    ) AS metadata
                  FROM autoskill.evidence_items e, q
                  WHERE e.workspace_id = $1
                    AND e.revoked_at IS NULL
                    AND to_tsvector('simple', e.summary) @@ q.query
                ),
                body_candidates AS (
                  SELECT
                    'body_index_document'::text AS object_type,
                    d.body_index_document_id AS object_id,
                    d.skill_id,
                    left(d.text_content, 240) AS summary,
                    ts_rank(to_tsvector('simple', d.text_content), q.query)::float AS rank,
                    jsonb_build_object(
                      'document_kind', d.document_kind,
                      'secret_scan_status', d.secret_scan_status,
                      'taint', d.taint,
                      'skill_version_id', d.skill_version_id,
                      'lifecycle_state', s.lifecycle_state,
                      'slug', s.slug
                    ) AS metadata
                  FROM autoskill.body_index_documents d
                  LEFT JOIN autoskill.skills s ON s.skill_id = d.skill_id
                  CROSS JOIN q
                  WHERE d.workspace_id = $1
                    AND to_tsvector('simple', d.text_content) @@ q.query
                ),
                external_skill_candidates AS (
                  SELECT
                    'external_skill'::text AS object_type,
                    e.external_skill_id AS object_id,
                    NULL::uuid AS skill_id,
                    left(
                      COALESCE(e.name, e.slug) || ': ' || COALESCE(e.description, ''),
                      240
                    ) AS summary,
                    ts_rank(
                      to_tsvector(
                        'simple',
                        COALESCE(e.name, '') || ' ' || COALESCE(e.description, '')
                      ),
                      q.query
                    )::float AS rank,
                    jsonb_build_object(
                      'source', e.source,
                      'root_path_hash', e.root_path_hash,
                      'slug', e.slug,
                      'status', e.status,
                      'ownership', 'external',
                      'file_hash', e.file_hash,
                      'risk_summary', e.risk_summary
                    ) AS metadata
                  FROM autoskill.external_skill_inventory e, q
                  WHERE e.workspace_id = $1
                    AND e.status IN ('visible', 'changed')
                    AND to_tsvector(
                      'simple',
                      COALESCE(e.name, '') || ' ' || COALESCE(e.description, '')
                    ) @@ q.query
                )
                SELECT *
                FROM (
                  SELECT * FROM evidence_candidates
                  UNION ALL
                  SELECT * FROM body_candidates
                  UNION ALL
                  SELECT * FROM external_skill_candidates
                ) candidates
                ORDER BY rank DESC, summary ASC
                LIMIT $3
                """,
                workspace_id,
                query,
                limit,
            )
            candidates = [RetrievalCandidate.from_row(row) for row in rows]
            decision = "candidates_found" if candidates else "no_candidates"
            log_id = (
                await _insert_retrieval_log(
                    conn,
                    workspace_id=workspace_id,
                    trace_id=trace_id or uuid4(),
                    span_id=span_id or uuid4(),
                    parent_span_id=parent_span_id,
                    session_id=session_id,
                    turn_id=turn_id,
                    query=query,
                    decision=decision,
                    candidates=candidates,
                )
                if record_decision
                else None
            )

        return RetrievalResult(
            retrieval_log_id=log_id,
            decision=decision,
            candidates=candidates,
        )

    async def semantic_query(
        self,
        *,
        workspace_key: str,
        embedding_model: str,
        embedding: list[float],
        embedding_profile_id: UUID | None = None,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
    ) -> RetrievalResult:
        if not embedding:
            return RetrievalResult(retrieval_log_id=None, decision="empty_query", candidates=[])

        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                WITH nearest AS (
                  SELECT
                    e.*,
                    (e.embedding <=> $3::vector)::float AS distance
                  FROM autoskill.embeddings e
                  WHERE e.workspace_id = $1
                    AND (
                      ($4::uuid IS NOT NULL AND e.embedding_profile_id = $4)
                      OR ($4::uuid IS NULL AND e.embedding_profile_id IS NULL
                        AND e.embedding_model = $2)
                    )
                    AND e.embedding_dim = $6
                  ORDER BY e.embedding <=> $3::vector
                  LIMIT $5
                ),
                body_candidates AS (
                  SELECT
                    'body_index_document'::text AS object_type,
                    d.body_index_document_id AS object_id,
                    d.skill_id,
                    left(d.text_content, 240) AS summary,
                    greatest(0.0, 1.0 - n.distance)::float AS rank,
                    jsonb_build_object(
                      'document_kind', d.document_kind,
                      'secret_scan_status', d.secret_scan_status,
                      'taint', d.taint,
                      'skill_version_id', d.skill_version_id,
                      'lifecycle_state', s.lifecycle_state,
                      'slug', s.slug,
                      'retrieval_mode', 'vector',
                      'semantic_distance', n.distance
                    ) AS metadata
                  FROM nearest n
                  JOIN autoskill.body_index_documents d
                    ON n.object_type = 'body_index_document'
                   AND n.object_id = d.body_index_document_id
                  LEFT JOIN autoskill.skills s ON s.skill_id = d.skill_id
                ),
                evidence_candidates AS (
                  SELECT
                    'evidence_item'::text AS object_type,
                    ev.evidence_id AS object_id,
                    NULL::uuid AS skill_id,
                    ev.summary,
                    greatest(0.0, 1.0 - n.distance)::float AS rank,
                    jsonb_build_object(
                      'kind', ev.kind,
                      'maturity', ev.maturity,
                      'trust', ev.trust,
                      'taint', ev.taint,
                      'source_event_id', ev.source_event_id,
                      'retrieval_mode', 'vector',
                      'semantic_distance', n.distance
                    ) AS metadata
                  FROM nearest n
                  JOIN autoskill.evidence_items ev
                    ON n.object_type = 'evidence_item'
                   AND n.object_id = ev.evidence_id
                  WHERE ev.revoked_at IS NULL
                ),
                external_skill_candidates AS (
                  SELECT
                    'external_skill'::text AS object_type,
                    ex.external_skill_id AS object_id,
                    NULL::uuid AS skill_id,
                    left(
                      COALESCE(ex.name, ex.slug) || ': ' || COALESCE(ex.description, ''),
                      240
                    ) AS summary,
                    greatest(0.0, 1.0 - n.distance)::float AS rank,
                    jsonb_build_object(
                      'source', ex.source,
                      'root_path_hash', ex.root_path_hash,
                      'slug', ex.slug,
                      'status', ex.status,
                      'ownership', 'external',
                      'file_hash', ex.file_hash,
                      'risk_summary', ex.risk_summary,
                      'retrieval_mode', 'vector',
                      'semantic_distance', n.distance
                    ) AS metadata
                  FROM nearest n
                  JOIN autoskill.external_skill_inventory ex
                    ON n.object_type = 'external_skill'
                   AND n.object_id = ex.external_skill_id
                  WHERE ex.status IN ('visible', 'changed')
                )
                SELECT *
                FROM (
                  SELECT * FROM body_candidates
                  UNION ALL
                  SELECT * FROM evidence_candidates
                  UNION ALL
                  SELECT * FROM external_skill_candidates
                ) candidates
                ORDER BY rank DESC, summary ASC
                LIMIT $5
                """,
                workspace_id,
                embedding_model,
                _vector_literal(embedding),
                embedding_profile_id,
                limit,
                len(embedding),
            )
            candidates = [RetrievalCandidate.from_row(row) for row in rows]
            decision = "semantic_candidates_found" if candidates else "semantic_no_candidates"
            log_id = await _insert_retrieval_log(
                conn,
                workspace_id=workspace_id,
                trace_id=trace_id or uuid4(),
                span_id=span_id or uuid4(),
                parent_span_id=parent_span_id,
                session_id=session_id,
                turn_id=turn_id,
                query=f"semantic:{embedding_model}:{len(embedding)}",
                decision=decision,
                candidates=candidates,
            )

        return RetrievalResult(
            retrieval_log_id=log_id,
            decision=decision,
            candidates=candidates,
        )

    async def expand_skill_graph(
        self,
        *,
        workspace_key: str,
        skill_ids: list[UUID],
        edge_kinds: list[str] | None = None,
        limit: int = 25,
    ) -> list[RetrievalCandidate]:
        if not skill_ids:
            return []
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH workspace AS (
                  SELECT workspace_id
                  FROM autoskill.workspaces
                  WHERE external_key = $1
                ),
                edges AS (
                  SELECT
                    e.from_skill_id AS source_skill_id,
                    e.to_skill_id AS related_skill_id,
                    e.edge_kind
                  FROM autoskill.skill_edges e, workspace w
                  WHERE e.workspace_id = w.workspace_id
                    AND e.from_skill_id = ANY($2::uuid[])
                    AND e.revoked_at IS NULL
                    AND ($3::text[] IS NULL OR e.edge_kind = ANY($3::text[]))
                  UNION ALL
                  SELECT
                    e.to_skill_id AS source_skill_id,
                    e.from_skill_id AS related_skill_id,
                    e.edge_kind
                  FROM autoskill.skill_edges e, workspace w
                  WHERE e.workspace_id = w.workspace_id
                    AND e.to_skill_id = ANY($2::uuid[])
                    AND e.revoked_at IS NULL
                    AND ($3::text[] IS NULL OR e.edge_kind = ANY($3::text[]))
                )
                SELECT
                  'body_index_document'::text AS object_type,
                  d.body_index_document_id AS object_id,
                  d.skill_id,
                  left(d.text_content, 240) AS summary,
                  0.0::float AS rank,
                  jsonb_build_object(
                    'document_kind', d.document_kind,
                    'secret_scan_status', d.secret_scan_status,
                    'taint', d.taint,
                    'skill_version_id', d.skill_version_id,
                    'lifecycle_state', s.lifecycle_state,
                    'slug', s.slug,
                    'graph_edge_kind', edges.edge_kind,
                    'graph_source_skill_id', edges.source_skill_id
                  ) AS metadata
                FROM edges
                JOIN autoskill.body_index_documents d ON d.skill_id = edges.related_skill_id
                JOIN autoskill.skills s ON s.skill_id = d.skill_id
                ORDER BY
                  CASE edges.edge_kind
                    WHEN 'prerequisite' THEN 0
                    WHEN 'conflict' THEN 1
                    WHEN 'shadow' THEN 2
                    ELSE 3
                  END,
                  s.slug ASC,
                  d.created_at DESC
                LIMIT $4
                """,
                workspace_key,
                skill_ids,
                edge_kinds,
                limit,
            )
            return [RetrievalCandidate.from_row(row) for row in rows]

    async def record_context_hint(
        self,
        *,
        retrieval_log_id: UUID | None,
        rendered_skill_ids: list[UUID],
        decision: str,
        suppressed: list[dict[str, object]],
        reason_codes: list[str],
        metadata: dict[str, Any] | None = None,
        broker_policy_version_id: UUID | None = None,
    ) -> None:
        if retrieval_log_id is None:
            return
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE autoskill.retrieval_logs
                SET rendered_skill_ids = $2,
                    no_skill_control = ($3 IN ('no_skill', 'defer_skill')),
                    decision = $3,
                    broker_policy_version_id = $4,
                    metadata = metadata || $5::jsonb
                WHERE retrieval_log_id = $1
                """,
                retrieval_log_id,
                rendered_skill_ids,
                decision,
                broker_policy_version_id,
                json.dumps(
                    {
                        "suppressed": suppressed,
                        "reason_codes": reason_codes,
                        "rendered_skill_count": len(rendered_skill_ids),
                        "broker_policy_version_id": (
                            str(broker_policy_version_id)
                            if broker_policy_version_id
                            else None
                        ),
                    }
                    | (metadata or {}),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        object_keys = _object_keys(objects)
        if not object_keys:
            return 0
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                WITH targets AS (
                  SELECT *
                  FROM unnest($2::text[], $3::uuid[]) AS target(object_type, object_id)
                )
                DELETE FROM autoskill.body_index_documents d
                USING autoskill.workspaces w, targets t
                WHERE d.workspace_id = w.workspace_id
                  AND w.external_key = $1
                  AND (
                    (t.object_type = 'body_index_document'
                      AND d.body_index_document_id = t.object_id)
                    OR (t.object_type = 'skill_version'
                      AND d.skill_version_id = t.object_id)
                    OR (t.object_type = 'skill'
                      AND d.skill_id = t.object_id)
                    OR (t.object_type = 'compiled_skill_file'
                      AND d.skill_version_id = t.object_id)
                  )
                """,
                workspace_key,
                [object_type for object_type, _object_id in object_keys],
                [object_id for _object_type, object_id in object_keys],
            )
            return _command_count(result)

    async def invalidate_logs(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        object_keys = _object_keys(objects)
        if not object_keys:
            return 0
        pool = await self._get_pool()
        skill_ids = [
            object_id
            for object_type, object_id in object_keys
            if object_type in {"skill", "skill_version", "compiled_skill_file"}
        ]
        log_ids = [
            object_id
            for object_type, object_id in object_keys
            if object_type == "retrieval_log"
        ]
        source_ids = [
            object_id
            for object_type, object_id in object_keys
            if object_type in {"evidence_item", "body_index_document", "external_skill"}
        ]
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE autoskill.retrieval_logs rl
                SET metadata = rl.metadata || jsonb_build_object(
                  'revoked', true,
                  'revoked_at', now(),
                  'revocation_reason', 'derived_object_revoked'
                )
                FROM autoskill.workspaces w
                WHERE rl.workspace_id = w.workspace_id
                  AND w.external_key = $1
                  AND (
                    ($2::uuid[] <> '{}'::uuid[]
                      AND (
                        rl.candidate_skill_ids && $2::uuid[]
                        OR rl.rendered_skill_ids && $2::uuid[]
                      ))
                    OR ($3::uuid[] <> '{}'::uuid[]
                      AND rl.retrieval_log_id = ANY($3::uuid[]))
                    OR ($4::uuid[] <> '{}'::uuid[]
                      AND EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements(rl.metadata->'candidate_objects') item
                        WHERE (item->>'object_id')::uuid = ANY($4::uuid[])
                      ))
                  )
                """,
                workspace_key,
                skill_ids,
                log_ids,
                source_ids,
            )
            return _command_count(result)

    async def list_recent_logs(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[RetrievalLog]:
        pool = await self._get_pool()
        bounded_limit = max(1, min(limit, 500))
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                  rl.retrieval_log_id,
                  rl.trace_id,
                  rl.span_id,
                  rl.parent_span_id,
                  rl.session_id,
                  rl.turn_id,
                  rl.broker_policy_version_id,
                  rl.decision,
                  rl.candidate_skill_ids,
                  rl.rendered_skill_ids,
                  rl.no_skill_control,
                  rl.metadata,
                  rl.created_at
                FROM autoskill.retrieval_logs rl
                JOIN autoskill.workspaces w ON w.workspace_id = rl.workspace_id
                WHERE ($1::text IS NULL OR w.external_key = $1)
                ORDER BY rl.created_at DESC, rl.retrieval_log_id DESC
                LIMIT $2
                """,
                workspace_key,
                bounded_limit,
            )
        return [RetrievalLog.from_row(row) for row in rows]

    async def get_log(
        self,
        *,
        workspace_key: str | None = None,
        retrieval_log_id: UUID,
    ) -> RetrievalLog | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                  rl.retrieval_log_id,
                  rl.trace_id,
                  rl.span_id,
                  rl.parent_span_id,
                  rl.session_id,
                  rl.turn_id,
                  rl.broker_policy_version_id,
                  rl.decision,
                  rl.candidate_skill_ids,
                  rl.rendered_skill_ids,
                  rl.no_skill_control,
                  rl.metadata,
                  rl.created_at
                FROM autoskill.retrieval_logs rl
                JOIN autoskill.workspaces w ON w.workspace_id = rl.workspace_id
                WHERE rl.retrieval_log_id = $1
                  AND ($2::text IS NULL OR w.external_key = $2)
                """,
                retrieval_log_id,
                workspace_key,
            )
        return RetrievalLog.from_row(row) if row else None

    async def replay_context_for_log(
        self,
        *,
        workspace_key: str,
        retrieval_log_id: UUID,
        limit: int = 8,
    ) -> list[RetrievalCandidate]:
        pool = await self._get_pool()
        bounded_limit = max(1, min(limit, 25))
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH candidate_objects AS (
                  SELECT
                    (item->>'object_id')::uuid AS object_id,
                    item->>'object_type' AS object_type,
                    COALESCE((item->>'rank')::double precision, 0.0) AS rank,
                    ordinality
                  FROM autoskill.retrieval_logs rl
                  JOIN autoskill.workspaces w ON w.workspace_id = rl.workspace_id
                  CROSS JOIN LATERAL jsonb_array_elements(
                    COALESCE(rl.metadata->'candidate_objects', '[]'::jsonb)
                  ) WITH ORDINALITY AS expanded(item, ordinality)
                  WHERE rl.retrieval_log_id = $1
                    AND w.external_key = $2
                ),
                hydrated AS (
                  SELECT
                    co.object_type,
                    co.object_id,
                    b.skill_id,
                    left(b.text_content, 700) AS summary,
                    co.rank,
                    jsonb_build_object(
                      'source', 'body_index_document',
                      'document_kind', b.document_kind,
                      'secret_scan_status', b.secret_scan_status,
                      'taint', b.taint
                    ) AS metadata,
                    co.ordinality
                  FROM candidate_objects co
                  JOIN autoskill.body_index_documents b
                    ON b.body_index_document_id = co.object_id
                  WHERE co.object_type = 'body_index_document'

                  UNION ALL

                  SELECT
                    co.object_type,
                    co.object_id,
                    NULL::uuid AS skill_id,
                    left(e.summary, 700) AS summary,
                    co.rank,
                    jsonb_build_object(
                      'source', 'evidence_item',
                      'kind', e.kind,
                      'maturity', e.maturity,
                      'trust', e.trust,
                      'taint', e.taint
                    ) AS metadata,
                    co.ordinality
                  FROM candidate_objects co
                  JOIN autoskill.evidence_items e
                    ON e.evidence_id = co.object_id
                  WHERE co.object_type = 'evidence_item'
                    AND e.revoked_at IS NULL

                  UNION ALL

                  SELECT
                    co.object_type,
                    co.object_id,
                    NULL::uuid AS skill_id,
                    left(concat_ws(' - ', ex.name, ex.description), 700) AS summary,
                    co.rank,
                    jsonb_build_object(
                      'source', 'external_skill',
                      'slug', ex.slug,
                      'status', ex.status,
                      'risk_summary', ex.risk_summary
                    ) AS metadata,
                    co.ordinality
                  FROM candidate_objects co
                  JOIN autoskill.external_skill_inventory ex
                    ON ex.external_skill_id = co.object_id
                  WHERE co.object_type = 'external_skill'
                )
                SELECT object_type, object_id, skill_id, summary, rank, metadata
                FROM hydrated
                WHERE summary IS NOT NULL AND btrim(summary) <> ''
                ORDER BY ordinality
                LIMIT $3
                """,
                retrieval_log_id,
                workspace_key,
                bounded_limit,
            )
        return [RetrievalCandidate.from_row(row) for row in rows]


async def _insert_retrieval_log(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    trace_id: UUID,
    span_id: UUID,
    parent_span_id: UUID | None,
    session_id: str | None,
    turn_id: str | None,
    query: str,
    decision: str,
    candidates: list[RetrievalCandidate],
) -> UUID:
    row = await conn.fetchrow(
        """
        INSERT INTO autoskill.retrieval_logs (
          retrieval_log_id,
          workspace_id,
          session_id,
          turn_id,
          trace_id,
          span_id,
          parent_span_id,
          decision,
          candidate_skill_ids,
          rendered_skill_ids,
          no_skill_control,
          metadata
        )
        VALUES (
          gen_random_uuid(), $1, $2, $3, $4, $5, $6,
          $7, $8, '{}'::uuid[], true, $9::jsonb
        )
        RETURNING retrieval_log_id
        """,
        workspace_id,
        session_id,
        turn_id,
        trace_id,
        span_id,
        parent_span_id,
        decision,
        [candidate.skill_id for candidate in candidates if candidate.skill_id],
        json.dumps(
            {
                "query_hash": sha256_text(query.strip().lower()),
                "candidate_count": len(candidates),
                "candidate_objects": [
                    {
                        "object_type": candidate.object_type,
                        "object_id": str(candidate.object_id),
                        "rank": candidate.rank,
                    }
                    for candidate in candidates
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    return row["retrieval_log_id"]


async def _get_workspace_id(
    conn: asyncpg.Connection,
    workspace_key: str,
) -> UUID | None:
    return await conn.fetchval(
        """
        SELECT workspace_id
        FROM autoskill.workspaces
        WHERE external_key = $1
        """,
        workspace_key,
    )


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in embedding) + "]"


def _object_keys(objects: list[dict[str, str]]) -> list[tuple[str, UUID]]:
    keys: list[tuple[str, UUID]] = []
    for item in objects:
        object_type = str(item.get("object_type") or "")
        object_id = item.get("object_id")
        if not object_type or object_id is None:
            continue
        try:
            keys.append((object_type, UUID(str(object_id))))
        except ValueError:
            continue
    return keys


def _command_count(command_tag: str) -> int:
    try:
        return int(command_tag.rsplit(" ", 1)[1])
    except (IndexError, ValueError):
        return 0
