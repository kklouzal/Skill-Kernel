from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.services.evaluator import evaluate_proposal_gate


@dataclass(frozen=True)
class EvaluationRunItem:
    evaluation_id: UUID
    skill_version_id: UUID
    status: str
    result: dict[str, Any]

    def to_json(self) -> dict[str, object]:
        return {
            "evaluation_id": str(self.evaluation_id),
            "skill_version_id": str(self.skill_version_id),
            "status": self.status,
            "result": self.result,
        }


@dataclass(frozen=True)
class EvaluationRunResult:
    scanned: int
    evaluated: int
    blocked: int
    failed: int
    needs_intervention: int
    passed: int
    evaluations: list[EvaluationRunItem]

    def to_json(self) -> dict[str, object]:
        return {
            "scanned": self.scanned,
            "evaluated": self.evaluated,
            "blocked": self.blocked,
            "failed": self.failed,
            "needs_intervention": self.needs_intervention,
            "passed": self.passed,
            "evaluations": [item.to_json() for item in self.evaluations],
        }


class EvaluationStore(Protocol):
    async def run_pending_proposal_gates(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> EvaluationRunResult:
        """Execute deterministic proposal-gate evaluations."""


class NullEvaluationStore:
    async def run_pending_proposal_gates(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> EvaluationRunResult:
        return EvaluationRunResult(
            scanned=0,
            evaluated=0,
            blocked=0,
            failed=0,
            needs_intervention=0,
            passed=0,
            evaluations=[],
        )


class AsyncpgEvaluationStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def run_pending_proposal_gates(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> EvaluationRunResult:
        pool = await self._get_pool()
        items: list[EvaluationRunItem] = []
        async with pool.acquire() as conn, conn.transaction():
            rows = await _claim_planned_evaluations(
                conn,
                workspace_key=workspace_key,
                limit=limit,
            )
            for row in rows:
                probes = await _load_probes(conn, row)
                gate = evaluate_proposal_gate(
                    skill_ir=_json_dict(row["skill_ir"]),
                    scanner_status=row["scanner_status"],
                    probes=probes,
                )
                result = {
                    **_json_dict(row["result"]),
                    **gate.to_json(),
                    "executor": "deterministic-proposal-gate.v1",
                }
                await _finish_evaluation(
                    conn,
                    evaluation_id=row["evaluation_id"],
                    skill_version_id=row["skill_version_id"],
                    status=gate.status,
                    result=result,
                )
                items.append(
                    EvaluationRunItem(
                        evaluation_id=row["evaluation_id"],
                        skill_version_id=row["skill_version_id"],
                        status=gate.status,
                        result=result,
                    )
                )

        return EvaluationRunResult(
            scanned=len(rows),
            evaluated=len(items),
            blocked=sum(1 for item in items if item.status == "blocked"),
            failed=sum(1 for item in items if item.status == "failed"),
            needs_intervention=sum(1 for item in items if item.status == "needs_intervention"),
            passed=sum(1 for item in items if item.status == "passed"),
            evaluations=items,
        )


async def _claim_planned_evaluations(
    conn: asyncpg.Connection,
    *,
    workspace_key: str | None,
    limit: int,
) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT
          ev.evaluation_id,
          ev.workspace_id,
          ev.skill_version_id,
          ev.result,
          sv.skill_ir,
          sv.scanner_status
        FROM autoskill.evaluations ev
        JOIN autoskill.skill_versions sv USING (skill_version_id)
        JOIN autoskill.skills s USING (skill_id)
        JOIN autoskill.workspaces w ON w.workspace_id = ev.workspace_id
        WHERE ev.category = 'proposal_gate'
          AND ev.status = 'planned'
          AND s.lifecycle_state = 'candidate'
          AND ($1::text IS NULL OR w.external_key = $1)
        ORDER BY ev.created_at ASC
        LIMIT $2
        FOR UPDATE OF ev SKIP LOCKED
        """,
        workspace_key,
        limit,
    )


async def _load_probes(conn: asyncpg.Connection, row: asyncpg.Record) -> list[dict[str, Any]]:
    result = _json_dict(row["result"])
    probe_hashes = [str(probe_hash) for probe_hash in result.get("probe_hashes", [])]
    if not probe_hashes:
        return []
    rows = await conn.fetch(
        """
        SELECT probe_hash, kind, maturity, spec, expected
        FROM autoskill.probes
        WHERE workspace_id = $1
          AND probe_hash = ANY($2::text[])
        ORDER BY array_position($2::text[], probe_hash)
        """,
        row["workspace_id"],
        probe_hashes,
    )
    return [
        {
            "probe_hash": record["probe_hash"],
            "kind": record["kind"],
            "maturity": record["maturity"],
            "spec": _json_dict(record["spec"]),
            "expected": _json_dict(record["expected"]),
        }
        for record in rows
    ]


async def _finish_evaluation(
    conn: asyncpg.Connection,
    *,
    evaluation_id: UUID,
    skill_version_id: UUID,
    status: str,
    result: dict[str, Any],
) -> None:
    await conn.execute(
        """
        UPDATE autoskill.evaluations
        SET status = $2,
            result = $3::jsonb
        WHERE evaluation_id = $1
        """,
        evaluation_id,
        status,
        _json(result),
    )
    await conn.execute(
        """
        UPDATE autoskill.skill_versions
        SET evaluator_status = $2
        WHERE skill_version_id = $1
        """,
        skill_version_id,
        status,
    )


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
