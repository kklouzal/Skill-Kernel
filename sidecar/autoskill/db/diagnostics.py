from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.core.hashing import sha256_json
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class DiagnosticMomentumRecord:
    diagnostic_momentum_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    skill_id: UUID | None
    skill_version_id: UUID | None
    executor_profile_id: UUID | None
    issue_signature_hash: str
    diagnostic_kind: str
    root_cause_hypothesis: str
    suggested_change_direction: str
    evidence_count: int
    contrastive_support_count: int
    counterevidence_count: int
    momentum_score: float
    risk_score: float
    status: str
    first_seen_at: datetime
    last_seen_at: datetime

    @classmethod
    def from_row(
        cls,
        row: asyncpg.Record | dict[str, Any],
    ) -> DiagnosticMomentumRecord:
        return cls(
            diagnostic_momentum_id=row["diagnostic_momentum_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            skill_id=_row_get(row, "skill_id"),
            skill_version_id=_row_get(row, "skill_version_id"),
            executor_profile_id=_row_get(row, "executor_profile_id"),
            issue_signature_hash=row["issue_signature_hash"],
            diagnostic_kind=row["diagnostic_kind"],
            root_cause_hypothesis=row["root_cause_hypothesis"],
            suggested_change_direction=row["suggested_change_direction"],
            evidence_count=int(row["evidence_count"]),
            contrastive_support_count=int(row["contrastive_support_count"]),
            counterevidence_count=int(row["counterevidence_count"]),
            momentum_score=float(row["momentum_score"]),
            risk_score=float(row["risk_score"]),
            status=row["status"],
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "diagnostic_momentum_id": str(self.diagnostic_momentum_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "skill_id": str(self.skill_id) if self.skill_id else None,
            "skill_version_id": str(self.skill_version_id) if self.skill_version_id else None,
            "executor_profile_id": (
                str(self.executor_profile_id) if self.executor_profile_id else None
            ),
            "issue_signature_hash": self.issue_signature_hash,
            "diagnostic_kind": self.diagnostic_kind,
            "root_cause_hypothesis": self.root_cause_hypothesis,
            "suggested_change_direction": self.suggested_change_direction,
            "evidence_count": self.evidence_count,
            "contrastive_support_count": self.contrastive_support_count,
            "counterevidence_count": self.counterevidence_count,
            "momentum_score": self.momentum_score,
            "risk_score": self.risk_score,
            "status": self.status,
            "first_seen_at": self.first_seen_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
        }


class DiagnosticMomentumStore(Protocol):
    async def record_signal(
        self,
        *,
        workspace_key: str,
        diagnostic_kind: str,
        root_cause_hypothesis: str,
        suggested_change_direction: str,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        executor_profile_id: UUID | None = None,
        evidence_delta: int = 1,
        contrastive_support_delta: int = 0,
        counterevidence_delta: int = 0,
        risk_score: float = 0.0,
        issue_signature: dict[str, Any] | None = None,
    ) -> DiagnosticMomentumRecord:
        """Accumulate recurring diagnostic evidence before accepting patches."""

    async def list_ready(
        self,
        *,
        workspace_key: str,
        min_momentum_score: float = 2.0,
        limit: int = 100,
    ) -> list[DiagnosticMomentumRecord]:
        """Return diagnostic records ready for probe or patch planning."""

    async def claim_ready_for_repair(
        self,
        *,
        workspace_key: str,
        limit: int = 25,
        min_momentum_score: float = 2.0,
        worker_id: str | None = None,
        job_id: UUID | None = None,
    ) -> list[DiagnosticMomentumRecord]:
        """Claim ready diagnostic records for fail-closed repair execution."""

    async def complete_repair_execution(
        self,
        *,
        workspace_key: str,
        diagnostic_momentum_id: UUID,
        status: str,
        execution: dict[str, Any],
    ) -> None:
        """Record that a ready diagnostic record has queued or blocked repair work."""


class NullDiagnosticMomentumStore:
    async def record_signal(
        self,
        *,
        workspace_key: str,
        diagnostic_kind: str,
        root_cause_hypothesis: str,
        suggested_change_direction: str,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        executor_profile_id: UUID | None = None,
        evidence_delta: int = 1,
        contrastive_support_delta: int = 0,
        counterevidence_delta: int = 0,
        risk_score: float = 0.0,
        issue_signature: dict[str, Any] | None = None,
    ) -> DiagnosticMomentumRecord:
        from uuid import uuid4

        now = datetime.now(UTC)
        evidence_count = max(0, evidence_delta)
        contrastive = max(0, contrastive_support_delta)
        counter = max(0, counterevidence_delta)
        momentum = _momentum_score(evidence_count, contrastive, counter)
        return DiagnosticMomentumRecord(
            diagnostic_momentum_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            skill_id=skill_id,
            skill_version_id=skill_version_id,
            executor_profile_id=executor_profile_id,
            issue_signature_hash=_issue_signature_hash(issue_signature or {}),
            diagnostic_kind=diagnostic_kind,
            root_cause_hypothesis=root_cause_hypothesis,
            suggested_change_direction=suggested_change_direction,
            evidence_count=evidence_count,
            contrastive_support_count=contrastive,
            counterevidence_count=counter,
            momentum_score=momentum,
            risk_score=risk_score,
            status=_status_for(momentum, risk_score),
            first_seen_at=now,
            last_seen_at=now,
        )

    async def list_ready(
        self,
        *,
        workspace_key: str,
        min_momentum_score: float = 2.0,
        limit: int = 100,
    ) -> list[DiagnosticMomentumRecord]:
        return []

    async def claim_ready_for_repair(
        self,
        *,
        workspace_key: str,
        limit: int = 25,
        min_momentum_score: float = 2.0,
        worker_id: str | None = None,
        job_id: UUID | None = None,
    ) -> list[DiagnosticMomentumRecord]:
        return []

    async def complete_repair_execution(
        self,
        *,
        workspace_key: str,
        diagnostic_momentum_id: UUID,
        status: str,
        execution: dict[str, Any],
    ) -> None:
        return None


class AsyncpgDiagnosticMomentumStore(AsyncpgPoolOwner):
    async def record_signal(
        self,
        *,
        workspace_key: str,
        diagnostic_kind: str,
        root_cause_hypothesis: str,
        suggested_change_direction: str,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        executor_profile_id: UUID | None = None,
        evidence_delta: int = 1,
        contrastive_support_delta: int = 0,
        counterevidence_delta: int = 0,
        risk_score: float = 0.0,
        issue_signature: dict[str, Any] | None = None,
    ) -> DiagnosticMomentumRecord:
        evidence_delta = max(0, evidence_delta)
        contrastive_support_delta = max(0, contrastive_support_delta)
        counterevidence_delta = max(0, counterevidence_delta)
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.diagnostic_momentum (
                  diagnostic_momentum_id,
                  workspace_id,
                  skill_id,
                  skill_version_id,
                  executor_profile_id,
                  issue_signature_hash,
                  diagnostic_kind,
                  root_cause_hypothesis,
                  suggested_change_direction,
                  evidence_count,
                  contrastive_support_count,
                  counterevidence_count,
                  momentum_score,
                  risk_score,
                  status
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
                  $14
                )
                ON CONFLICT (
                  workspace_id,
                  skill_id,
                  executor_profile_id,
                  issue_signature_hash,
                  diagnostic_kind
                )
                DO UPDATE SET
                  root_cause_hypothesis = EXCLUDED.root_cause_hypothesis,
                  suggested_change_direction = EXCLUDED.suggested_change_direction,
                  evidence_count = autoskill.diagnostic_momentum.evidence_count
                    + EXCLUDED.evidence_count,
                  contrastive_support_count =
                    autoskill.diagnostic_momentum.contrastive_support_count
                    + EXCLUDED.contrastive_support_count,
                  counterevidence_count =
                    autoskill.diagnostic_momentum.counterevidence_count
                    + EXCLUDED.counterevidence_count,
                  risk_score = GREATEST(
                    autoskill.diagnostic_momentum.risk_score,
                    EXCLUDED.risk_score
                  ),
                  momentum_score = (
                    autoskill.diagnostic_momentum.evidence_count
                    + EXCLUDED.evidence_count
                    + (
                      2 * (
                        autoskill.diagnostic_momentum.contrastive_support_count
                        + EXCLUDED.contrastive_support_count
                      )
                    )
                    - (
                      autoskill.diagnostic_momentum.counterevidence_count
                      + EXCLUDED.counterevidence_count
                    )
                  )::double precision,
                  status = CASE
                    WHEN GREATEST(
                      autoskill.diagnostic_momentum.risk_score,
                      EXCLUDED.risk_score
                    ) >= 0.8 THEN 'ready_for_probe'
                    WHEN (
                      autoskill.diagnostic_momentum.evidence_count
                      + EXCLUDED.evidence_count
                      + (
                        2 * (
                          autoskill.diagnostic_momentum.contrastive_support_count
                          + EXCLUDED.contrastive_support_count
                        )
                      )
                      - (
                        autoskill.diagnostic_momentum.counterevidence_count
                        + EXCLUDED.counterevidence_count
                      )
                    ) >= 4 THEN 'ready_for_patch'
                    WHEN (
                      autoskill.diagnostic_momentum.evidence_count
                      + EXCLUDED.evidence_count
                      + (
                        2 * (
                          autoskill.diagnostic_momentum.contrastive_support_count
                          + EXCLUDED.contrastive_support_count
                        )
                      )
                      - (
                        autoskill.diagnostic_momentum.counterevidence_count
                        + EXCLUDED.counterevidence_count
                      )
                    ) >= 2 THEN 'ready_for_probe'
                    ELSE 'accumulating'
                  END,
                  last_seen_at = now()
                RETURNING *, $15::text AS workspace_key
                """,
                workspace_id,
                skill_id,
                skill_version_id,
                executor_profile_id,
                _issue_signature_hash(issue_signature or {}),
                diagnostic_kind,
                root_cause_hypothesis,
                suggested_change_direction,
                evidence_delta,
                contrastive_support_delta,
                counterevidence_delta,
                _momentum_score(
                    evidence_delta,
                    contrastive_support_delta,
                    counterevidence_delta,
                ),
                risk_score,
                _status_for(
                    _momentum_score(
                        evidence_delta,
                        contrastive_support_delta,
                        counterevidence_delta,
                    ),
                    risk_score,
                ),
                workspace_key,
            )
        return DiagnosticMomentumRecord.from_row(row)

    async def list_ready(
        self,
        *,
        workspace_key: str,
        min_momentum_score: float = 2.0,
        limit: int = 100,
    ) -> list[DiagnosticMomentumRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                SELECT *, $3::text AS workspace_key
                FROM autoskill.diagnostic_momentum
                WHERE workspace_id = $1
                  AND momentum_score >= $2
                  AND status IN ('ready_for_probe', 'ready_for_patch')
                ORDER BY momentum_score DESC, last_seen_at DESC
                LIMIT $4
                """,
                workspace_id,
                min_momentum_score,
                workspace_key,
                max(1, min(limit, 1000)),
            )
        return [DiagnosticMomentumRecord.from_row(row) for row in rows]

    async def claim_ready_for_repair(
        self,
        *,
        workspace_key: str,
        limit: int = 25,
        min_momentum_score: float = 2.0,
        worker_id: str | None = None,
        job_id: UUID | None = None,
    ) -> list[DiagnosticMomentumRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                WITH ready AS (
                  SELECT diagnostic_momentum_id
                  FROM autoskill.diagnostic_momentum
                  WHERE workspace_id = $1
                    AND momentum_score >= $2
                    AND status IN ('ready_for_probe', 'ready_for_patch')
                  ORDER BY momentum_score DESC, last_seen_at DESC
                  LIMIT $4
                  FOR UPDATE SKIP LOCKED
                )
                UPDATE autoskill.diagnostic_momentum dm
                SET status = 'repairing',
                    last_seen_at = now()
                FROM ready
                WHERE dm.diagnostic_momentum_id = ready.diagnostic_momentum_id
                RETURNING dm.*, $3::text AS workspace_key
                """,
                workspace_id,
                min_momentum_score,
                workspace_key,
                max(1, min(limit, 1000)),
            )
        return [DiagnosticMomentumRecord.from_row(row) for row in rows]

    async def complete_repair_execution(
        self,
        *,
        workspace_key: str,
        diagnostic_momentum_id: UUID,
        status: str,
        execution: dict[str, Any],
    ) -> None:
        next_status = "repair_queued" if status == "queued" else "ready_for_probe"
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            await conn.execute(
                """
                UPDATE autoskill.diagnostic_momentum
                SET status = $3,
                    last_seen_at = now()
                WHERE workspace_id = $1
                  AND diagnostic_momentum_id = $2
                """,
                workspace_id,
                diagnostic_momentum_id,
                next_status,
            )


def _momentum_score(
    evidence_count: int,
    contrastive_support_count: int,
    counterevidence_count: int,
) -> float:
    return float(evidence_count + (2 * contrastive_support_count) - counterevidence_count)


def _status_for(momentum_score: float, risk_score: float) -> str:
    if momentum_score >= 4:
        return "ready_for_patch"
    if risk_score >= 0.8 or momentum_score >= 2:
        return "ready_for_probe"
    return "accumulating"


def _issue_signature_hash(signature: dict[str, Any]) -> str:
    return sha256_json(signature or {"signature": "default"})


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None
