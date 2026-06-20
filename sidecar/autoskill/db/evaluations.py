from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.core.enums import PROPOSAL_GATE_LIFECYCLE_STATES, LifecycleState
from autoskill.core.skillir import SkillIR
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.services.contrastive import derive_contrastive_replay
from autoskill.services.evaluator import evaluate_proposal_gate
from autoskill.services.probes import plan_candidate_probes, probe_scan_envelope

AUTONOMOUS_REMEDIATION_ACTIONS = (
    "collect_more_evidence",
    "run_more_probes",
    "run_re_adjudication",
    "stage_ephemeral_candidate",
    "stage_canary",
    "reduce_scope",
    "auto_reject",
    "no_op_reschedule",
)

RESCHEDULED_REMEDIATION_STATUSES = {
    "rescheduled_for_contrastive_replay",
    "rescheduled_for_re_adjudication",
    "rescheduled_for_additional_probes",
    "ephemeral_candidate_staged",
    "no_op_rescheduled",
}


@dataclass(frozen=True)
class EvaluationRunItem:
    evaluation_id: UUID
    skill_version_id: UUID
    executor_profile_id: UUID | None
    status: str
    result: dict[str, Any]

    def to_json(self) -> dict[str, object]:
        return {
            "evaluation_id": str(self.evaluation_id),
            "skill_version_id": str(self.skill_version_id),
            "executor_profile_id": (
                str(self.executor_profile_id) if self.executor_profile_id else None
            ),
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


@dataclass(frozen=True)
class EvaluationFallbackRemediationResult:
    scanned: int
    reset_to_planned: int
    waiting_for_evidence: int
    contrastive_replays: int
    threshold_deadlocks: int
    remediations: list[dict[str, Any]]

    def to_json(self) -> dict[str, object]:
        return {
            "scanned": self.scanned,
            "reset_to_planned": self.reset_to_planned,
            "waiting_for_evidence": self.waiting_for_evidence,
            "contrastive_replays": self.contrastive_replays,
            "threshold_deadlocks": self.threshold_deadlocks,
            "remediations": self.remediations,
        }


@dataclass(frozen=True)
class MissingProbeUpsertResult:
    added_probe_hashes: list[str]
    blocked_probe_scans: list[dict[str, Any]]


@dataclass(frozen=True)
class EvaluationReviewRecord:
    workspace_id: UUID | None
    workspace_key: str | None
    evaluation_id: UUID
    skill_version_id: UUID | None
    skill_slug: str | None
    skill_version: int | None
    executor_profile_id: UUID | None
    category: str
    status: str
    result_summary: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> EvaluationReviewRecord:
        result = _json_dict(row["result"])
        return cls(
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            evaluation_id=row["evaluation_id"],
            skill_version_id=_row_get(row, "skill_version_id"),
            skill_slug=_row_get(row, "skill_slug"),
            skill_version=_row_get(row, "skill_version"),
            executor_profile_id=_row_get(row, "executor_profile_id"),
            category=row["category"],
            status=row["status"],
            result_summary={
                "candidate_slug": result.get("candidate_slug"),
                "required_gates": result.get("required_gates"),
                "status": result.get("status"),
                "summary": result.get("summary"),
                "reason_codes": list(result.get("reason_codes") or []),
                "autonomy_assurance": _safe_autonomy_assurance(
                    _json_dict(result.get("autonomy_assurance"))
                ),
                "autonomy_fallback": _safe_autonomy_fallback(
                    _json_dict(result.get("autonomy_fallback"))
                ),
                "autonomy_remediation": _safe_autonomy_remediation(
                    _json_dict(result.get("autonomy_remediation"))
                ),
            },
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, object]:
        return {
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "evaluation_id": str(self.evaluation_id),
            "skill_version_id": (
                str(self.skill_version_id) if self.skill_version_id else None
            ),
            "skill_slug": self.skill_slug,
            "skill_version": self.skill_version,
            "executor_profile_id": (
                str(self.executor_profile_id) if self.executor_profile_id else None
            ),
            "category": self.category,
            "status": self.status,
            "result_summary": self.result_summary,
            "created_at": self.created_at.isoformat(),
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

    async def list_evaluation_reviews(
        self,
        *,
        workspace_key: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[EvaluationReviewRecord]:
        """List proposal evaluation statuses for operator review."""

    async def remediate_autonomy_fallbacks(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        parent_span_id: UUID | None = None,
    ) -> EvaluationFallbackRemediationResult:
        """Run autonomous remediation for stalled proposal-gate fallback actions."""

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        """Retire probes and revoke evaluations derived from revoked objects."""


class NullEvaluationStore:
    def __init__(self) -> None:
        self.reviews: list[EvaluationReviewRecord] = []

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

    async def list_evaluation_reviews(
        self,
        *,
        workspace_key: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[EvaluationReviewRecord]:
        reviews = self.reviews
        if workspace_key is not None:
            reviews = [review for review in reviews if review.workspace_key == workspace_key]
        if status is not None:
            reviews = [review for review in reviews if review.status == status]
        return reviews[: max(1, min(limit, 250))]

    async def remediate_autonomy_fallbacks(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        parent_span_id: UUID | None = None,
    ) -> EvaluationFallbackRemediationResult:
        return EvaluationFallbackRemediationResult(
            scanned=0,
            reset_to_planned=0,
            waiting_for_evidence=0,
            contrastive_replays=0,
            threshold_deadlocks=0,
            remediations=[],
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
                    executor_profile_id=row["executor_profile_id"],
                )
                result = {
                    **_json_dict(row["result"]),
                    **gate.to_json(),
                    "executor": "deterministic-proposal-gate.v1",
                    "executor_profile_id": (
                        str(row["executor_profile_id"])
                        if row["executor_profile_id"]
                        else None
                    ),
                    "workspace_key": row["workspace_key"],
                    "skill_id": str(row["skill_id"]),
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
                    executor_profile_id=row["executor_profile_id"],
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
                        executor_profile_id=row["executor_profile_id"],
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

    async def list_evaluation_reviews(
        self,
        *,
        workspace_key: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[EvaluationReviewRecord]:
        pool = await self._get_pool()
        rows = await pool.fetch(
            """
            SELECT
              w.workspace_id,
              w.external_key AS workspace_key,
              ev.evaluation_id,
              ev.skill_version_id,
              s.slug AS skill_slug,
              sv.version AS skill_version,
              ev.executor_profile_id,
              ev.category,
              ev.status,
              ev.result,
              ev.created_at
            FROM autoskill.evaluations ev
            JOIN autoskill.workspaces w USING (workspace_id)
            LEFT JOIN autoskill.skill_versions sv
              ON sv.skill_version_id = ev.skill_version_id
            LEFT JOIN autoskill.skills s
              ON s.skill_id = sv.skill_id
            WHERE ($1::text IS NULL OR w.external_key = $1)
              AND ($2::text IS NULL OR ev.status = $2)
            ORDER BY ev.created_at DESC, ev.evaluation_id DESC
            LIMIT $3
            """,
            workspace_key,
            status,
            max(1, min(limit, 250)),
        )
        return [EvaluationReviewRecord.from_row(row) for row in rows]

    async def remediate_autonomy_fallbacks(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        parent_span_id: UUID | None = None,
    ) -> EvaluationFallbackRemediationResult:
        pool = await self._get_pool()
        remediations: list[dict[str, Any]] = []
        reset_to_planned = 0
        waiting_for_evidence = 0
        contrastive_replay_count = 0
        threshold_deadlocks = 0
        async with pool.acquire() as conn, conn.transaction():
            rows = await _claim_fallback_remediation_evaluations(
                conn,
                workspace_key=workspace_key,
                limit=limit,
            )
            for row in rows:
                result = _json_dict(row["result"])
                fallback = _json_dict(result.get("autonomy_fallback"))
                selected_action = str(fallback.get("selected_action") or "")
                probes = await _load_probes(conn, row)
                supplemental_probe_hashes: list[str] = []
                blocked_probe_scans: list[dict[str, Any]] = []
                if selected_action == "run_more_probes":
                    supplemental_probe_upsert = await _upsert_missing_candidate_probes(
                        conn,
                        workspace_id=row["workspace_id"],
                        skill_version_id=row["skill_version_id"],
                        skill_ir=_json_dict(row["skill_ir"]),
                        current_probe_hashes=[
                            str(probe_hash)
                            for probe_hash in result.get("probe_hashes", [])
                        ],
                    )
                    supplemental_probe_hashes = (
                        supplemental_probe_upsert.added_probe_hashes
                    )
                    blocked_probe_scans = supplemental_probe_upsert.blocked_probe_scans
                _enriched, contrastive_replays = await _attach_contrastive_replays(
                    conn,
                    workspace_id=row["workspace_id"],
                    probes=probes,
                )
                contrastive_replay_count += len(contrastive_replays)
                selected_action = _trial_lane_action(
                    result,
                    selected_action=selected_action,
                    scanner_status=str(row["scanner_status"] or ""),
                )
                remediation, attempt_count, threshold_deadlock = _remediation_patch(
                    result,
                    selected_action=selected_action,
                    contrastive_replays=contrastive_replays,
                    supplemental_probe_hashes=supplemental_probe_hashes,
                    blocked_probe_scans=blocked_probe_scans,
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                )
                if threshold_deadlock:
                    threshold_deadlocks += 1
                    await _mark_threshold_deadlock_status(
                        conn,
                        workspace_id=row["workspace_id"],
                        skill_version_id=row["skill_version_id"],
                        decision_id=_optional_uuid(fallback.get("autonomy_decision_id")),
                        result=result,
                    )

                updated_result = {
                    **result,
                    "autonomy_remediation": remediation,
                }
                if supplemental_probe_hashes:
                    updated_result["probe_hashes"] = _dedupe(
                        [
                            *[
                                str(probe_hash)
                                for probe_hash in result.get("probe_hashes", [])
                            ],
                            *supplemental_probe_hashes,
                        ]
                    )
                if selected_action == "stage_ephemeral_candidate":
                    await _stage_ephemeral_candidate(
                        conn,
                        workspace_id=row["workspace_id"],
                        skill_id=row["skill_id"],
                    )
                    await _mark_threshold_deadlock_trialing(
                        conn,
                        workspace_id=row["workspace_id"],
                        skill_version_id=row["skill_version_id"],
                    )
                if selected_action == "auto_reject":
                    updated_result.pop("autonomy_fallback", None)
                    updated_result["status"] = "failed"
                    updated_result["reason_codes"] = _dedupe(
                        [
                            *[
                                str(code)
                                for code in result.get("reason_codes", [])
                            ],
                            "auto-rejected-by-autonomy-fallback",
                        ]
                    )
                    await _finish_evaluation(
                        conn,
                        workspace_id=row["workspace_id"],
                        evaluation_id=row["evaluation_id"],
                        skill_version_id=row["skill_version_id"],
                        executor_profile_id=row["executor_profile_id"],
                        status="failed",
                        result=updated_result,
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=parent_span_id,
                    )
                    remediations.append(
                        {
                            "evaluation_id": str(row["evaluation_id"]),
                            "skill_version_id": str(row["skill_version_id"]),
                            "selected_action": selected_action,
                            "status": remediation["status"],
                            "threshold_deadlock_candidate": threshold_deadlock,
                            "attempt_count": attempt_count,
                            "contrastive_replays": len(contrastive_replays),
                        }
                    )
                    continue
                reschedule = not threshold_deadlock and (
                    remediation["status"] in RESCHEDULED_REMEDIATION_STATUSES
                )
                if reschedule:
                    updated_result.pop("autonomy_fallback", None)
                    await _reset_evaluation_to_planned(
                        conn,
                        evaluation_id=row["evaluation_id"],
                        skill_version_id=row["skill_version_id"],
                        result=updated_result,
                    )
                    reset_to_planned += 1
                else:
                    await conn.execute(
                        """
                        UPDATE autoskill.evaluations
                        SET result = $2::jsonb,
                            trace_id = COALESCE($3, trace_id),
                            span_id = COALESCE($4, span_id),
                            parent_span_id = COALESCE($5, parent_span_id)
                        WHERE evaluation_id = $1
                        """,
                        row["evaluation_id"],
                        _json(updated_result),
                        trace_id,
                        span_id,
                        parent_span_id,
                    )
                    waiting_for_evidence += 1
                remediations.append(
                    {
                        "evaluation_id": str(row["evaluation_id"]),
                        "skill_version_id": str(row["skill_version_id"]),
                        "selected_action": selected_action,
                        "status": remediation["status"],
                        "attempt_count": attempt_count,
                        "contrastive_replays": len(contrastive_replays),
                        "threshold_deadlock_recorded": threshold_deadlock,
                    }
                )

        return EvaluationFallbackRemediationResult(
            scanned=len(rows),
            reset_to_planned=reset_to_planned,
            waiting_for_evidence=waiting_for_evidence,
            contrastive_replays=contrastive_replay_count,
            threshold_deadlocks=threshold_deadlocks,
            remediations=remediations,
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
          ev.executor_profile_id,
          ev.result,
          w.external_key AS workspace_key,
          s.skill_id,
          sv.skill_ir,
          sv.scanner_status
        FROM autoskill.evaluations ev
        JOIN autoskill.skill_versions sv USING (skill_version_id)
        JOIN autoskill.skills s USING (skill_id)
        JOIN autoskill.workspaces w ON w.workspace_id = ev.workspace_id
        WHERE ev.category = 'proposal_gate'
          AND ev.status = 'planned'
          AND s.lifecycle_state = ANY($3::text[])
          AND ($1::text IS NULL OR w.external_key = $1)
        ORDER BY ev.created_at ASC
        LIMIT $2
        FOR UPDATE OF ev SKIP LOCKED
        """,
        workspace_key,
        limit,
        list(PROPOSAL_GATE_LIFECYCLE_STATES),
    )


async def _claim_fallback_remediation_evaluations(
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
          ev.executor_profile_id,
          ev.result,
          w.external_key AS workspace_key,
          s.skill_id,
          sv.skill_ir,
          sv.scanner_status
        FROM autoskill.evaluations ev
        JOIN autoskill.skill_versions sv USING (skill_version_id)
        JOIN autoskill.skills s USING (skill_id)
        JOIN autoskill.workspaces w ON w.workspace_id = ev.workspace_id
        WHERE ev.category = 'proposal_gate'
          AND ev.status = 'needs_intervention'
          AND ev.result ? 'autonomy_fallback'
          AND ev.result #>> '{autonomy_fallback,selected_action}' = ANY($3::text[])
          AND COALESCE(ev.result #>> '{autonomy_remediation,status}', '') NOT IN (
            'ephemeral_candidate_staged',
            'canary_staged',
            'scope_reduction_recorded',
            'auto_rejected'
          )
          AND (
            (
              COALESCE(ev.result #>> '{autonomy_remediation,status}', '')
                <> 'threshold_deadlock_candidate'
              AND COALESCE(
                (
                  ev.result #>>
                    '{autonomy_remediation,threshold_deadlock_candidate}'
                )::boolean,
                false
              ) IS NOT true
              AND NOT EXISTS (
                SELECT 1
                FROM autoskill.threshold_deadlock_findings tdf
                WHERE tdf.workspace_id = ev.workspace_id
                  AND tdf.policy_kind = 'proposal_gate_acceptance_policy.v1'
                  AND tdf.status = 'open'
                  AND ev.skill_version_id = ANY(tdf.stalled_candidate_ids)
              )
            )
            OR (
              sv.scanner_status = 'passed'
              AND ev.result #>> '{autonomy_fallback,selected_action}' = ANY($5::text[])
              AND COALESCE(
                jsonb_array_length(
                  ev.result #> '{autonomy_assurance,hard_invariant_failures}'
                ),
                0
              ) = 0
              AND COALESCE(
                (ev.result #>> '{autonomy_fallback,deterministic_checks,hard_invariants_passed}')::boolean,
                true
              ) IS true
              AND (
                COALESCE(ev.result -> 'reason_codes', '[]'::jsonb) ?| $6::text[]
                OR COALESCE(
                  ev.result #> '{autonomy_assurance,soft_threshold_misses}',
                  '[]'::jsonb
                ) ?| $6::text[]
              )
              AND jsonb_path_exists(
                ev.result,
                '$.probe_results[*] ? (@.kind == "no_skill_control" && @.status == "needs_intervention")'
              )
              AND NOT jsonb_path_exists(
                ev.result,
                '$.probe_results[*] ? (!((@.kind == "no_skill_control" && @.status == "needs_intervention") || ((@.kind == "target" || @.kind == "regression" || @.kind == "adversarial") && @.status == "passed")))'
              )
            )
          )
          AND s.lifecycle_state = ANY($4::text[])
          AND ($1::text IS NULL OR w.external_key = $1)
        ORDER BY
          COALESCE(
            (ev.result #>> '{autonomy_remediation,updated_at}')::timestamptz,
            ev.created_at
          ) ASC,
          ev.created_at ASC
        LIMIT $2
        FOR UPDATE OF ev SKIP LOCKED
        """,
        workspace_key,
        limit,
        list(AUTONOMOUS_REMEDIATION_ACTIONS),
        list(PROPOSAL_GATE_LIFECYCLE_STATES),
        [
            "collect_more_evidence",
            "run_more_probes",
            "run_re_adjudication",
            "no_op_reschedule",
        ],
        ["intervention-required", "no_skill_control-evidence-insufficient"],
    )


async def _upsert_missing_candidate_probes(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    skill_version_id: UUID,
    skill_ir: dict[str, Any],
    current_probe_hashes: list[str],
) -> MissingProbeUpsertResult:
    try:
        skill = SkillIR.model_validate(skill_ir)
    except Exception:
        return MissingProbeUpsertResult(added_probe_hashes=[], blocked_probe_scans=[])
    current = {str(probe_hash) for probe_hash in current_probe_hashes}
    added: list[str] = []
    blocked_probe_scans: list[dict[str, Any]] = []
    for probe in plan_candidate_probes(skill):
        if probe.probe_hash in current:
            continue
        if not probe.ok:
            blocked_probe_scans.append(probe_scan_envelope(probe))
            continue
        spec = {
            **probe.spec,
            "skill_version_id": str(skill_version_id),
            "candidate_slug": skill.slug,
            "source": "evaluations.remediate_fallbacks",
            "remediation_action": "run_more_probes",
        }
        await conn.execute(
            """
            INSERT INTO autoskill.probes (
              probe_id, workspace_id, probe_hash, kind, maturity, spec, expected, active
            )
            VALUES (gen_random_uuid(), $1, $2, $3, $4, $5::jsonb, $6::jsonb, false)
            ON CONFLICT (workspace_id, probe_hash) DO NOTHING
            """,
            workspace_id,
            probe.probe_hash,
            probe.kind,
            probe.maturity,
            _json(spec),
            _json(probe.expected),
        )
        added.append(probe.probe_hash)
    return MissingProbeUpsertResult(
        added_probe_hashes=added,
        blocked_probe_scans=blocked_probe_scans,
    )


async def _stage_ephemeral_candidate(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    skill_id: UUID,
) -> None:
    await conn.execute(
        """
        UPDATE autoskill.skills
        SET lifecycle_state = $3,
            updated_at = now()
        WHERE workspace_id = $1
          AND skill_id = $2
          AND lifecycle_state IN (
            'observed_pattern',
            'candidate_cluster',
            'ephemeral_candidate',
            'trial_candidate',
            'validated_candidate',
            'candidate'
          )
        """,
        workspace_id,
        skill_id,
        LifecycleState.EPHEMERAL_CANDIDATE.value,
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


async def _reset_evaluation_to_planned(
    conn: asyncpg.Connection,
    *,
    evaluation_id: UUID,
    skill_version_id: UUID,
    result: dict[str, Any],
) -> None:
    await conn.execute(
        """
        UPDATE autoskill.evaluations
        SET status = 'planned',
            result = $2::jsonb
        WHERE evaluation_id = $1
        """,
        evaluation_id,
        _json(result),
    )
    await conn.execute(
        """
        UPDATE autoskill.skill_versions
        SET evaluator_status = 'pending'
        WHERE skill_version_id = $1
        """,
        skill_version_id,
    )


async def _mark_threshold_deadlock_status(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    skill_version_id: UUID,
    decision_id: UUID | None,
    result: dict[str, Any],
) -> None:
    reason_codes = _reason_codes_for_deadlock(result)
    recommended_action = _recommended_deadlock_action(
        result,
        selected_action=str(
            _json_dict(result.get("autonomy_fallback")).get("selected_action")
            or _json_dict(result.get("autonomy_remediation")).get("selected_action")
            or ""
        ),
    )
    await conn.execute(
        """
        INSERT INTO autoskill.threshold_deadlock_findings (
          threshold_deadlock_id,
          workspace_id,
          policy_kind,
          stalled_candidate_ids,
          stall_reason_codes,
          hard_invariants_passed,
          llm_high_utility_count,
          recommended_action,
          status
        )
        SELECT
          gen_random_uuid(),
          $1,
          'proposal_gate_acceptance_policy.v1',
          ARRAY[$2]::uuid[],
          $3::text[],
          true,
          0,
          $4,
          'open'
        WHERE NOT EXISTS (
          SELECT 1
          FROM autoskill.threshold_deadlock_findings
          WHERE workspace_id = $1
            AND policy_kind = 'proposal_gate_acceptance_policy.v1'
            AND status = 'open'
            AND $2 = ANY(stalled_candidate_ids)
            AND stall_reason_codes = $3::text[]
        )
        """,
        workspace_id,
        skill_version_id,
        reason_codes,
        recommended_action,
    )
    if decision_id is not None:
        await conn.execute(
            """
            UPDATE autoskill.admin_autonomy_decision_status
            SET soft_threshold_state = 'threshold_deadlock_candidate',
                dominant_reason_code = 'threshold_deadlock',
                updated_at = now()
            WHERE decision_id = $1
            """,
            decision_id,
        )


async def _mark_threshold_deadlock_trialing(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    skill_version_id: UUID,
) -> None:
    await conn.execute(
        """
        UPDATE autoskill.threshold_deadlock_findings
        SET status = 'trialing_policy',
            resolved_at = now()
        WHERE workspace_id = $1
          AND policy_kind = 'proposal_gate_acceptance_policy.v1'
          AND status = 'open'
          AND $2 = ANY(stalled_candidate_ids)
        """,
        workspace_id,
        skill_version_id,
    )


def _remediation_patch(
    result: dict[str, Any],
    *,
    selected_action: str,
    contrastive_replays: list[dict[str, Any]],
    supplemental_probe_hashes: list[str] | None = None,
    trace_id: UUID | None,
    span_id: UUID | None,
    parent_span_id: UUID | None,
    blocked_probe_scans: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], int, bool]:
    supplemental_probe_hashes = supplemental_probe_hashes or []
    blocked_probe_scans = blocked_probe_scans or []
    previous = _json_dict(result.get("autonomy_remediation"))
    previous_attempts = _json_list(previous.get("attempts"))
    attempt_count = int(previous.get("attempt_count") or 0) + 1
    attempted = [
        "inspect_evidence_coverage",
        "derive_contrastive_replay_from_permitted_evidence",
    ]
    if selected_action == "run_more_probes":
        attempted.append("generate_additional_probe_plan")
    if supplemental_probe_hashes:
        attempted.append("persist_missing_candidate_probes")
    if blocked_probe_scans:
        attempted.append("blocked_generated_probe_scanner_findings")
    if selected_action == "run_re_adjudication":
        attempted.append("run_llm_re_adjudication")
    if selected_action == "stage_ephemeral_candidate":
        attempted.append("stage_ephemeral_candidate")
    if selected_action == "stage_canary":
        attempted.append("stage_canary_with_smaller_blast_radius")
    if selected_action == "reduce_scope":
        attempted.append("record_scope_reduction_required")
    if selected_action == "auto_reject":
        attempted.append("auto_reject_with_reason")
    if selected_action == "no_op_reschedule":
        attempted.append("no_op_reschedule")
    status = "waiting_for_contrastive_evidence"
    if contrastive_replays:
        status = "rescheduled_for_contrastive_replay"
    elif supplemental_probe_hashes or (
        selected_action == "run_more_probes" and attempt_count < 3
    ):
        status = "rescheduled_for_additional_probes"
    elif selected_action == "run_re_adjudication" and attempt_count < 3:
        status = "rescheduled_for_re_adjudication"
    elif selected_action == "stage_ephemeral_candidate":
        status = "ephemeral_candidate_staged"
    elif selected_action == "stage_canary":
        status = "canary_staged"
    elif selected_action == "reduce_scope":
        status = "scope_reduction_recorded"
    elif selected_action == "auto_reject":
        status = "auto_rejected"
    hard_failures = _json_dict(result.get("autonomy_assurance")).get(
        "hard_invariant_failures"
    )
    if selected_action == "no_op_reschedule" and not hard_failures:
        status = "rescheduled_for_re_adjudication"
    threshold_deadlock = (
        selected_action not in {"auto_reject", "stage_ephemeral_candidate", "stage_canary"}
        and not contrastive_replays
        and not supplemental_probe_hashes
        and attempt_count >= 3
        and not hard_failures
    )
    if threshold_deadlock:
        status = "threshold_deadlock_candidate"
    recommended_action = (
        _recommended_deadlock_action(result, selected_action=selected_action)
        if threshold_deadlock
        else None
    )
    attempt = {
        "attempt": attempt_count,
        "selected_action": selected_action,
        "status": status,
        "attempted_autonomous_remedies": attempted,
        "contrastive_replays": len(contrastive_replays),
        "supplemental_probe_hashes": supplemental_probe_hashes,
        "blocked_probe_scans": blocked_probe_scans,
        "updated_at": datetime.now(UTC).isoformat(),
        "trace_id": str(trace_id) if trace_id else None,
        "span_id": str(span_id) if span_id else None,
        "parent_span_id": str(parent_span_id) if parent_span_id else None,
    }
    return (
        {
            "schema": "autoskill.proposal-gate-autonomy-remediation.v1",
            "source": "evaluations.remediate_fallbacks",
            "selected_action": selected_action,
            "status": status,
            "attempt_count": attempt_count,
            "attempted_autonomous_remedies": attempted,
            "contrastive_replays": contrastive_replays,
            "supplemental_probe_hashes": supplemental_probe_hashes,
            "blocked_probe_scans": blocked_probe_scans,
            "reason_codes": (
                ["probe-scanner-blocked"] if blocked_probe_scans else []
            ),
            "threshold_deadlock_candidate": threshold_deadlock,
            "recommended_action": recommended_action,
            "attempts": [*previous_attempts[-9:], attempt],
            "updated_at": attempt["updated_at"],
        },
        attempt_count,
        threshold_deadlock,
    )


def _trial_lane_action(
    result: dict[str, Any],
    *,
    selected_action: str,
    scanner_status: str,
) -> str:
    """Route eligible no-skill-control stalls into reversible evidence gathering."""

    if selected_action in {"stage_ephemeral_candidate", "stage_canary", "auto_reject"}:
        return selected_action
    if selected_action not in {
        "collect_more_evidence",
        "run_more_probes",
        "run_re_adjudication",
        "no_op_reschedule",
    }:
        return selected_action
    if not _eligible_for_trial_lane(result, scanner_status=scanner_status):
        return selected_action
    return "stage_ephemeral_candidate"


def _eligible_for_trial_lane(result: dict[str, Any], *, scanner_status: str) -> bool:
    if scanner_status != "passed":
        return False
    assurance = _json_dict(result.get("autonomy_assurance"))
    if assurance.get("hard_invariant_failures"):
        return False
    deterministic = _json_dict(_json_dict(result.get("autonomy_fallback")).get(
        "deterministic_checks"
    ))
    if deterministic and deterministic.get("hard_invariants_passed") is False:
        return False
    reason_codes = {str(code) for code in result.get("reason_codes") or []}
    soft_misses = {
        str(code) for code in assurance.get("soft_threshold_misses") or []
    }
    if not ({"intervention-required", "no_skill_control-evidence-insufficient"} & (
        reason_codes | soft_misses
    )):
        return False
    probe_results = [
        probe for probe in result.get("probe_results") or [] if isinstance(probe, dict)
    ]
    if not probe_results:
        return False
    has_no_skill_intervention = False
    for probe in probe_results:
        kind = str(probe.get("kind") or "")
        status = str(probe.get("status") or "")
        if kind == "no_skill_control" and status == "needs_intervention":
            has_no_skill_intervention = True
            continue
        if kind in {"target", "regression", "adversarial"} and status == "passed":
            continue
        return False
    return has_no_skill_intervention


def _reason_codes_for_deadlock(result: dict[str, Any]) -> list[str]:
    assurance = _json_dict(result.get("autonomy_assurance"))
    reason_codes = [
        str(code)
        for code in (
            assurance.get("soft_threshold_misses")
            or result.get("reason_codes")
            or ["intervention-required"]
        )
    ]
    return reason_codes or ["intervention-required"]


def _recommended_deadlock_action(
    result: dict[str, Any],
    *,
    selected_action: str,
) -> str:
    reason_codes = set(_reason_codes_for_deadlock(result))
    fallback_reason_codes = {
        str(code)
        for code in _json_dict(result.get("autonomy_fallback")).get("reason_codes") or []
    }
    all_reason_codes = reason_codes | fallback_reason_codes

    if "token-delta-without-utility-gain" in all_reason_codes:
        return "narrow_scope"
    if {
        "utility-delta-below-threshold",
        "probe-margin-low",
        "probe-failed",
        "llm-json-invalid",
        "autonomous-re-adjudication-required",
    } & all_reason_codes:
        return "generate_more_probes"
    if {
        "auto-reject-with-reason",
        "candidate-utility-negative",
        "repeated-contradictory-adjudications",
    } & all_reason_codes:
        return "reject_cohort"
    if {
        "qualified-autonomous-model-profile-unavailable",
        "llm-adjudication-unavailable",
        "required-infrastructure-unavailable",
    } & all_reason_codes:
        return "no_action"
    if selected_action == "run_re_adjudication":
        return "generate_more_probes"
    if selected_action == "reduce_scope":
        return "narrow_scope"
    if selected_action == "auto_reject":
        return "reject_cohort"
    if selected_action == "stage_canary":
        return "increase_canary_budget"
    return "collect_more_evidence"


async def _finish_evaluation(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    evaluation_id: UUID,
    skill_version_id: UUID,
    executor_profile_id: UUID | None,
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
    if executor_profile_id is not None:
        await _record_executor_compatibility(
            conn,
            workspace_id=workspace_id,
            skill_version_id=skill_version_id,
            executor_profile_id=executor_profile_id,
            evaluation_id=evaluation_id,
            status=status,
            result=result,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
        )


async def _record_executor_compatibility(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    skill_version_id: UUID,
    executor_profile_id: UUID,
    evaluation_id: UUID,
    status: str,
    result: dict[str, Any],
    trace_id: UUID | None,
    span_id: UUID | None,
    parent_span_id: UUID | None,
) -> None:
    compatibility_status = _compatibility_status_for_evaluation(status)
    evidence = {
        "source": "proposal_gate_evaluation",
        "evaluation_id": str(evaluation_id),
        "evaluation_status": status,
        "reason_codes": result.get("reason_codes", []),
        "trace_id": str(trace_id) if trace_id else None,
        "span_id": str(span_id) if span_id else None,
        "parent_span_id": str(parent_span_id) if parent_span_id else None,
    }
    await conn.execute(
        """
        INSERT INTO autoskill.skill_profile_compatibility (
          skill_profile_compatibility_id,
          workspace_id,
          skill_version_id,
          executor_profile_id,
          status,
          evidence
        )
        VALUES (gen_random_uuid(), $1, $2, $3, $4, $5::jsonb)
        ON CONFLICT (workspace_id, skill_version_id, executor_profile_id)
        DO UPDATE SET
          status = EXCLUDED.status,
          evidence = EXCLUDED.evidence,
          last_checked_at = now()
        """,
        workspace_id,
        skill_version_id,
        executor_profile_id,
        compatibility_status,
        _json(evidence),
    )


def _compatibility_status_for_evaluation(status: str) -> str:
    if status == "passed":
        return "compatible"
    if status == "needs_intervention":
        return "degraded"
    return "blocked"


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


def _safe_autonomy_assurance(value: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return {}
    return {
        "decision_family": value.get("decision_family"),
        "policy_version": value.get("policy_version"),
        "hard_invariant_failures": list(value.get("hard_invariant_failures") or []),
        "soft_threshold_misses": list(value.get("soft_threshold_misses") or []),
        "autonomous_fallback_actions": list(
            value.get("autonomous_fallback_actions") or []
        ),
        "threshold_deadlock_candidate": bool(value.get("threshold_deadlock_candidate")),
        "administrative_escalation_allowed": bool(
            value.get("administrative_escalation_allowed")
        ),
        "calibration_support_status": value.get("calibration_support_status"),
        "evidence_mode": value.get("evidence_mode"),
    }


def _safe_autonomy_fallback(value: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return {}
    deterministic_checks = _json_dict(value.get("deterministic_checks"))
    return {
        "schema": value.get("schema"),
        "decision_family": value.get("decision_family"),
        "selected_action": value.get("selected_action"),
        "decision_band": value.get("decision_band"),
        "reason_codes": list(value.get("reason_codes") or []),
        "model_profile_id": value.get("model_profile_id"),
        "llm_invocation_id": value.get("llm_invocation_id"),
        "autonomy_decision_id": value.get("autonomy_decision_id"),
        "adjudication_id": value.get("adjudication_id"),
        "confidence_band": value.get("confidence_band"),
        "evidence_fidelity": value.get("evidence_fidelity"),
        "runtime_writes_authorized": bool(value.get("runtime_writes_authorized")),
        "administrative_escalation_allowed": bool(
            value.get("administrative_escalation_allowed")
        ),
        "deterministic_checks": {
            "schema_valid": bool(deterministic_checks.get("schema_valid")),
            "hard_invariants_passed": bool(
                deterministic_checks.get("hard_invariants_passed")
            ),
            "scanner_override": bool(deterministic_checks.get("scanner_override")),
            "runtime_write_authorized": bool(
                deterministic_checks.get("runtime_write_authorized")
            ),
            "admissible": bool(deterministic_checks.get("admissible")),
        },
    }


def _safe_autonomy_remediation(value: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return {}
    attempts = []
    for attempt in _json_list(value.get("attempts")):
        attempts.append(
            {
                "attempt": attempt.get("attempt"),
                "selected_action": attempt.get("selected_action"),
                "status": attempt.get("status"),
                "attempted_autonomous_remedies": list(
                    attempt.get("attempted_autonomous_remedies") or []
                ),
                "contrastive_replay_count": int(
                    attempt.get("contrastive_replays") or 0
                ),
                "supplemental_probe_hash_count": len(
                    attempt.get("supplemental_probe_hashes") or []
                ),
                "updated_at": attempt.get("updated_at"),
                "trace_id": attempt.get("trace_id"),
                "span_id": attempt.get("span_id"),
                "parent_span_id": attempt.get("parent_span_id"),
            }
        )
    return {
        "schema": value.get("schema"),
        "source": value.get("source"),
        "selected_action": value.get("selected_action"),
        "status": value.get("status"),
        "attempt_count": int(value.get("attempt_count") or 0),
        "attempted_autonomous_remedies": list(
            value.get("attempted_autonomous_remedies") or []
        ),
        "contrastive_replay_count": len(value.get("contrastive_replays") or []),
        "supplemental_probe_hash_count": len(
            value.get("supplemental_probe_hashes") or []
        ),
        "threshold_deadlock_candidate": bool(
            value.get("threshold_deadlock_candidate")
        ),
        "recommended_action": value.get("recommended_action"),
        "attempts": attempts[-10:],
        "updated_at": value.get("updated_at"),
    }


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None


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


def _optional_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _json_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


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
