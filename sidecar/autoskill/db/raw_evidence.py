from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace

RAW_EVIDENCE_KINDS = {
    "user_prompt",
    "agent_message",
    "system_prompt",
    "model_input",
    "model_output",
    "tool_params",
    "tool_result",
    "transcript_window",
    "trajectory_window",
    "memory_file",
    "context_file",
    "diagnostic_raw_stream",
    "other",
}
SENSITIVITY_LEVELS = {
    "public",
    "internal",
    "private",
    "secret_candidate",
    "credential_candidate",
    "unknown",
}
RAW_ACCESSOR_KINDS = {
    "core_job",
    "llm_profile",
    "operator_ui",
    "retention_job",
    "scanner",
    "evaluator",
}
RAW_EXPOSURE_LEVELS = {
    "metadata",
    "redacted",
    "secret_masked_raw",
    "raw_local_only",
    "raw_allowed_hosted",
}
RAW_ACCESS_DECISIONS = {
    "allowed",
    "denied",
    "masked",
    "expired",
    "revoked",
}


@dataclass(frozen=True)
class RawEvidenceInput:
    workspace_key: str
    source_event_hash: str
    source_kind: str
    source_id: str | None
    session_id: str | None
    turn_id: str | None
    raw_kind: str
    content_hash: str
    sensitivity_level: str
    taint: list[str]
    retention_until: datetime
    encryption_key_id: str
    ciphertext: bytes | None
    external_ciphertext_ref: str | None
    compression: str
    capture_policy_id: str
    redaction_policy_id: str
    access_policy: dict[str, Any]


@dataclass(frozen=True)
class RawEvidenceRecord:
    raw_evidence_record_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    source_event_hash: str
    source_kind: str
    source_id: str | None
    session_id: str | None
    turn_id: str | None
    raw_kind: str
    content_hash: str
    sensitivity_level: str
    taint: list[str]
    retention_until: datetime
    encryption_key_id: str
    external_ciphertext_ref: str | None
    compression: str
    capture_policy_id: str
    redaction_policy_id: str
    access_policy: dict[str, Any]
    created_at: datetime
    revoked_at: datetime | None = None

    @classmethod
    def from_row(cls, row: asyncpg.Record | Mapping[str, Any]) -> RawEvidenceRecord:
        return cls(
            raw_evidence_record_id=row["raw_evidence_record_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            source_event_hash=row["source_event_hash"],
            source_kind=row["source_kind"],
            source_id=_row_get(row, "source_id"),
            session_id=_row_get(row, "session_id"),
            turn_id=_row_get(row, "turn_id"),
            raw_kind=row["raw_kind"],
            content_hash=row["content_hash"],
            sensitivity_level=row["sensitivity_level"],
            taint=list(row["taint"]),
            retention_until=row["retention_until"],
            encryption_key_id=row["encryption_key_id"],
            external_ciphertext_ref=_row_get(row, "external_ciphertext_ref"),
            compression=row["compression"],
            capture_policy_id=row["capture_policy_id"],
            redaction_policy_id=row["redaction_policy_id"],
            access_policy=_json_dict(row["access_policy"]),
            created_at=row["created_at"],
            revoked_at=_row_get(row, "revoked_at"),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "object_type": "raw_vault_record",
            "object_id": str(self.raw_evidence_record_id),
            "raw_evidence_record_id": str(self.raw_evidence_record_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "source_event_hash": self.source_event_hash,
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "raw_kind": self.raw_kind,
            "content_hash": self.content_hash,
            "sensitivity_level": self.sensitivity_level,
            "taint": self.taint,
            "retention_until": self.retention_until.isoformat(),
            "encryption_key_id": self.encryption_key_id,
            "external_ciphertext_ref": self.external_ciphertext_ref,
            "compression": self.compression,
            "capture_policy_id": self.capture_policy_id,
            "redaction_policy_id": self.redaction_policy_id,
            "access_policy": self.access_policy,
            "created_at": self.created_at.isoformat(),
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "content_policy": {
                "raw_evidence_returned": False,
                "browser_exposure": "forbidden",
                "guarded_reveal_required": True,
            },
        }


@dataclass(frozen=True)
class RawEvidenceAccessLogRecord:
    raw_access_id: UUID
    raw_evidence_record_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    job_id: UUID | None
    purpose: str
    accessor_kind: str
    model_profile_id: UUID | None
    exposure_level: str
    decision: str
    reason_code: str
    created_at: datetime


class RawEvidenceStore(Protocol):
    async def create_record(self, record: RawEvidenceInput) -> RawEvidenceRecord:
        """Persist an encrypted raw-evidence vault record idempotently."""

    async def record_access(
        self,
        *,
        raw_evidence_record_id: UUID,
        workspace_key: str,
        purpose: str,
        accessor_kind: str,
        exposure_level: str,
        decision: str,
        reason_code: str,
        job_id: UUID | None = None,
        model_profile_id: UUID | None = None,
    ) -> RawEvidenceAccessLogRecord:
        """Append a raw-vault access/audit decision without exposing raw bytes."""


class NullRawEvidenceStore:
    def __init__(self) -> None:
        self.records: list[RawEvidenceRecord] = []
        self.access_log: list[RawEvidenceAccessLogRecord] = []

    async def create_record(self, record: RawEvidenceInput) -> RawEvidenceRecord:
        for existing in self.records:
            if (
                existing.workspace_key == record.workspace_key
                and existing.source_event_hash == record.source_event_hash
                and existing.raw_kind == record.raw_kind
                and existing.content_hash == record.content_hash
            ):
                return existing
        created = RawEvidenceRecord(
            raw_evidence_record_id=uuid4(),
            workspace_id=None,
            workspace_key=record.workspace_key,
            source_event_hash=record.source_event_hash,
            source_kind=record.source_kind,
            source_id=record.source_id,
            session_id=record.session_id,
            turn_id=record.turn_id,
            raw_kind=record.raw_kind,
            content_hash=record.content_hash,
            sensitivity_level=record.sensitivity_level,
            taint=list(record.taint),
            retention_until=record.retention_until,
            encryption_key_id=record.encryption_key_id,
            external_ciphertext_ref=record.external_ciphertext_ref,
            compression=record.compression,
            capture_policy_id=record.capture_policy_id,
            redaction_policy_id=record.redaction_policy_id,
            access_policy=dict(record.access_policy),
            created_at=datetime.now(UTC),
        )
        self.records.append(created)
        return created

    async def record_access(
        self,
        *,
        raw_evidence_record_id: UUID,
        workspace_key: str,
        purpose: str,
        accessor_kind: str,
        exposure_level: str,
        decision: str,
        reason_code: str,
        job_id: UUID | None = None,
        model_profile_id: UUID | None = None,
    ) -> RawEvidenceAccessLogRecord:
        record = RawEvidenceAccessLogRecord(
            raw_access_id=uuid4(),
            raw_evidence_record_id=raw_evidence_record_id,
            workspace_id=None,
            workspace_key=workspace_key,
            job_id=job_id,
            purpose=purpose,
            accessor_kind=accessor_kind,
            model_profile_id=model_profile_id,
            exposure_level=exposure_level,
            decision=decision,
            reason_code=reason_code,
            created_at=datetime.now(UTC),
        )
        self.access_log.append(record)
        return record


class AsyncpgRawEvidenceStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def create_record(self, record: RawEvidenceInput) -> RawEvidenceRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, record.workspace_key)
            row = await _insert_raw_evidence_record(conn, workspace_id, record)
        return RawEvidenceRecord.from_row({**dict(row), "workspace_key": record.workspace_key})

    async def record_access(
        self,
        *,
        raw_evidence_record_id: UUID,
        workspace_key: str,
        purpose: str,
        accessor_kind: str,
        exposure_level: str,
        decision: str,
        reason_code: str,
        job_id: UUID | None = None,
        model_profile_id: UUID | None = None,
    ) -> RawEvidenceAccessLogRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.raw_evidence_access_log (
                  raw_access_id,
                  raw_evidence_record_id,
                  workspace_id,
                  job_id,
                  purpose,
                  accessor_kind,
                  model_profile_id,
                  exposure_level,
                  decision,
                  reason_code
                )
                VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING *
                """,
                raw_evidence_record_id,
                workspace_id,
                job_id,
                purpose,
                accessor_kind,
                model_profile_id,
                exposure_level,
                decision,
                reason_code,
            )
        return RawEvidenceAccessLogRecord(
            raw_access_id=row["raw_access_id"],
            raw_evidence_record_id=row["raw_evidence_record_id"],
            workspace_id=row["workspace_id"],
            workspace_key=workspace_key,
            job_id=row["job_id"],
            purpose=row["purpose"],
            accessor_kind=row["accessor_kind"],
            model_profile_id=row["model_profile_id"],
            exposure_level=row["exposure_level"],
            decision=row["decision"],
            reason_code=row["reason_code"],
            created_at=row["created_at"],
        )


async def _insert_raw_evidence_record(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    record: RawEvidenceInput,
) -> asyncpg.Record:
    _validate_raw_evidence_input(record)
    return await conn.fetchrow(
        """
        INSERT INTO autoskill.raw_evidence_records (
          raw_evidence_record_id,
          workspace_id,
          source_event_hash,
          source_kind,
          source_id,
          session_id,
          turn_id,
          raw_kind,
          content_hash,
          sensitivity_level,
          taint,
          retention_until,
          encryption_key_id,
          ciphertext,
          external_ciphertext_ref,
          compression,
          capture_policy_id,
          redaction_policy_id,
          access_policy
        )
        VALUES (
          gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9,
          $10, $11, $12, $13, $14, $15, $16, $17, $18::jsonb
        )
        ON CONFLICT (workspace_id, source_event_hash, raw_kind, content_hash)
        DO UPDATE SET source_event_hash = EXCLUDED.source_event_hash
        RETURNING *
        """,
        workspace_id,
        record.source_event_hash,
        record.source_kind,
        record.source_id,
        record.session_id,
        record.turn_id,
        record.raw_kind,
        record.content_hash,
        record.sensitivity_level,
        record.taint,
        record.retention_until,
        record.encryption_key_id,
        record.ciphertext,
        record.external_ciphertext_ref,
        record.compression,
        record.capture_policy_id,
        record.redaction_policy_id,
        json.dumps(record.access_policy, sort_keys=True, separators=(",", ":")),
    )


def _validate_raw_evidence_input(record: RawEvidenceInput) -> None:
    if record.raw_kind not in RAW_EVIDENCE_KINDS:
        raise ValueError(f"raw_kind must be one of: {', '.join(sorted(RAW_EVIDENCE_KINDS))}")
    if record.sensitivity_level not in SENSITIVITY_LEVELS:
        raise ValueError(
            f"sensitivity_level must be one of: {', '.join(sorted(SENSITIVITY_LEVELS))}"
        )
    if record.ciphertext is None and record.external_ciphertext_ref is None:
        raise ValueError("raw evidence requires ciphertext or external_ciphertext_ref")


def _row_get(row: asyncpg.Record | Mapping[str, Any], key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}
