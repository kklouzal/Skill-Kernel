from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.services.contrastive import derive_contrastive_replay
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
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        parent_span_id: UUID | None = None,
    ) -> EvaluationRunResult:
        """Execute deterministic proposal-gate evaluations."""

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        """Retire probes and revoke evaluations derived from revoked objects."""


class NullEvaluationStore:
    async def run_pending_proposal_gates(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        parent_span_id: UUID | None = None,
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

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        return 0


class AsyncpgEvaluationStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def run_pending_proposal_gates(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        parent_span_id: UUID | None = None,
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
                probes, contrastive_replays = await _attach_contrastive_replays(
                    conn,
                    workspace_id=row["workspace_id"],
                    probes=probes,
                )
                gate = evaluate_proposal_gate(
                    skill_ir=_json_dict(row["skill_ir"]),
                    scanner_status=row["scanner_status"],
                    probes=probes,
                )
                result = {
                    **_json_dict(row["result"]),
                    **gate.to_json(),
                    "executor": "deterministic-proposal-gate.v1",
                    "evidence_ids": _probe_evidence_ids(probes),
                    "trace_id": str(trace_id) if trace_id else None,
                    "span_id": str(span_id) if span_id else None,
                    "parent_span_id": str(parent_span_id) if parent_span_id else None,
                }
                if contrastive_replays:
                    result["contrastive_replays"] = contrastive_replays
                await _finish_evaluation(
                    conn,
                    workspace_id=row["workspace_id"],
                    evaluation_id=row["evaluation_id"],
                    skill_version_id=row["skill_version_id"],
                    status=gate.status,
                    result=result,
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
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
        async with pool.acquire() as conn, conn.transaction():
            result = await conn.fetchval(
                """
                WITH targets AS (
                  SELECT *
                  FROM unnest($2::text[], $3::uuid[]) AS target(object_type, object_id)
                ),
                version_targets AS (
                  SELECT object_id AS skill_version_id
                  FROM targets
                  WHERE object_type = 'skill_version'
                  UNION
                  SELECT sv.skill_version_id
                  FROM autoskill.skill_versions sv
                  JOIN targets t ON t.object_type = 'skill'
                    AND t.object_id = sv.skill_id
                ),
                retired_probes AS (
                  UPDATE autoskill.probes p
                  SET active = false,
                      retired_at = COALESCE(retired_at, now()),
                      spec = p.spec || jsonb_build_object(
                        'revoked', true,
                        'revoked_at', now(),
                        'revocation_reason', 'derived_object_revoked'
                      )
                  FROM autoskill.workspaces w
                  WHERE p.workspace_id = w.workspace_id
                    AND w.external_key = $1
                    AND p.retired_at IS NULL
                    AND (
                      p.probe_id IN (
                        SELECT object_id FROM targets WHERE object_type = 'probe'
                      )
                      OR p.spec->>'skill_version_id' IN (
                        SELECT skill_version_id::text FROM version_targets
                      )
                    )
                  RETURNING p.probe_id
                ),
                revoked_evaluations AS (
                  UPDATE autoskill.evaluations ev
                  SET status = 'revoked',
                      result = ev.result || jsonb_build_object(
                        'revoked', true,
                        'revoked_at', now(),
                        'revocation_reason', 'derived_object_revoked'
                      )
                  FROM autoskill.workspaces w
                  WHERE ev.workspace_id = w.workspace_id
                    AND w.external_key = $1
                    AND ev.status <> 'revoked'
                    AND (
                      ev.evaluation_id IN (
                        SELECT object_id FROM targets WHERE object_type = 'evaluation'
                      )
                      OR ev.skill_version_id IN (
                        SELECT skill_version_id FROM version_targets
                      )
                    )
                  RETURNING ev.evaluation_id
                )
                SELECT
                  (SELECT count(*) FROM retired_probes)
                  + (SELECT count(*) FROM revoked_evaluations) AS invalidated
                """,
                workspace_key,
                [object_type for object_type, _object_id in object_keys],
                [object_id for _object_type, object_id in object_keys],
            )
        return int(result or 0)


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


async def _attach_contrastive_replays(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    probes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    enriched: list[dict[str, Any]] = []
    replays: list[dict[str, Any]] = []
    for probe in probes:
        spec = _json_dict(probe.get("spec"))
        if probe.get("kind") != "no_skill_control" or spec.get("intervention_replay"):
            enriched.append(probe)
            continue

        evidence_ids = _uuid_list(spec.get("evidence_ids"))
        if not evidence_ids:
            enriched.append(probe)
            continue

        evidence = await _load_replay_evidence(
            conn,
            workspace_id=workspace_id,
            evidence_ids=evidence_ids,
        )
        replay = derive_contrastive_replay(
            evidence,
            candidate_slug=str(spec.get("candidate_slug") or "") or None,
        )
        if replay is None:
            enriched.append(probe)
            continue

        replay_json = replay.to_json()
        updated_spec = {**spec, "intervention_replay": replay_json}
        enriched_probe = {**probe, "maturity": "contrastive", "spec": updated_spec}
        await _persist_contrastive_probe(
            conn,
            workspace_id=workspace_id,
            probe_hash=str(probe["probe_hash"]),
            spec=updated_spec,
            evidence_ids=_uuid_list(replay_json.get("evidence_ids")),
            basis={
                **replay_json["basis"],
                "probe_hash": str(probe["probe_hash"]),
            },
        )
        replays.append(
            {
                "probe_hash": str(probe["probe_hash"]),
                "evidence_ids": replay_json["evidence_ids"],
                "basis": replay_json["basis"],
            }
        )
        enriched.append(enriched_probe)
    return enriched, replays


async def _load_replay_evidence(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    evidence_ids: list[UUID],
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT evidence_id, payload
        FROM autoskill.evidence_items
        WHERE workspace_id = $1
          AND evidence_id = ANY($2::uuid[])
          AND revoked_at IS NULL
        """,
        workspace_id,
        evidence_ids,
    )
    return [
        {
            "evidence_id": str(row["evidence_id"]),
            "payload": _json_dict(row["payload"]),
        }
        for row in rows
    ]


async def _persist_contrastive_probe(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    probe_hash: str,
    spec: dict[str, Any],
    evidence_ids: list[UUID],
    basis: dict[str, Any],
) -> None:
    await conn.execute(
        """
        UPDATE autoskill.probes
        SET maturity = 'contrastive',
            spec = $3::jsonb
        WHERE workspace_id = $1
          AND probe_hash = $2
        """,
        workspace_id,
        probe_hash,
        _json(spec),
    )
    for evidence_id in evidence_ids:
        await conn.execute(
            """
            INSERT INTO autoskill.evidence_maturity (
              evidence_maturity_id, workspace_id, object_type, object_id, maturity, basis
            )
            VALUES (gen_random_uuid(), $1, 'evidence', $2, 'contrastive', $3::jsonb)
            ON CONFLICT (workspace_id, object_type, object_id) DO UPDATE
            SET maturity = EXCLUDED.maturity,
                basis = EXCLUDED.basis,
                updated_at = now()
            """,
            workspace_id,
            evidence_id,
            _json(basis),
        )


async def _finish_evaluation(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    evaluation_id: UUID,
    skill_version_id: UUID,
    status: str,
    result: dict[str, Any],
    trace_id: UUID | None = None,
    span_id: UUID | None = None,
    parent_span_id: UUID | None = None,
) -> None:
    await conn.execute(
        """
        UPDATE autoskill.evaluations
        SET status = $2,
            result = $3::jsonb,
            trace_id = COALESCE($4, trace_id),
            span_id = COALESCE($5, span_id),
            parent_span_id = COALESCE($6, parent_span_id)
        WHERE evaluation_id = $1
        """,
        evaluation_id,
        status,
        _json(result),
        trace_id,
        span_id,
        parent_span_id,
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
    if status == "passed":
        await _record_intervention_maturity(
            conn,
            workspace_id=workspace_id,
            skill_version_id=skill_version_id,
            result=result,
        )


async def _record_intervention_maturity(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    skill_version_id: UUID,
    result: dict[str, Any],
) -> None:
    basis = {
        "evaluation_status": result.get("status"),
        "reason_codes": result.get("reason_codes", []),
        "evaluation_id": result.get("evaluation_id"),
    }
    await conn.execute(
        """
        INSERT INTO autoskill.evidence_maturity (
          evidence_maturity_id, workspace_id, object_type, object_id, maturity, basis
        )
        VALUES (gen_random_uuid(), $1, 'skill_version', $2, 'intervention_validated', $3::jsonb)
        ON CONFLICT (workspace_id, object_type, object_id) DO UPDATE
        SET maturity = EXCLUDED.maturity,
            basis = EXCLUDED.basis,
            updated_at = now()
        """,
        workspace_id,
        skill_version_id,
        _json(basis),
    )
    for evidence_id in _uuid_list(result.get("evidence_ids")):
        await conn.execute(
            """
            INSERT INTO autoskill.evidence_maturity (
              evidence_maturity_id, workspace_id, object_type, object_id, maturity, basis
            )
            VALUES (gen_random_uuid(), $1, 'evidence', $2, 'intervention_validated', $3::jsonb)
            ON CONFLICT (workspace_id, object_type, object_id) DO UPDATE
            SET maturity = EXCLUDED.maturity,
                basis = EXCLUDED.basis,
                updated_at = now()
            """,
            workspace_id,
            evidence_id,
            _json(basis),
        )


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def _probe_evidence_ids(probes: list[dict[str, Any]]) -> list[str]:
    evidence_ids: set[str] = set()
    for probe in probes:
        spec = _json_dict(probe.get("spec"))
        for evidence_id in spec.get("evidence_ids") or []:
            evidence_ids.add(str(evidence_id))
    return sorted(evidence_ids)


def _uuid_list(value: object) -> list[UUID]:
    if not isinstance(value, list):
        return []
    parsed: list[UUID] = []
    for item in value:
        try:
            parsed.append(UUID(str(item)))
        except ValueError:
            continue
    return parsed


def _object_keys(objects: list[dict[str, str]]) -> list[tuple[str, UUID]]:
    keys: list[tuple[str, UUID]] = []
    for item in objects:
        object_type = item.get("object_type")
        object_id = item.get("object_id")
        if not object_type or not object_id:
            continue
        try:
            keys.append((str(object_type), UUID(str(object_id))))
        except ValueError:
            continue
    return keys


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
