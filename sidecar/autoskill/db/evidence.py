from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.core.enums import EvidenceMaturity
from autoskill.core.hashing import sha256_json
from autoskill.db.pool import AsyncpgPoolOwner

RECURRING_EVIDENCE_MIN_SUPPORT = 3


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    source_event_id: UUID | None
    evidence_hash: str
    kind: str
    maturity: str
    trust: str
    taint: list[str]
    summary: str
    payload: dict[str, Any]
    created_at: datetime
    revoked_at: datetime | None = None

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> EvidenceRecord:
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return cls(
            evidence_id=row["evidence_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            source_event_id=_row_get(row, "source_event_id"),
            evidence_hash=row["evidence_hash"],
            kind=row["kind"],
            maturity=row["maturity"],
            trust=row["trust"],
            taint=list(row["taint"]),
            summary=row["summary"],
            payload=payload,
            created_at=row["created_at"],
            revoked_at=_row_get(row, "revoked_at"),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "evidence_id": str(self.evidence_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "source_event_id": str(self.source_event_id) if self.source_event_id else None,
            "evidence_hash": self.evidence_hash,
            "kind": self.kind,
            "maturity": self.maturity,
            "trust": self.trust,
            "taint": self.taint,
            "summary": self.summary,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
        }


@dataclass(frozen=True)
class EvidenceDeriveResult:
    scanned: int
    created: int
    duplicate: int
    evidence: list[EvidenceRecord]


class EvidenceStore(Protocol):
    async def derive_from_raw_events(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> EvidenceDeriveResult:
        """Create observed evidence items from already-redacted raw events."""

    async def list_evidence(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[EvidenceRecord]:
        """List recent non-revoked evidence."""


class NullEvidenceStore:
    async def derive_from_raw_events(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> EvidenceDeriveResult:
        return EvidenceDeriveResult(scanned=0, created=0, duplicate=0, evidence=[])

    async def list_evidence(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[EvidenceRecord]:
        return []


class AsyncpgEvidenceStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def derive_from_raw_events(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> EvidenceDeriveResult:
        pool = await self._get_pool()
        evidence: list[EvidenceRecord] = []
        duplicate = 0
        async with pool.acquire() as conn, conn.transaction():
            events = await conn.fetch(
                """
                SELECT e.*, w.external_key AS workspace_key
                FROM autoskill.raw_events e
                JOIN autoskill.workspaces w USING (workspace_id)
                LEFT JOIN autoskill.evidence_items i
                  ON i.source_event_id = e.event_id
                 AND i.kind = 'event_observation'
                WHERE i.evidence_id IS NULL
                  AND ($1::text IS NULL OR w.external_key = $1)
                ORDER BY e.occurred_at ASC
                LIMIT $2
                FOR UPDATE OF e SKIP LOCKED
                """,
                workspace_key,
                limit,
            )
            for event in events:
                inserted = await _insert_event_evidence(conn, event)
                if inserted is None:
                    duplicate += 1
                    continue
                evidence.append(inserted)
            chunks = await conn.fetch(
                """
                SELECT
                  c.*,
                  s.source_kind,
                  s.source_key,
                  s.fingerprint,
                  w.external_key AS workspace_key
                FROM autoskill.historical_import_chunks c
                JOIN autoskill.historical_import_sources s
                  USING (historical_import_source_id)
                JOIN autoskill.workspaces w ON w.workspace_id = c.workspace_id
                LEFT JOIN autoskill.provenance_edges p
                  ON p.workspace_id = c.workspace_id
                 AND p.source_kind = 'historical_import_chunk'
                 AND p.source_id = c.historical_import_chunk_id
                 AND p.derived_kind = 'evidence_item'
                 AND p.relation = 'derived_from'
                WHERE c.status = 'observed'
                  AND p.provenance_edge_id IS NULL
                  AND ($1::text IS NULL OR w.external_key = $1)
                ORDER BY c.created_at ASC
                LIMIT $2
                FOR UPDATE OF c SKIP LOCKED
                """,
                workspace_key,
                limit,
            )
            for chunk in chunks:
                inserted = await _insert_historical_chunk_evidence(conn, chunk)
                if inserted is None:
                    duplicate += 1
                    continue
                evidence.append(inserted)
            recurring = await _insert_recurring_evidence_clusters(
                conn,
                workspace_key=workspace_key,
            )
            evidence.extend(recurring)

        return EvidenceDeriveResult(
            scanned=len(events) + len(chunks),
            created=len(evidence),
            duplicate=duplicate,
            evidence=evidence,
        )

    async def list_evidence(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[EvidenceRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT i.*, w.external_key AS workspace_key
                FROM autoskill.evidence_items i
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE i.revoked_at IS NULL
                  AND ($1::text IS NULL OR w.external_key = $1)
                ORDER BY i.created_at DESC
                LIMIT $2
                """,
                workspace_key,
                limit,
            )
            return [EvidenceRecord.from_row(row) for row in rows]


async def _insert_event_evidence(
    conn: asyncpg.Connection,
    event: asyncpg.Record,
) -> EvidenceRecord | None:
    payload = _evidence_payload(event)
    evidence_hash = sha256_json(
        {
            "kind": "event_observation",
            "workspace_id": str(event["workspace_id"]),
            "source_event_id": str(event["event_id"]),
            "payload_hash": event["payload_hash"],
        }
    )
    row = await conn.fetchrow(
        """
        INSERT INTO autoskill.evidence_items (
          evidence_id,
          workspace_id,
          source_event_id,
          evidence_hash,
          kind,
          maturity,
          trust,
          taint,
          summary,
          payload
        )
        VALUES (
          gen_random_uuid(), $1, $2, $3, 'event_observation', $4, $5, $6, $7, $8::jsonb
        )
        ON CONFLICT (workspace_id, evidence_hash) DO NOTHING
        RETURNING *
        """,
        event["workspace_id"],
        event["event_id"],
        evidence_hash,
        str(EvidenceMaturity.OBSERVED),
        event["trust"],
        event["taint"],
        _summary(event),
        _json(payload),
    )
    if row is None:
        return None

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
        VALUES (gen_random_uuid(), $1, 'raw_event', $2, 'evidence_item', $3, 'derived_from')
        ON CONFLICT DO NOTHING
        """,
        event["workspace_id"],
        event["event_id"],
        row["evidence_id"],
    )
    return EvidenceRecord.from_row({**dict(row), "workspace_key": event["workspace_key"]})


async def _insert_historical_chunk_evidence(
    conn: asyncpg.Connection,
    chunk: asyncpg.Record,
) -> EvidenceRecord | None:
    payload = _historical_chunk_payload(chunk)
    evidence_hash = sha256_json(
        {
            "kind": "historical_chunk_observation",
            "workspace_id": str(chunk["workspace_id"]),
            "historical_import_chunk_id": str(chunk["historical_import_chunk_id"]),
            "content_hash": chunk["content_hash"],
        }
    )
    taint = _historical_chunk_taint(chunk)
    row = await conn.fetchrow(
        """
        INSERT INTO autoskill.evidence_items (
          evidence_id,
          workspace_id,
          evidence_hash,
          kind,
          maturity,
          trust,
          taint,
          summary,
          payload
        )
        VALUES (
          gen_random_uuid(),
          $1,
          $2,
          'historical_chunk_observation',
          $3,
          $4,
          $5,
          $6,
          $7::jsonb
        )
        ON CONFLICT (workspace_id, evidence_hash) DO NOTHING
        RETURNING *
        """,
        chunk["workspace_id"],
        evidence_hash,
        str(EvidenceMaturity.OBSERVED),
        chunk["trust_level"],
        taint,
        _historical_chunk_summary(chunk),
        _json(payload),
    )
    if row is None:
        return None

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
          'historical_import_chunk',
          $2,
          'evidence_item',
          $3,
          'derived_from'
        )
        ON CONFLICT DO NOTHING
        """,
        chunk["workspace_id"],
        chunk["historical_import_chunk_id"],
        row["evidence_id"],
    )
    return EvidenceRecord.from_row({**dict(row), "workspace_key": chunk["workspace_key"]})


async def _insert_recurring_evidence_clusters(
    conn: asyncpg.Connection,
    *,
    workspace_key: str | None,
) -> list[EvidenceRecord]:
    rows = await conn.fetch(
        """
        SELECT i.*, w.external_key AS workspace_key
        FROM autoskill.evidence_items i
        JOIN autoskill.workspaces w USING (workspace_id)
        WHERE i.revoked_at IS NULL
          AND i.kind IN ('event_observation', 'historical_chunk_observation')
          AND i.maturity = 'observed'
          AND ($1::text IS NULL OR w.external_key = $1)
        ORDER BY i.created_at ASC
        LIMIT 2000
        """,
        workspace_key,
    )
    grouped: dict[str, list[EvidenceRecord]] = defaultdict(list)
    for row in rows:
        record = EvidenceRecord.from_row(row)
        grouped[_recurring_signature(record)].append(record)

    clusters: list[EvidenceRecord] = []
    for signature, records in sorted(grouped.items()):
        if len(records) < RECURRING_EVIDENCE_MIN_SUPPORT:
            continue
        inserted = await _insert_recurring_evidence_cluster(conn, signature, records)
        if inserted is not None:
            clusters.append(inserted)
    return clusters


async def _insert_recurring_evidence_cluster(
    conn: asyncpg.Connection,
    signature: str,
    records: list[EvidenceRecord],
) -> EvidenceRecord | None:
    first = records[0]
    workspace_id = first.workspace_id
    if workspace_id is None:
        return None
    evidence_hash = sha256_json(
        {
            "kind": "recurring_evidence_cluster",
            "workspace_id": str(workspace_id),
            "signature": signature,
            "min_support": RECURRING_EVIDENCE_MIN_SUPPORT,
        }
    )
    payload = _recurring_payload(signature, records)
    row = await conn.fetchrow(
        """
        INSERT INTO autoskill.evidence_items (
          evidence_id,
          workspace_id,
          evidence_hash,
          kind,
          maturity,
          trust,
          taint,
          summary,
          payload
        )
        VALUES (
          gen_random_uuid(),
          $1,
          $2,
          'recurring_evidence_cluster',
          $3,
          $4,
          $5,
          $6,
          $7::jsonb
        )
        ON CONFLICT (workspace_id, evidence_hash) DO NOTHING
        RETURNING *
        """,
        workspace_id,
        evidence_hash,
        str(EvidenceMaturity.RECURRING),
        _dominant_trust(records),
        _merged_taint(records),
        _recurring_summary(signature, records),
        _json(payload),
    )
    if row is None:
        return None

    await conn.executemany(
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
        VALUES (gen_random_uuid(), $1, 'evidence_item', $2, 'evidence_item', $3, 'supports_cluster')
        ON CONFLICT DO NOTHING
        """,
        [
            (workspace_id, record.evidence_id, row["evidence_id"])
            for record in records[:50]
        ],
    )
    await conn.execute(
        """
        INSERT INTO autoskill.evidence_maturity (
          evidence_maturity_id, workspace_id, object_type, object_id, maturity, basis
        )
        VALUES (gen_random_uuid(), $1, 'evidence', $2, 'recurring', $3::jsonb)
        ON CONFLICT (workspace_id, object_type, object_id) DO UPDATE
        SET maturity = EXCLUDED.maturity,
            basis = EXCLUDED.basis,
            updated_at = now()
        """,
        workspace_id,
        row["evidence_id"],
        _json(
            {
                "schema": "autoskill.recurring_evidence_maturity.v1",
                "signature": signature,
                "support_count": len(records),
                "support_evidence_ids": [str(record.evidence_id) for record in records[:50]],
            }
        ),
    )
    return EvidenceRecord.from_row({**dict(row), "workspace_key": first.workspace_key})


def _recurring_signature(record: EvidenceRecord) -> str:
    source = record.payload.get("source_event", {})
    event_type = _safe_component(source.get("event_type") or record.kind)
    payload = record.payload.get("redacted_payload", {})
    payload_terms = _payload_terms(payload)
    if payload_terms:
        return ":".join([event_type, *payload_terms[:4]])
    return event_type


def _payload_terms(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    terms: list[str] = []
    for key in ("error", "error_code", "status", "tool", "command", "message", "content"):
        value = payload.get(key)
        if isinstance(value, dict):
            value = value.get("code") or value.get("message") or value.get("type")
        if value is None:
            continue
        terms.extend(_safe_component(part) for part in str(value).split())
    return [term for term in terms if len(term) >= 3]


def _safe_component(value: object) -> str:
    cleaned = "".join(
        ch.lower() if ch.isalnum() else "-"
        for ch in str(value)
    )
    return "-".join(part for part in cleaned.split("-") if part)[:48] or "unknown"


def _recurring_payload(signature: str, records: list[EvidenceRecord]) -> dict[str, Any]:
    first_source = records[0].payload.get("source_event", {})
    return {
        "schema_version": 1,
        "schema": "autoskill.recurring_evidence_cluster.v1",
        "signature": signature,
        "support_count": len(records),
        "min_support": RECURRING_EVIDENCE_MIN_SUPPORT,
        "support_evidence_ids": [str(record.evidence_id) for record in records[:50]],
        "source_event": {
            "event_type": first_source.get("event_type") or records[0].kind,
            "source": first_source.get("source"),
            "first_observed_at": records[0].created_at.isoformat(),
            "last_observed_at": records[-1].created_at.isoformat(),
        },
        "redacted_payload": {
            "content": signature.replace(":", " "),
            "support_count": len(records),
        },
    }


def _recurring_summary(signature: str, records: list[EvidenceRecord]) -> str:
    return (
        f"Recurring redacted evidence cluster {signature!r} observed "
        f"{len(records)} times."
    )


def _dominant_trust(records: list[EvidenceRecord]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        counts[record.trust] += 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _merged_taint(records: list[EvidenceRecord]) -> list[str]:
    taint = {item for record in records for item in record.taint}
    return sorted(taint)


def _summary(event: asyncpg.Record) -> str:
    session = event["session_id"] or "unknown-session"
    turn = event["turn_id"] or "unknown-turn"
    return (
        f"Observed redacted {event['event_type']} event from {event['source']} "
        f"in {session}/{turn}."
    )


def _evidence_payload(event: asyncpg.Record) -> dict[str, Any]:
    event_payload = event["payload"]
    if isinstance(event_payload, str):
        event_payload = json.loads(event_payload)
    return {
        "schema_version": 1,
        "source_event": {
            "event_id": str(event["event_id"]),
            "event_type": event["event_type"],
            "occurred_at": event["occurred_at"].isoformat(),
            "session_id": event["session_id"],
            "turn_id": event["turn_id"],
            "source": event["source"],
            "redaction_state": event["redaction_state"],
            "payload_hash": event["payload_hash"],
            "plugin_version": event["plugin_version"],
            "openclaw_version": event["openclaw_version"],
        },
        "redacted_payload": event_payload,
    }


def _historical_chunk_payload(chunk: asyncpg.Record) -> dict[str, Any]:
    metadata = chunk["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    taint = chunk["taint"]
    if isinstance(taint, str):
        taint = json.loads(taint)
    return {
        "schema_version": 1,
        "source_event": {
            "event_type": "historical_import_chunk",
            "source": "historical_import",
            "historical_import_source_id": str(chunk["historical_import_source_id"]),
            "historical_import_chunk_id": str(chunk["historical_import_chunk_id"]),
            "source_kind": chunk["source_kind"],
            "source_key_hash": sha256_json(
                {
                    "source_kind": chunk["source_kind"],
                    "source_key": chunk["source_key"],
                    "fingerprint": chunk["fingerprint"],
                }
            ),
            "fingerprint": chunk["fingerprint"],
            "item_key_hash": sha256_json(
                {
                    "source_kind": chunk["source_kind"],
                    "source_key": chunk["source_key"],
                    "item_key": chunk["item_key"],
                    "chunk_index": chunk["chunk_index"],
                }
            ),
            "chunk_index": chunk["chunk_index"],
            "chunk_kind": chunk["chunk_kind"],
            "content_hash": chunk["content_hash"],
            "parser_version": chunk["parser_version"],
            "redaction_policy_version": chunk["redaction_policy_version"],
        },
        "redacted_payload": {
            "content": chunk["redacted_text"],
            "token_estimate": chunk["token_estimate"],
            "metadata": metadata,
            "taint": taint,
        },
    }


def _historical_chunk_summary(chunk: asyncpg.Record) -> str:
    return (
        "Observed redacted historical "
        f"{chunk['source_kind']} chunk {chunk['chunk_index']} "
        f"from fingerprint {chunk['fingerprint']}."
    )


def _historical_chunk_taint(chunk: asyncpg.Record) -> list[str]:
    raw = chunk["taint"]
    if isinstance(raw, str):
        raw = json.loads(raw)
    keys = [f"historical:{key}" for key, value in sorted(raw.items()) if value]
    return sorted({"historical", "redacted", *keys})


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None
