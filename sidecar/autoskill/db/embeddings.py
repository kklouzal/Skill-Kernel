from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.core.hashing import sha256_text
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace

EMBEDDING_DIM = 1536
EMBEDDING_OBJECT_TYPE_BODY_INDEX_DOCUMENT = "body_index_document"
EMBEDDING_OBJECT_TYPE_EVIDENCE_ITEM = "evidence_item"
EMBEDDING_OBJECT_TYPE_EXTERNAL_SKILL = "external_skill"
EMBEDDING_OBJECT_TYPE_HISTORICAL_IMPORT_CHUNK = "historical_import_chunk"


@dataclass(frozen=True)
class EmbeddingRecord:
    embedding_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    object_type: str
    object_id: UUID
    skill_id: UUID | None
    embedding_profile_id: UUID | None
    embedding_model: str
    embedding_dim: int
    text_hash: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, object]) -> EmbeddingRecord:
        return cls(
            embedding_id=row["embedding_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            object_type=row["object_type"],
            object_id=row["object_id"],
            skill_id=_row_get(row, "skill_id"),
            embedding_profile_id=_row_get(row, "embedding_profile_id"),
            embedding_model=row["embedding_model"],
            embedding_dim=row["embedding_dim"],
            text_hash=row["text_hash"],
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, object]:
        return {
            "embedding_id": str(self.embedding_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "object_type": self.object_type,
            "object_id": str(self.object_id),
            "skill_id": str(self.skill_id) if self.skill_id else None,
            "embedding_profile_id": (
                str(self.embedding_profile_id) if self.embedding_profile_id else None
            ),
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
            "text_hash": self.text_hash,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class EmbeddingUpsertResult:
    embedding: EmbeddingRecord
    created: bool


@dataclass(frozen=True)
class EmbeddingSearchCandidate:
    embedding: EmbeddingRecord
    distance: float

    def to_json(self) -> dict[str, object]:
        payload = self.embedding.to_json()
        payload["distance"] = self.distance
        return payload


@dataclass(frozen=True)
class EmbeddingRecallAuditResult:
    sampled: int
    k: int
    min_recall: float
    avg_recall: float
    failures: list[dict[str, Any]]

    def to_json(self) -> dict[str, object]:
        return {
            "sampled": self.sampled,
            "k": self.k,
            "min_recall": self.min_recall,
            "avg_recall": self.avg_recall,
            "failures": self.failures,
        }


@dataclass(frozen=True)
class EmbeddingSourceText:
    object_type: str
    object_id: UUID
    workspace_key: str
    skill_id: UUID | None
    text: str
    text_hash: str

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, object]) -> EmbeddingSourceText:
        return cls(
            object_type=row["object_type"],
            object_id=row["object_id"],
            workspace_key=row["workspace_key"],
            skill_id=_row_get(row, "skill_id"),
            text=row["text"],
            text_hash=row["text_hash"],
        )

    def to_json(self) -> dict[str, object]:
        return {
            "object_type": self.object_type,
            "object_id": str(self.object_id),
            "workspace_key": self.workspace_key,
            "skill_id": str(self.skill_id) if self.skill_id else None,
            "text_hash": self.text_hash,
        }


class EmbeddingStore(Protocol):
    async def list_unembedded_sources(
        self,
        *,
        embedding_model: str,
        embedding_profile_id: UUID | None = None,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[EmbeddingSourceText]:
        """List evidence/body text that does not yet have this model embedding."""

    async def upsert_embedding(
        self,
        *,
        workspace_key: str,
        object_type: str,
        object_id: UUID,
        embedding_model: str,
        embedding: list[float],
        text: str,
        skill_id: UUID | None = None,
        embedding_profile_id: UUID | None = None,
    ) -> EmbeddingUpsertResult:
        """Create or replace one embedding record."""

    async def search_embeddings(
        self,
        *,
        workspace_key: str,
        embedding_model: str,
        embedding: list[float],
        embedding_profile_id: UUID | None = None,
        object_type: str | None = None,
        limit: int = 10,
    ) -> list[EmbeddingSearchCandidate]:
        """Search nearest embeddings with exact pgvector distance."""

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        """Remove embeddings derived from revoked objects."""

    async def audit_recall(
        self,
        *,
        workspace_key: str,
        embedding_model: str,
        embedding_profile_id: UUID | None = None,
        object_type: str | None = None,
        sample_size: int = 10,
        k: int = 10,
        min_recall: float = 0.95,
    ) -> EmbeddingRecallAuditResult:
        """Compare indexed nearest-neighbor recall against exact pgvector ordering."""


class NullEmbeddingStore:
    async def list_unembedded_sources(
        self,
        *,
        embedding_model: str,
        embedding_profile_id: UUID | None = None,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[EmbeddingSourceText]:
        return []

    async def upsert_embedding(
        self,
        *,
        workspace_key: str,
        object_type: str,
        object_id: UUID,
        embedding_model: str,
        embedding: list[float],
        text: str,
        skill_id: UUID | None = None,
        embedding_profile_id: UUID | None = None,
    ) -> EmbeddingUpsertResult:
        _validate_embedding(embedding)
        now = datetime.now(UTC)
        record = EmbeddingRecord(
            embedding_id=UUID("00000000-0000-0000-0000-000000000000"),
            workspace_id=None,
            workspace_key=workspace_key,
            object_type=object_type,
            object_id=object_id,
            skill_id=skill_id,
            embedding_profile_id=embedding_profile_id,
            embedding_model=embedding_model,
            embedding_dim=len(embedding),
            text_hash=sha256_text(text),
            created_at=now,
        )
        return EmbeddingUpsertResult(embedding=record, created=True)

    async def search_embeddings(
        self,
        *,
        workspace_key: str,
        embedding_model: str,
        embedding: list[float],
        embedding_profile_id: UUID | None = None,
        object_type: str | None = None,
        limit: int = 10,
    ) -> list[EmbeddingSearchCandidate]:
        _validate_embedding(embedding)
        return []

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        return 0

    async def audit_recall(
        self,
        *,
        workspace_key: str,
        embedding_model: str,
        embedding_profile_id: UUID | None = None,
        object_type: str | None = None,
        sample_size: int = 10,
        k: int = 10,
        min_recall: float = 0.95,
    ) -> EmbeddingRecallAuditResult:
        return EmbeddingRecallAuditResult(
            sampled=0,
            k=k,
            min_recall=1.0,
            avg_recall=1.0,
            failures=[],
        )


class AsyncpgEmbeddingStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def list_unembedded_sources(
        self,
        *,
        embedding_model: str,
        embedding_profile_id: UUID | None = None,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[EmbeddingSourceText]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH sources AS (
                  SELECT
                    'evidence_item'::text AS object_type,
                    e.evidence_id AS object_id,
                    w.external_key AS workspace_key,
                    NULL::uuid AS skill_id,
                    e.summary AS text,
                    encode(digest(e.summary, 'sha256'), 'hex') AS text_hash,
                    e.created_at
                  FROM autoskill.evidence_items e
                  JOIN autoskill.workspaces w USING (workspace_id)
                  WHERE e.revoked_at IS NULL
                    AND ($1::text IS NULL OR w.external_key = $1)
                  UNION ALL
                  SELECT
                    'body_index_document'::text AS object_type,
                    d.body_index_document_id AS object_id,
                    w.external_key AS workspace_key,
                    d.skill_id,
                    d.text_content AS text,
                    d.text_hash,
                    d.created_at
                  FROM autoskill.body_index_documents d
                  JOIN autoskill.workspaces w USING (workspace_id)
                  WHERE ($1::text IS NULL OR w.external_key = $1)
                  UNION ALL
                  SELECT
                    'external_skill'::text AS object_type,
                    e.external_skill_id AS object_id,
                    w.external_key AS workspace_key,
                    NULL::uuid AS skill_id,
                    source_text.text,
                    encode(digest(source_text.text, 'sha256'), 'hex') AS text_hash,
                    e.updated_at AS created_at
                  FROM autoskill.external_skill_inventory e
                  JOIN autoskill.workspaces w USING (workspace_id)
                  CROSS JOIN LATERAL (
                    SELECT trim(concat_ws(
                      E'\n',
                      'External skill: ' || e.slug,
                      CASE
                        WHEN coalesce(trim(e.name), '') = '' THEN NULL
                        ELSE 'Name: ' || trim(e.name)
                      END,
                      CASE
                        WHEN coalesce(trim(e.description), '') = '' THEN NULL
                        ELSE 'Description: ' || trim(e.description)
                      END
                    )) AS text
                  ) source_text
                  WHERE e.status IN ('visible', 'changed')
                    AND source_text.text <> ''
                    AND ($1::text IS NULL OR w.external_key = $1)
                  UNION ALL
                  SELECT
                    'historical_import_chunk'::text AS object_type,
                    c.historical_import_chunk_id AS object_id,
                    w.external_key AS workspace_key,
                    NULL::uuid AS skill_id,
                    c.redacted_text AS text,
                    c.content_hash AS text_hash,
                    c.created_at
                  FROM autoskill.historical_import_chunks c
                  JOIN autoskill.workspaces w USING (workspace_id)
                  WHERE c.status = 'observed'
                    AND trim(c.redacted_text) <> ''
                    AND ($1::text IS NULL OR w.external_key = $1)
                )
                SELECT s.*
                FROM sources s
                LEFT JOIN autoskill.embeddings existing
                  ON existing.object_type = s.object_type
                 AND existing.object_id = s.object_id
                 AND (
                   ($3::uuid IS NOT NULL AND existing.embedding_profile_id = $3)
                   OR ($3::uuid IS NULL AND existing.embedding_profile_id IS NULL
                     AND existing.embedding_model = $2)
                 )
                 AND existing.text_hash = s.text_hash
                WHERE existing.embedding_id IS NULL
                ORDER BY s.created_at ASC, s.object_type ASC
                LIMIT $4
                """,
                workspace_key,
                embedding_model,
                embedding_profile_id,
                limit,
            )
            return [EmbeddingSourceText.from_row(row) for row in rows]

    async def upsert_embedding(
        self,
        *,
        workspace_key: str,
        object_type: str,
        object_id: UUID,
        embedding_model: str,
        embedding: list[float],
        text: str,
        skill_id: UUID | None = None,
        embedding_profile_id: UUID | None = None,
    ) -> EmbeddingUpsertResult:
        _validate_embedding(embedding)
        embedding_dim = len(embedding)
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            conflict_target = (
                "(workspace_id, object_type, object_id, embedding_profile_id) "
                "WHERE embedding_profile_id IS NOT NULL"
                if embedding_profile_id is not None
                else "(workspace_id, object_type, object_id, embedding_model) "
                "WHERE embedding_profile_id IS NULL"
            )
            row = await conn.fetchrow(
                f"""
                INSERT INTO autoskill.embeddings (
                  embedding_id,
                  workspace_id,
                  object_type,
                  object_id,
                  skill_id,
                  embedding_profile_id,
                  embedding_model,
                  embedding_dim,
                  embedding,
                  text_hash
                )
                VALUES (
                  gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8::vector, $9
                )
                ON CONFLICT {conflict_target} DO UPDATE
                SET embedding = EXCLUDED.embedding,
                    embedding_dim = EXCLUDED.embedding_dim,
                    embedding_profile_id = EXCLUDED.embedding_profile_id,
                    embedding_model = EXCLUDED.embedding_model,
                    text_hash = EXCLUDED.text_hash
                RETURNING *, (xmax = 0) AS created
                """,
                workspace_id,
                object_type,
                object_id,
                skill_id,
                embedding_profile_id,
                embedding_model,
                embedding_dim,
                _vector_literal(embedding),
                sha256_text(text),
            )
            return EmbeddingUpsertResult(
                embedding=EmbeddingRecord.from_row({**dict(row), "workspace_key": workspace_key}),
                created=bool(row["created"]),
            )

    async def search_embeddings(
        self,
        *,
        workspace_key: str,
        embedding_model: str,
        embedding: list[float],
        embedding_profile_id: UUID | None = None,
        object_type: str | None = None,
        limit: int = 10,
    ) -> list[EmbeddingSearchCandidate]:
        _validate_embedding(embedding)
        embedding_dim = len(embedding)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT e.*,
                       w.external_key AS workspace_key,
                       (e.embedding <=> $3::vector)::float AS distance
                FROM autoskill.embeddings e
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE w.external_key = $1
                  AND (
                    ($4::uuid IS NOT NULL AND e.embedding_profile_id = $4)
                    OR ($4::uuid IS NULL AND e.embedding_profile_id IS NULL
                      AND e.embedding_model = $2)
                  )
                  AND e.embedding_dim = $7
                  AND ($5::text IS NULL OR e.object_type = $5)
                ORDER BY e.embedding <=> $3::vector
                LIMIT $6
                """,
                workspace_key,
                embedding_model,
                _vector_literal(embedding),
                embedding_profile_id,
                object_type,
                limit,
                embedding_dim,
            )
            return [
                EmbeddingSearchCandidate(
                    embedding=EmbeddingRecord.from_row(row),
                    distance=float(row["distance"]),
                )
                for row in rows
            ]

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
                DELETE FROM autoskill.embeddings e
                USING autoskill.workspaces w, targets t
                WHERE e.workspace_id = w.workspace_id
                  AND w.external_key = $1
                  AND (
                    (e.object_type = t.object_type AND e.object_id = t.object_id)
                    OR (t.object_type = 'skill' AND e.skill_id = t.object_id)
                    OR (t.object_type = 'skill_version'
                      AND EXISTS (
                        SELECT 1
                        FROM autoskill.body_index_documents d
                        WHERE d.body_index_document_id = e.object_id
                          AND d.skill_version_id = t.object_id
                      ))
                    OR (t.object_type = 'compiled_skill_file'
                      AND EXISTS (
                        SELECT 1
                        FROM autoskill.body_index_documents d
                        WHERE d.body_index_document_id = e.object_id
                          AND d.skill_version_id = t.object_id
                      ))
                  )
                """,
                workspace_key,
                [object_type for object_type, _object_id in object_keys],
                [object_id for _object_type, object_id in object_keys],
            )
            return _command_count(result)

    async def audit_recall(
        self,
        *,
        workspace_key: str,
        embedding_model: str,
        embedding_profile_id: UUID | None = None,
        object_type: str | None = None,
        sample_size: int = 10,
        k: int = 10,
        min_recall: float = 0.95,
    ) -> EmbeddingRecallAuditResult:
        pool = await self._get_pool()
        sample_limit = max(1, min(sample_size, 100))
        result_limit = max(1, min(k, 100))
        failures: list[dict[str, Any]] = []
        recalls: list[float] = []
        async with pool.acquire() as conn, conn.transaction():
            samples = await conn.fetch(
                """
                SELECT
                  e.embedding_id,
                  e.object_type,
                  e.object_id,
                  e.embedding_dim,
                  e.embedding::text AS embedding
                FROM autoskill.embeddings e
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE w.external_key = $1
                  AND (
                    ($3::uuid IS NOT NULL AND e.embedding_profile_id = $3)
                    OR ($3::uuid IS NULL AND e.embedding_profile_id IS NULL
                      AND e.embedding_model = $2)
                  )
                  AND ($4::text IS NULL OR e.object_type = $4)
                ORDER BY e.created_at DESC, e.embedding_id ASC
                LIMIT $5
                """,
                workspace_key,
                embedding_model,
                embedding_profile_id,
                object_type,
                sample_limit,
            )
            for sample in samples:
                approximate_ids = await _nearest_embedding_ids(
                    conn,
                    workspace_key=workspace_key,
                    embedding_model=embedding_model,
                    embedding_profile_id=embedding_profile_id,
                    embedding=str(sample["embedding"]),
                    embedding_dim=int(sample["embedding_dim"]),
                    object_type=object_type,
                    limit=result_limit,
                    prefer_index=True,
                )
                exact_ids = await _nearest_embedding_ids(
                    conn,
                    workspace_key=workspace_key,
                    embedding_model=embedding_model,
                    embedding_profile_id=embedding_profile_id,
                    embedding=str(sample["embedding"]),
                    embedding_dim=int(sample["embedding_dim"]),
                    object_type=object_type,
                    limit=result_limit,
                    prefer_index=False,
                )
                if not exact_ids:
                    continue
                recall = len(set(approximate_ids) & set(exact_ids)) / len(exact_ids)
                recalls.append(recall)
                if recall < min_recall:
                    failures.append(
                        {
                            "embedding_id": str(sample["embedding_id"]),
                            "object_type": sample["object_type"],
                            "object_id": str(sample["object_id"]),
                            "recall": round(recall, 4),
                            "expected_ids": [str(item) for item in exact_ids],
                            "observed_ids": [str(item) for item in approximate_ids],
                        }
                    )
        if not recalls:
            return EmbeddingRecallAuditResult(
                sampled=0,
                k=result_limit,
                min_recall=1.0,
                avg_recall=1.0,
                failures=[],
            )
        return EmbeddingRecallAuditResult(
            sampled=len(recalls),
            k=result_limit,
            min_recall=round(min(recalls), 4),
            avg_recall=round(sum(recalls) / len(recalls), 4),
            failures=failures,
        )


async def _nearest_embedding_ids(
    conn: asyncpg.Connection,
    *,
    workspace_key: str,
    embedding_model: str,
    embedding_profile_id: UUID | None,
    embedding: str,
    embedding_dim: int,
    object_type: str | None,
    limit: int,
    prefer_index: bool,
) -> list[UUID]:
    if prefer_index:
        await conn.execute("SET LOCAL enable_seqscan = off")
        await conn.execute("SET LOCAL enable_bitmapscan = off")
    else:
        await conn.execute("SET LOCAL enable_indexscan = off")
        await conn.execute("SET LOCAL enable_bitmapscan = off")
    rows = await conn.fetch(
        """
        SELECT e.embedding_id
        FROM autoskill.embeddings e
        JOIN autoskill.workspaces w USING (workspace_id)
        WHERE w.external_key = $1
          AND (
            ($4::uuid IS NOT NULL AND e.embedding_profile_id = $4)
            OR ($4::uuid IS NULL AND e.embedding_profile_id IS NULL
              AND e.embedding_model = $2)
          )
          AND e.embedding_dim = $7
          AND ($5::text IS NULL OR e.object_type = $5)
        ORDER BY e.embedding <=> $3::vector
        LIMIT $6
        """,
        workspace_key,
        embedding_model,
        embedding,
        embedding_profile_id,
        object_type,
        limit,
        embedding_dim,
    )
    await conn.execute("RESET enable_seqscan")
    await conn.execute("RESET enable_indexscan")
    await conn.execute("RESET enable_bitmapscan")
    return [row["embedding_id"] for row in rows]


def _validate_embedding(embedding: list[float]) -> None:
    if not embedding:
        raise ValueError("embedding must not be empty")
    if not all(isfinite(value) for value in embedding):
        raise ValueError("embedding values must be finite")
    if not any(value != 0.0 for value in embedding):
        raise ValueError("embedding must not be all zeros")


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in embedding) + "]"


def _row_get(row: asyncpg.Record | dict[str, object], key: str) -> object:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None


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
