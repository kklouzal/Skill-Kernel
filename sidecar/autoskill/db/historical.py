from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

import asyncpg

from autoskill.core.hashing import sha256_text
from autoskill.core.redaction import redact_text
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace

HISTORICAL_SOURCE_KINDS = {
    "session_store",
    "transcript",
    "transcript_corpus",
    "trajectory",
    "compaction_summary",
    "workspace_memory",
    "workspace_context",
    "task_record",
    "taskflow_record",
    "plugin_hook_manifest",
    "plugin_manifest",
    "plugin_session_state",
    "plugin_source",
    "queued_injection",
    "active_memory",
    "diagnostics_export",
    "media_artifact",
    "observability_export",
    "channel_media",
    "transcription",
    "preprocessing_artifact",
    "existing_skill",
    "other",
}
HISTORICAL_SOURCE_STATUSES = {"discovered", "inventory_only", "imported", "revoked"}
HISTORICAL_CHUNK_STATUSES = {"observed", "revoked"}
HISTORICAL_TRUST_LEVELS = {"trusted", "tainted", "untrusted"}


@dataclass(frozen=True)
class HistoricalSourceInput:
    source_kind: str
    source_key: str
    fingerprint: str
    parser_version: str
    redaction_policy_version: str
    trust_level: str = "tainted"
    taint: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    status: str = "discovered"


@dataclass(frozen=True)
class HistoricalSourceRecord:
    historical_import_source_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    source_kind: str
    source_key: str
    fingerprint: str
    parser_version: str
    redaction_policy_version: str
    trust_level: str
    taint: dict[str, Any]
    metadata: dict[str, Any]
    status: str
    last_seen_at: datetime
    imported_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> HistoricalSourceRecord:
        return cls(
            historical_import_source_id=row["historical_import_source_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            source_kind=row["source_kind"],
            source_key=row["source_key"],
            fingerprint=row["fingerprint"],
            parser_version=row["parser_version"],
            redaction_policy_version=row["redaction_policy_version"],
            trust_level=row["trust_level"],
            taint=_json_dict(_row_get(row, "taint")),
            metadata=_json_dict(_row_get(row, "metadata")),
            status=row["status"],
            last_seen_at=row["last_seen_at"],
            imported_at=_row_get(row, "imported_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_json(self) -> dict[str, object]:
        return {
            "historical_import_source_id": str(self.historical_import_source_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "source_kind": self.source_kind,
            "source_key": self.source_key,
            "fingerprint": self.fingerprint,
            "parser_version": self.parser_version,
            "redaction_policy_version": self.redaction_policy_version,
            "trust_level": self.trust_level,
            "taint": self.taint,
            "metadata": self.metadata,
            "status": self.status,
            "last_seen_at": self.last_seen_at.isoformat(),
            "imported_at": self.imported_at.isoformat() if self.imported_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class HistoricalChunkInput:
    source_kind: str
    source_key: str
    fingerprint: str
    item_key: str
    chunk_index: int
    redacted_text: str
    parser_version: str
    redaction_policy_version: str
    chunk_kind: str = "redacted_text"
    token_estimate: int = 0
    trust_level: str = "tainted"
    taint: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    def storage_redacted(self) -> HistoricalChunkInput:
        redacted_text = redact_text(self.redacted_text)
        if redacted_text == self.redacted_text:
            return self
        taint = dict(self.taint or {})
        taint["storage_redacted"] = True
        return HistoricalChunkInput(
            source_kind=self.source_kind,
            source_key=self.source_key,
            fingerprint=self.fingerprint,
            item_key=self.item_key,
            chunk_index=self.chunk_index,
            redacted_text=redacted_text,
            parser_version=self.parser_version,
            redaction_policy_version=self.redaction_policy_version,
            chunk_kind=self.chunk_kind,
            token_estimate=self.token_estimate,
            trust_level=self.trust_level,
            taint=taint,
            metadata=self.metadata,
        )


@dataclass(frozen=True)
class HistoricalChunkRecord:
    historical_import_chunk_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    historical_import_source_id: UUID
    item_key: str
    chunk_index: int
    source_item_locator_hash: str | None
    source_item_kind: str | None
    item_key_hash: str | None
    line_range_hash: str | None
    record_index: int | None
    chunk_kind: str
    content_hash: str
    redacted_text: str
    token_estimate: int
    parser_version: str
    redaction_policy_version: str
    trust_level: str
    taint: dict[str, Any]
    metadata: dict[str, Any]
    status: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> HistoricalChunkRecord:
        return cls(
            historical_import_chunk_id=row["historical_import_chunk_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            historical_import_source_id=row["historical_import_source_id"],
            item_key=row["item_key"],
            chunk_index=row["chunk_index"],
            source_item_locator_hash=_row_get(row, "source_item_locator_hash"),
            source_item_kind=_row_get(row, "source_item_kind"),
            item_key_hash=_row_get(row, "item_key_hash"),
            line_range_hash=_row_get(row, "line_range_hash"),
            record_index=_row_get(row, "record_index"),
            chunk_kind=row["chunk_kind"],
            content_hash=row["content_hash"],
            redacted_text=row["redacted_text"],
            token_estimate=row["token_estimate"],
            parser_version=row["parser_version"],
            redaction_policy_version=row["redaction_policy_version"],
            trust_level=row["trust_level"],
            taint=_json_dict(_row_get(row, "taint")),
            metadata=_json_dict(_row_get(row, "metadata")),
            status=row["status"],
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, object]:
        return {
            "historical_import_chunk_id": str(self.historical_import_chunk_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "historical_import_source_id": str(self.historical_import_source_id),
            "item_key": self.item_key,
            "chunk_index": self.chunk_index,
            "source_item_locator_hash": self.source_item_locator_hash,
            "source_item_kind": self.source_item_kind,
            "item_key_hash": self.item_key_hash,
            "line_range_hash": self.line_range_hash,
            "record_index": self.record_index,
            "chunk_kind": self.chunk_kind,
            "content_hash": self.content_hash,
            "redacted_text": self.redacted_text,
            "token_estimate": self.token_estimate,
            "parser_version": self.parser_version,
            "redaction_policy_version": self.redaction_policy_version,
            "trust_level": self.trust_level,
            "taint": self.taint,
            "metadata": self.metadata,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class HistoricalSourceUpsertResult:
    created: int
    updated: int
    sources: list[HistoricalSourceRecord]

    def to_json(self) -> dict[str, object]:
        return {
            "created": self.created,
            "updated": self.updated,
            "sources": [source.to_json() for source in self.sources],
        }


@dataclass(frozen=True)
class HistoricalChunkRecordResult:
    created: int
    skipped: int
    chunks: list[HistoricalChunkRecord]

    def to_json(self) -> dict[str, object]:
        return {
            "created": self.created,
            "skipped": self.skipped,
            "chunks": [chunk.to_json() for chunk in self.chunks],
        }


@dataclass(frozen=True)
class HistoricalSourceRevokeResult:
    source: HistoricalSourceRecord | None
    sources_revoked: int
    chunks_revoked: int

    def to_json(self) -> dict[str, object]:
        return {
            "source": self.source.to_json() if self.source is not None else None,
            "sources_revoked": self.sources_revoked,
            "chunks_revoked": self.chunks_revoked,
        }


@dataclass(frozen=True)
class HistoricalImportRunRecord:
    historical_import_run_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    run_kind: str
    idempotency_key: str
    status: str
    checkpoint: dict[str, Any]
    stats: dict[str, Any]
    started_at: datetime
    completed_at: datetime | None
    updated_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> HistoricalImportRunRecord:
        return cls(
            historical_import_run_id=row["historical_import_run_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            run_kind=row["run_kind"],
            idempotency_key=row["idempotency_key"],
            status=row["status"],
            checkpoint=_json_dict(_row_get(row, "checkpoint")),
            stats=_json_dict(_row_get(row, "stats")),
            started_at=row["started_at"],
            completed_at=_row_get(row, "completed_at"),
            updated_at=row["updated_at"],
        )

    def to_json(self) -> dict[str, object]:
        return {
            "historical_import_run_id": str(self.historical_import_run_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "run_kind": self.run_kind,
            "idempotency_key": self.idempotency_key,
            "status": self.status,
            "checkpoint": self.checkpoint,
            "stats": self.stats,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "updated_at": self.updated_at.isoformat(),
        }


class HistoricalImportStore(Protocol):
    async def upsert_sources(
        self,
        *,
        workspace_key: str,
        sources: list[HistoricalSourceInput],
    ) -> HistoricalSourceUpsertResult: ...

    async def list_sources(
        self,
        *,
        workspace_key: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[HistoricalSourceRecord]: ...

    async def record_chunks(
        self,
        *,
        workspace_key: str,
        chunks: list[HistoricalChunkInput],
    ) -> HistoricalChunkRecordResult: ...

    async def revoke_source(
        self,
        *,
        workspace_key: str,
        historical_import_source_id: UUID,
    ) -> HistoricalSourceRevokeResult: ...

    async def record_import_run(
        self,
        *,
        workspace_key: str,
        run_kind: str,
        idempotency_key: str,
        status: str,
        checkpoint: dict[str, Any] | None = None,
        stats: dict[str, Any] | None = None,
    ) -> HistoricalImportRunRecord: ...


class NullHistoricalImportStore:
    async def upsert_sources(
        self,
        *,
        workspace_key: str,
        sources: list[HistoricalSourceInput],
    ) -> HistoricalSourceUpsertResult:
        return HistoricalSourceUpsertResult(created=0, updated=0, sources=[])

    async def list_sources(
        self,
        *,
        workspace_key: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[HistoricalSourceRecord]:
        return []

    async def record_chunks(
        self,
        *,
        workspace_key: str,
        chunks: list[HistoricalChunkInput],
    ) -> HistoricalChunkRecordResult:
        return HistoricalChunkRecordResult(created=0, skipped=len(chunks), chunks=[])

    async def revoke_source(
        self,
        *,
        workspace_key: str,
        historical_import_source_id: UUID,
    ) -> HistoricalSourceRevokeResult:
        return HistoricalSourceRevokeResult(source=None, sources_revoked=0, chunks_revoked=0)

    async def record_import_run(
        self,
        *,
        workspace_key: str,
        run_kind: str,
        idempotency_key: str,
        status: str,
        checkpoint: dict[str, Any] | None = None,
        stats: dict[str, Any] | None = None,
    ) -> HistoricalImportRunRecord:
        now = datetime.now()
        return HistoricalImportRunRecord(
            historical_import_run_id=UUID("00000000-0000-0000-0000-000000000000"),
            workspace_id=None,
            workspace_key=workspace_key,
            run_kind=run_kind,
            idempotency_key=idempotency_key,
            status=status,
            checkpoint=checkpoint or {},
            stats=stats or {},
            started_at=now,
            completed_at=now if status in {"completed", "failed", "cancelled"} else None,
            updated_at=now,
        )


class AsyncpgHistoricalImportStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def upsert_sources(
        self,
        *,
        workspace_key: str,
        sources: list[HistoricalSourceInput],
    ) -> HistoricalSourceUpsertResult:
        if not sources:
            return HistoricalSourceUpsertResult(created=0, updated=0, sources=[])
        for source in sources:
            _validate_source_input(source)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            workspace_id = await ensure_workspace(conn, workspace_key)
            records: list[HistoricalSourceRecord] = []
            created = 0
            updated = 0
            for source in sources:
                row = await conn.fetchrow(
                    """
                    INSERT INTO autoskill.historical_import_sources (
                      historical_import_source_id,
                      workspace_id,
                      source_kind,
                      source_key,
                      fingerprint,
                      parser_version,
                      redaction_policy_version,
                      trust_level,
                      taint,
                      metadata,
                      status,
                      imported_at
                    )
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10::jsonb,$11,
                      CASE WHEN $11 = 'imported' THEN now() ELSE NULL END)
                    ON CONFLICT (workspace_id, source_kind, source_key, fingerprint)
                    DO UPDATE SET
                      parser_version = EXCLUDED.parser_version,
                      redaction_policy_version = EXCLUDED.redaction_policy_version,
                      trust_level = EXCLUDED.trust_level,
                      taint = EXCLUDED.taint,
                      metadata = EXCLUDED.metadata,
                      status = EXCLUDED.status,
                      last_seen_at = now(),
                      imported_at = CASE
                        WHEN EXCLUDED.status = 'imported' THEN now()
                        ELSE autoskill.historical_import_sources.imported_at
                      END,
                      updated_at = now()
                    RETURNING
                      historical_import_source_id,
                      workspace_id,
                      $12::text AS workspace_key,
                      source_kind,
                      source_key,
                      fingerprint,
                      parser_version,
                      redaction_policy_version,
                      trust_level,
                      taint,
                      metadata,
                      status,
                      last_seen_at,
                      imported_at,
                      created_at,
                      updated_at,
                      (xmax = 0) AS inserted
                    """,
                    uuid4(),
                    workspace_id,
                    source.source_kind,
                    source.source_key,
                    source.fingerprint,
                    source.parser_version,
                    source.redaction_policy_version,
                    source.trust_level,
                    json.dumps(source.taint or {}),
                    json.dumps(source.metadata or {}),
                    source.status,
                    workspace_key,
                )
                if bool(row["inserted"]):
                    created += 1
                else:
                    updated += 1
                records.append(HistoricalSourceRecord.from_row(row))
            return HistoricalSourceUpsertResult(
                created=created,
                updated=updated,
                sources=records,
            )

    async def list_sources(
        self,
        *,
        workspace_key: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[HistoricalSourceRecord]:
        if status is not None and status not in HISTORICAL_SOURCE_STATUSES:
            raise ValueError("status must be a historical source status")
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                  s.historical_import_source_id,
                  s.workspace_id,
                  w.external_key AS workspace_key,
                  s.source_kind,
                  s.source_key,
                  s.fingerprint,
                  s.parser_version,
                  s.redaction_policy_version,
                  s.trust_level,
                  s.taint,
                  s.metadata,
                  s.status,
                  s.last_seen_at,
                  s.imported_at,
                  s.created_at,
                  s.updated_at
                FROM autoskill.historical_import_sources s
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE ($1::text IS NULL OR w.external_key = $1)
                  AND ($2::text IS NULL OR s.status = $2)
                ORDER BY s.updated_at DESC, s.historical_import_source_id DESC
                LIMIT $3
                """,
                workspace_key,
                status,
                max(1, min(limit, 1000)),
            )
        return [HistoricalSourceRecord.from_row(row) for row in rows]

    async def record_chunks(
        self,
        *,
        workspace_key: str,
        chunks: list[HistoricalChunkInput],
    ) -> HistoricalChunkRecordResult:
        if not chunks:
            return HistoricalChunkRecordResult(created=0, skipped=0, chunks=[])
        chunks = [chunk.storage_redacted() for chunk in chunks]
        for chunk in chunks:
            _validate_chunk_input(chunk)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            workspace_id = await ensure_workspace(conn, workspace_key)
            records: list[HistoricalChunkRecord] = []
            created = 0
            skipped = 0
            for chunk in chunks:
                source = await conn.fetchrow(
                    """
                    SELECT historical_import_source_id
                    FROM autoskill.historical_import_sources
                    WHERE workspace_id = $1
                      AND source_kind = $2
                      AND source_key = $3
                      AND fingerprint = $4
                      AND status <> 'revoked'
                    """,
                    workspace_id,
                    chunk.source_kind,
                    chunk.source_key,
                    chunk.fingerprint,
                )
                if source is None:
                    raise ValueError("historical import chunk source is not registered")
                redacted_text = redact_text(chunk.redacted_text)
                content_hash = sha256_text(redacted_text)
                source_item_columns = _chunk_source_item_columns(chunk)
                row = await conn.fetchrow(
                    """
                    INSERT INTO autoskill.historical_import_chunks (
                      historical_import_chunk_id,
                      workspace_id,
                      historical_import_source_id,
                      item_key,
                      chunk_index,
                      source_item_locator_hash,
                      source_item_kind,
                      item_key_hash,
                      line_range_hash,
                      record_index,
                      chunk_kind,
                      content_hash,
                      redacted_text,
                      token_estimate,
                      parser_version,
                      redaction_policy_version,
                      trust_level,
                      taint,
                      metadata
                    )
                    VALUES (
                      $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                      $11,$12,$13,$14,$15,$16,$17,$18::jsonb,$19::jsonb
                    )
                    ON CONFLICT (
                      workspace_id,
                      historical_import_source_id,
                      item_key,
                      chunk_index,
                      content_hash
                    )
                    DO NOTHING
                    RETURNING
                      historical_import_chunk_id,
                      workspace_id,
                      $20::text AS workspace_key,
                      historical_import_source_id,
                      item_key,
                      chunk_index,
                      source_item_locator_hash,
                      source_item_kind,
                      item_key_hash,
                      line_range_hash,
                      record_index,
                      chunk_kind,
                      content_hash,
                      redacted_text,
                      token_estimate,
                      parser_version,
                      redaction_policy_version,
                      trust_level,
                      taint,
                      metadata,
                      status,
                      created_at
                    """,
                    uuid4(),
                    workspace_id,
                    source["historical_import_source_id"],
                    chunk.item_key,
                    chunk.chunk_index,
                    source_item_columns["source_item_locator_hash"],
                    source_item_columns["source_item_kind"],
                    source_item_columns["item_key_hash"],
                    source_item_columns["line_range_hash"],
                    source_item_columns["record_index"],
                    chunk.chunk_kind,
                    content_hash,
                    redacted_text,
                    chunk.token_estimate,
                    chunk.parser_version,
                    chunk.redaction_policy_version,
                    chunk.trust_level,
                    json.dumps(chunk.taint or {}),
                    json.dumps(chunk.metadata or {}),
                    workspace_key,
                )
                if row is None:
                    skipped += 1
                    continue
                await conn.execute(
                    """
                    INSERT INTO autoskill.provenance_edges (
                      provenance_edge_id,
                      workspace_id,
                      source_kind,
                      source_id,
                      derived_kind,
                      derived_id,
                      relation
                    )
                    VALUES (
                      gen_random_uuid(),
                      $1,
                      'historical_import_source',
                      $2,
                      'historical_import_chunk',
                      $3,
                      'historical_source_contains_chunk'
                    )
                    ON CONFLICT (
                      workspace_id,
                      source_kind,
                      source_id,
                      derived_kind,
                      derived_id,
                      relation
                    ) DO NOTHING
                    """,
                    workspace_id,
                    source["historical_import_source_id"],
                    row["historical_import_chunk_id"],
                )
                created += 1
                records.append(HistoricalChunkRecord.from_row(row))
            return HistoricalChunkRecordResult(
                created=created,
                skipped=skipped,
                chunks=records,
            )

    async def revoke_source(
        self,
        *,
        workspace_key: str,
        historical_import_source_id: UUID,
    ) -> HistoricalSourceRevokeResult:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            source = await conn.fetchrow(
                """
                UPDATE autoskill.historical_import_sources s
                SET status = 'revoked',
                    updated_at = now()
                FROM autoskill.workspaces w
                WHERE s.workspace_id = w.workspace_id
                  AND w.external_key = $1
                  AND s.historical_import_source_id = $2
                RETURNING
                  s.historical_import_source_id,
                  s.workspace_id,
                  w.external_key AS workspace_key,
                  s.source_kind,
                  s.source_key,
                  s.fingerprint,
                  s.parser_version,
                  s.redaction_policy_version,
                  s.trust_level,
                  s.taint,
                  s.metadata,
                  s.status,
                  s.last_seen_at,
                  s.imported_at,
                  s.created_at,
                  s.updated_at
                """,
                workspace_key,
                historical_import_source_id,
            )
            if source is None:
                return HistoricalSourceRevokeResult(
                    source=None,
                    sources_revoked=0,
                    chunks_revoked=0,
                )
            chunks_result = await conn.execute(
                """
                UPDATE autoskill.historical_import_chunks
                SET status = 'revoked'
                WHERE workspace_id = $1
                  AND historical_import_source_id = $2
                  AND status <> 'revoked'
                """,
                source["workspace_id"],
                historical_import_source_id,
            )
            return HistoricalSourceRevokeResult(
                source=HistoricalSourceRecord.from_row(source),
                sources_revoked=1,
                chunks_revoked=_execute_count(chunks_result),
            )

    async def record_import_run(
        self,
        *,
        workspace_key: str,
        run_kind: str,
        idempotency_key: str,
        status: str,
        checkpoint: dict[str, Any] | None = None,
        stats: dict[str, Any] | None = None,
    ) -> HistoricalImportRunRecord:
        if status not in {"running", "completed", "failed", "cancelled"}:
            raise ValueError("status must be a historical import run status")
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.historical_import_runs (
                  historical_import_run_id,
                  workspace_id,
                  run_kind,
                  idempotency_key,
                  status,
                  checkpoint,
                  stats,
                  completed_at
                )
                VALUES (
                  $1, $2, $3, $4, $5, $6::jsonb, $7::jsonb,
                  CASE WHEN $5 IN ('completed','failed','cancelled') THEN now() ELSE NULL END
                )
                ON CONFLICT (workspace_id, idempotency_key)
                DO UPDATE SET
                  run_kind = EXCLUDED.run_kind,
                  status = EXCLUDED.status,
                  checkpoint = EXCLUDED.checkpoint,
                  stats = EXCLUDED.stats,
                  completed_at = CASE
                    WHEN EXCLUDED.status IN ('completed','failed','cancelled') THEN now()
                    ELSE autoskill.historical_import_runs.completed_at
                  END,
                  updated_at = now()
                RETURNING
                  historical_import_run_id,
                  workspace_id,
                  $8::text AS workspace_key,
                  run_kind,
                  idempotency_key,
                  status,
                  checkpoint,
                  stats,
                  started_at,
                  completed_at,
                  updated_at
                """,
                uuid4(),
                workspace_id,
                run_kind,
                idempotency_key,
                status,
                json.dumps(checkpoint or {}),
                json.dumps(stats or {}),
                workspace_key,
            )
            return HistoricalImportRunRecord.from_row(row)


def _validate_source_input(source: HistoricalSourceInput) -> None:
    if source.source_kind not in HISTORICAL_SOURCE_KINDS:
        raise ValueError("source_kind must be a supported historical source kind")
    if source.status not in HISTORICAL_SOURCE_STATUSES:
        raise ValueError("status must be a historical source status")
    if source.trust_level not in HISTORICAL_TRUST_LEVELS:
        raise ValueError("trust_level must be trusted, tainted, or untrusted")
    if not source.source_key.strip():
        raise ValueError("source_key is required")
    if not source.fingerprint.strip():
        raise ValueError("fingerprint is required")


def _validate_chunk_input(chunk: HistoricalChunkInput) -> None:
    if chunk.source_kind not in HISTORICAL_SOURCE_KINDS:
        raise ValueError("source_kind must be a supported historical source kind")
    if chunk.trust_level not in HISTORICAL_TRUST_LEVELS:
        raise ValueError("trust_level must be trusted, tainted, or untrusted")
    if chunk.chunk_index < 0:
        raise ValueError("chunk_index must be non-negative")
    if chunk.token_estimate < 0:
        raise ValueError("token_estimate must be non-negative")
    if not chunk.redacted_text.strip():
        raise ValueError("redacted_text is required")


def _chunk_source_item_columns(chunk: HistoricalChunkInput) -> dict[str, Any]:
    metadata = _json_dict(chunk.metadata)
    source_item = _json_dict(metadata.get("source_item"))
    lineage = _json_dict(metadata.get("lineage"))
    record_index = source_item.get("record_index")
    return {
        "source_item_locator_hash": (
            source_item.get("locator_hash") or lineage.get("source_item_locator_hash")
        ),
        "source_item_kind": source_item.get("item_kind"),
        "item_key_hash": source_item.get("item_key_hash") or lineage.get("item_key_hash"),
        "line_range_hash": source_item.get("line_range_hash"),
        "record_index": record_index if isinstance(record_index, int) else None,
    }


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def _json_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    return dict(value)


def _execute_count(status: str) -> int:
    try:
        return int(status.rsplit(" ", 1)[-1])
    except (ValueError, IndexError):
        return 0
