from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

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


class RetrievalStore(Protocol):
    async def lexical_query(
        self,
        *,
        workspace_key: str,
        query: str,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
    ) -> RetrievalResult:
        """Run deterministic lexical retrieval and log the decision."""


class NullRetrievalStore:
    async def lexical_query(
        self,
        *,
        workspace_key: str,
        query: str,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
    ) -> RetrievalResult:
        return RetrievalResult(retrieval_log_id=None, decision="no_candidates", candidates=[])


class AsyncpgRetrievalStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def lexical_query(
        self,
        *,
        workspace_key: str,
        query: str,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
    ) -> RetrievalResult:
        if not query.strip():
            return RetrievalResult(retrieval_log_id=None, decision="empty_query", candidates=[])

        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
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
                      'skill_version_id', d.skill_version_id
                    ) AS metadata
                  FROM autoskill.body_index_documents d, q
                  WHERE d.workspace_id = $1
                    AND to_tsvector('simple', d.text_content) @@ q.query
                )
                SELECT *
                FROM (
                  SELECT * FROM evidence_candidates
                  UNION ALL
                  SELECT * FROM body_candidates
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
            log_id = await _insert_retrieval_log(
                conn,
                workspace_id=workspace_id,
                session_id=session_id,
                turn_id=turn_id,
                query=query,
                decision=decision,
                candidates=candidates,
            )

        return RetrievalResult(
            retrieval_log_id=log_id,
            decision=decision,
            candidates=candidates,
        )


async def _insert_retrieval_log(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
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
          decision,
          candidate_skill_ids,
          rendered_skill_ids,
          no_skill_control,
          metadata
        )
        VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, '{}'::uuid[], true, $6::jsonb)
        RETURNING retrieval_log_id
        """,
        workspace_id,
        session_id,
        turn_id,
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


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None
