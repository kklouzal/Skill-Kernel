from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.core.hashing import sha256_text
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class ContextArtifactRecord:
    context_artifact_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    artifact_kind: str
    source_object_type: str
    source_object_id: UUID | None
    skill_id: UUID | None
    skill_version_id: UUID | None
    broker_policy_version_id: UUID | None
    text_hash: str
    token_count: int
    max_tokens: int
    safety_status: str
    equivalence_status: str
    budget_status: str
    shadowing_status: str
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> ContextArtifactRecord:
        return cls(
            context_artifact_id=row["context_artifact_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            artifact_kind=row["artifact_kind"],
            source_object_type=row["source_object_type"],
            source_object_id=_row_get(row, "source_object_id"),
            skill_id=_row_get(row, "skill_id"),
            skill_version_id=_row_get(row, "skill_version_id"),
            broker_policy_version_id=_row_get(row, "broker_policy_version_id"),
            text_hash=row["text_hash"],
            token_count=int(row["token_count"]),
            max_tokens=int(row["max_tokens"]),
            safety_status=row["safety_status"],
            equivalence_status=row["equivalence_status"],
            budget_status=row["budget_status"],
            shadowing_status=row["shadowing_status"],
            metadata=_json_dict(row["metadata"]),
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "context_artifact_id": str(self.context_artifact_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "artifact_kind": self.artifact_kind,
            "source_object_type": self.source_object_type,
            "source_object_id": str(self.source_object_id) if self.source_object_id else None,
            "skill_id": str(self.skill_id) if self.skill_id else None,
            "skill_version_id": str(self.skill_version_id) if self.skill_version_id else None,
            "broker_policy_version_id": (
                str(self.broker_policy_version_id) if self.broker_policy_version_id else None
            ),
            "text_hash": self.text_hash,
            "token_count": self.token_count,
            "max_tokens": self.max_tokens,
            "safety_status": self.safety_status,
            "equivalence_status": self.equivalence_status,
            "budget_status": self.budget_status,
            "shadowing_status": self.shadowing_status,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class TokenLedgerRecord:
    context_token_ledger_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    context_artifact_id: UUID | None
    skill_id: UUID | None
    skill_version_id: UUID | None
    broker_policy_version_id: UUID | None
    session_id: str | None
    turn_id: str | None
    visibility_state: str
    token_count: int
    outcome: str | None
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> TokenLedgerRecord:
        return cls(
            context_token_ledger_id=row["context_token_ledger_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            context_artifact_id=_row_get(row, "context_artifact_id"),
            skill_id=_row_get(row, "skill_id"),
            skill_version_id=_row_get(row, "skill_version_id"),
            broker_policy_version_id=_row_get(row, "broker_policy_version_id"),
            session_id=_row_get(row, "session_id"),
            turn_id=_row_get(row, "turn_id"),
            visibility_state=row["visibility_state"],
            token_count=int(row["token_count"]),
            outcome=_row_get(row, "outcome"),
            metadata=_json_dict(row["metadata"]),
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "context_token_ledger_id": str(self.context_token_ledger_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "context_artifact_id": (
                str(self.context_artifact_id) if self.context_artifact_id else None
            ),
            "skill_id": str(self.skill_id) if self.skill_id else None,
            "skill_version_id": str(self.skill_version_id) if self.skill_version_id else None,
            "broker_policy_version_id": (
                str(self.broker_policy_version_id) if self.broker_policy_version_id else None
            ),
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "visibility_state": self.visibility_state,
            "token_count": self.token_count,
            "outcome": self.outcome,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


class ContextGovernanceStore(Protocol):
    async def record_artifact(
        self,
        *,
        workspace_key: str,
        artifact_kind: str,
        source_object_type: str,
        text: str,
        max_tokens: int,
        source_object_id: UUID | None = None,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        broker_policy_version_id: UUID | None = None,
        safety_status: str = "pending",
        equivalence_status: str = "pending",
        shadowing_status: str = "pending",
        metadata: dict[str, Any] | None = None,
    ) -> ContextArtifactRecord:
        """Persist context-loadable artifact budget and gate state."""

    async def record_token_ledger(
        self,
        *,
        workspace_key: str,
        visibility_state: str,
        token_count: int,
        context_artifact_id: UUID | None = None,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        broker_policy_version_id: UUID | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        outcome: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TokenLedgerRecord:
        """Record marginal context visibility accounting."""


class NullContextGovernanceStore:
    async def record_artifact(
        self,
        *,
        workspace_key: str,
        artifact_kind: str,
        source_object_type: str,
        text: str,
        max_tokens: int,
        source_object_id: UUID | None = None,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        broker_policy_version_id: UUID | None = None,
        safety_status: str = "pending",
        equivalence_status: str = "pending",
        shadowing_status: str = "pending",
        metadata: dict[str, Any] | None = None,
    ) -> ContextArtifactRecord:
        from uuid import uuid4

        token_count = _estimate_tokens(text)
        return ContextArtifactRecord(
            context_artifact_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            artifact_kind=artifact_kind,
            source_object_type=source_object_type,
            source_object_id=source_object_id,
            skill_id=skill_id,
            skill_version_id=skill_version_id,
            broker_policy_version_id=broker_policy_version_id,
            text_hash=sha256_text(text),
            token_count=token_count,
            max_tokens=max_tokens,
            safety_status=safety_status,
            equivalence_status=equivalence_status,
            budget_status=_budget_status(token_count, max_tokens),
            shadowing_status=shadowing_status,
            metadata=metadata or {},
            created_at=datetime.now(),
        )

    async def record_token_ledger(
        self,
        *,
        workspace_key: str,
        visibility_state: str,
        token_count: int,
        context_artifact_id: UUID | None = None,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        broker_policy_version_id: UUID | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        outcome: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TokenLedgerRecord:
        from uuid import uuid4

        return TokenLedgerRecord(
            context_token_ledger_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            context_artifact_id=context_artifact_id,
            skill_id=skill_id,
            skill_version_id=skill_version_id,
            broker_policy_version_id=broker_policy_version_id,
            session_id=session_id,
            turn_id=turn_id,
            visibility_state=visibility_state,
            token_count=token_count,
            outcome=outcome,
            metadata=metadata or {},
            created_at=datetime.now(),
        )


class AsyncpgContextGovernanceStore(AsyncpgPoolOwner):
    async def record_artifact(
        self,
        *,
        workspace_key: str,
        artifact_kind: str,
        source_object_type: str,
        text: str,
        max_tokens: int,
        source_object_id: UUID | None = None,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        broker_policy_version_id: UUID | None = None,
        safety_status: str = "pending",
        equivalence_status: str = "pending",
        shadowing_status: str = "pending",
        metadata: dict[str, Any] | None = None,
    ) -> ContextArtifactRecord:
        token_count = _estimate_tokens(text)
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.context_artifacts (
                  context_artifact_id,
                  workspace_id,
                  artifact_kind,
                  source_object_type,
                  source_object_id,
                  skill_id,
                  skill_version_id,
                  broker_policy_version_id,
                  text_hash,
                  token_count,
                  max_tokens,
                  safety_status,
                  equivalence_status,
                  budget_status,
                  shadowing_status,
                  metadata
                )
                VALUES (
                  gen_random_uuid(),
                  $1,
                  $2,
                  $3,
                  $4,
                  $5,
                  $6,
                  $7,
                  $8,
                  $9,
                  $10,
                  $11,
                  $12,
                  $13,
                  $14,
                  $15::jsonb
                )
                ON CONFLICT (
                  workspace_id,
                  artifact_kind,
                  source_object_type,
                  source_object_id,
                  text_hash
                )
                DO UPDATE SET
                  token_count = EXCLUDED.token_count,
                  max_tokens = EXCLUDED.max_tokens,
                  safety_status = EXCLUDED.safety_status,
                  equivalence_status = EXCLUDED.equivalence_status,
                  budget_status = EXCLUDED.budget_status,
                  shadowing_status = EXCLUDED.shadowing_status,
                  metadata = EXCLUDED.metadata
                RETURNING *, $16::text AS workspace_key
                """,
                workspace_id,
                artifact_kind,
                source_object_type,
                source_object_id,
                skill_id,
                skill_version_id,
                broker_policy_version_id,
                sha256_text(text),
                token_count,
                max_tokens,
                safety_status,
                equivalence_status,
                _budget_status(token_count, max_tokens),
                shadowing_status,
                _json(metadata or {}),
                workspace_key,
            )
        return ContextArtifactRecord.from_row(row)

    async def record_token_ledger(
        self,
        *,
        workspace_key: str,
        visibility_state: str,
        token_count: int,
        context_artifact_id: UUID | None = None,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        broker_policy_version_id: UUID | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        outcome: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TokenLedgerRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.context_token_ledgers (
                  context_token_ledger_id,
                  workspace_id,
                  context_artifact_id,
                  skill_id,
                  skill_version_id,
                  broker_policy_version_id,
                  session_id,
                  turn_id,
                  visibility_state,
                  token_count,
                  outcome,
                  metadata
                )
                VALUES (
                  gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb
                )
                RETURNING *, $12::text AS workspace_key
                """,
                workspace_id,
                context_artifact_id,
                skill_id,
                skill_version_id,
                broker_policy_version_id,
                session_id,
                turn_id,
                visibility_state,
                token_count,
                outcome,
                _json(metadata or {}),
                workspace_key,
            )
        return TokenLedgerRecord.from_row(row)


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _budget_status(token_count: int, max_tokens: int) -> str:
    return "passed" if token_count <= max_tokens else "over_budget"


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None
