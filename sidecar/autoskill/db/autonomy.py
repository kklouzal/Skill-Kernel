from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID, uuid4

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class ProposalGateFallbackRecord:
    autonomy_decision_id: UUID
    adjudication_id: UUID
    action: str
    decision_band: str
    confidence_band: str
    evidence_fidelity: str
    reason_codes: list[str]
    evaluation_id: UUID
    skill_version_id: UUID

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": "autoskill.proposal-gate-autonomy-fallback.v1",
            "autonomy_decision_id": str(self.autonomy_decision_id),
            "adjudication_id": str(self.adjudication_id),
            "action": self.action,
            "decision_band": self.decision_band,
            "confidence_band": self.confidence_band,
            "evidence_fidelity": self.evidence_fidelity,
            "reason_codes": self.reason_codes,
            "evaluation_id": str(self.evaluation_id),
            "skill_version_id": str(self.skill_version_id),
        }


class AutonomyControlStore(Protocol):
    async def record_proposal_gate_fallback(
        self,
        *,
        workspace_key: str,
        evaluation_id: UUID,
        skill_version_id: UUID,
        skill_id: UUID | None,
        job_id: UUID | None,
        model_profile_id: UUID | None,
        llm_verdict: dict[str, Any],
        confidence: float,
        deterministic_checks: dict[str, Any],
        action: str,
        decision_band: str,
        confidence_decomposition: dict[str, Any],
        hard_invariants: dict[str, Any],
        soft_thresholds: dict[str, Any],
        reason_codes: list[str],
        evidence_ids: list[UUID],
        result_patch: dict[str, Any],
    ) -> ProposalGateFallbackRecord:
        """Persist an autonomous fallback for a stalled proposal-gate evaluation."""


class NullAutonomyControlStore:
    def __init__(self) -> None:
        self.records: list[ProposalGateFallbackRecord] = []

    async def record_proposal_gate_fallback(
        self,
        *,
        workspace_key: str,
        evaluation_id: UUID,
        skill_version_id: UUID,
        skill_id: UUID | None,
        job_id: UUID | None,
        model_profile_id: UUID | None,
        llm_verdict: dict[str, Any],
        confidence: float,
        deterministic_checks: dict[str, Any],
        action: str,
        decision_band: str,
        confidence_decomposition: dict[str, Any],
        hard_invariants: dict[str, Any],
        soft_thresholds: dict[str, Any],
        reason_codes: list[str],
        evidence_ids: list[UUID],
        result_patch: dict[str, Any],
    ) -> ProposalGateFallbackRecord:
        record = ProposalGateFallbackRecord(
            autonomy_decision_id=uuid4(),
            adjudication_id=uuid4(),
            action=action,
            decision_band=decision_band,
            confidence_band=_confidence_band(confidence),
            evidence_fidelity=str(
                llm_verdict.get("evidence_fidelity")
                or result_patch.get("evidence_fidelity")
                or "redacted_derivative"
            ),
            reason_codes=list(reason_codes),
            evaluation_id=evaluation_id,
            skill_version_id=skill_version_id,
        )
        self.records.append(record)
        return record


class AsyncpgAutonomyControlStore(AsyncpgPoolOwner):
    async def record_proposal_gate_fallback(
        self,
        *,
        workspace_key: str,
        evaluation_id: UUID,
        skill_version_id: UUID,
        skill_id: UUID | None,
        job_id: UUID | None,
        model_profile_id: UUID | None,
        llm_verdict: dict[str, Any],
        confidence: float,
        deterministic_checks: dict[str, Any],
        action: str,
        decision_band: str,
        confidence_decomposition: dict[str, Any],
        hard_invariants: dict[str, Any],
        soft_thresholds: dict[str, Any],
        reason_codes: list[str],
        evidence_ids: list[UUID],
        result_patch: dict[str, Any],
    ) -> ProposalGateFallbackRecord:
        autonomy_decision_id = uuid4()
        adjudication_id = uuid4()
        confidence = _bounded_confidence(confidence)
        confidence_band = _confidence_band(confidence)
        evidence_fidelity = str(
            llm_verdict.get("evidence_fidelity")
            or result_patch.get("evidence_fidelity")
            or "redacted_derivative"
        )
        dominant_reason_code = reason_codes[0] if reason_codes else None
        verifier_state = "passed" if deterministic_checks.get("admissible") else "blocked"
        schema_status = "valid" if deterministic_checks.get("schema_valid") else "invalid"
        hard_invariant_state = (
            "passed" if not hard_invariants.get("failures") else "blocked"
        )
        soft_threshold_state = (
            "fallback_selected"
            if action not in {"no_op_reschedule", "collect_more_evidence"}
            else "fallback_needs_more_evidence"
        )
        autonomy_support_state = (
            "llm_adjudicated" if model_profile_id is not None else "llm_unavailable"
        )
        persisted_result_patch = {
            **result_patch,
            "autonomy_decision_id": str(autonomy_decision_id),
            "adjudication_id": str(adjudication_id),
        }

        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            await conn.execute(
                """
                INSERT INTO autoskill.autonomous_adjudications (
                  adjudication_id,
                  workspace_id,
                  job_id,
                  adjudication_kind,
                  input_evidence_ids,
                  model_profile_id,
                  llm_verdict,
                  confidence,
                  deterministic_checks,
                  decision,
                  escalation_reason
                )
                VALUES (
                  $1, $2, $3, 'skill_plan_semantic_adjudication',
                  $4::uuid[], $5, $6::jsonb, $7, $8::jsonb, $9, NULL
                )
                """,
                adjudication_id,
                workspace_id,
                job_id,
                evidence_ids,
                model_profile_id,
                _json(llm_verdict),
                confidence,
                _json(deterministic_checks),
                action,
            )
            await conn.execute(
                """
                INSERT INTO autoskill.autonomy_decisions (
                  autonomy_decision_id,
                  workspace_id,
                  job_id,
                  skill_id,
                  operation_kind,
                  llm_adjudication_ids,
                  hard_invariants,
                  soft_thresholds,
                  confidence_decomposition,
                  decision_band,
                  action,
                  reason_codes
                )
                VALUES (
                  $1, $2, $3, $4, 'proposal_gate_fallback', ARRAY[$5]::uuid[],
                  $6::jsonb, $7::jsonb, $8::jsonb, $9, $10, $11::text[]
                )
                """,
                autonomy_decision_id,
                workspace_id,
                job_id,
                skill_id,
                adjudication_id,
                _json(hard_invariants),
                _json(soft_thresholds),
                _json(confidence_decomposition),
                decision_band,
                action,
                reason_codes,
            )
            await conn.execute(
                """
                INSERT INTO autoskill.admin_semantic_adjudication_status (
                  adjudication_run_id,
                  workspace_key,
                  decision_family,
                  model_profile_id,
                  schema_status,
                  confidence_band,
                  evidence_fidelity,
                  verifier_state,
                  raw_vault_exposure_class,
                  dominant_reason_code,
                  completed_at
                )
                VALUES (
                  $1, $2, 'skill_plan_semantic_adjudication', $3, $4, $5,
                  $6, $7, 'none', $8, now()
                )
                ON CONFLICT (adjudication_run_id) DO UPDATE
                SET schema_status = EXCLUDED.schema_status,
                    confidence_band = EXCLUDED.confidence_band,
                    evidence_fidelity = EXCLUDED.evidence_fidelity,
                    verifier_state = EXCLUDED.verifier_state,
                    dominant_reason_code = EXCLUDED.dominant_reason_code,
                    completed_at = EXCLUDED.completed_at
                """,
                adjudication_id,
                workspace_key,
                model_profile_id,
                schema_status,
                confidence_band,
                evidence_fidelity,
                verifier_state,
                dominant_reason_code,
            )
            await conn.execute(
                """
                INSERT INTO autoskill.admin_autonomy_decision_status (
                  decision_id,
                  workspace_key,
                  decision_family,
                  target_kind,
                  target_id,
                  action_risk_tier,
                  hard_invariant_state,
                  soft_threshold_state,
                  selected_action,
                  confidence_band,
                  evidence_fidelity,
                  autonomy_support_state,
                  dominant_reason_code
                )
                VALUES (
                  $1, $2, 'skill_plan_semantic_adjudication',
                  'skill_version', $3, $4, $5, $6, $7, $8, $9, $10, $11
                )
                ON CONFLICT (decision_id) DO UPDATE
                SET hard_invariant_state = EXCLUDED.hard_invariant_state,
                    soft_threshold_state = EXCLUDED.soft_threshold_state,
                    selected_action = EXCLUDED.selected_action,
                    confidence_band = EXCLUDED.confidence_band,
                    evidence_fidelity = EXCLUDED.evidence_fidelity,
                    autonomy_support_state = EXCLUDED.autonomy_support_state,
                    dominant_reason_code = EXCLUDED.dominant_reason_code,
                    updated_at = now()
                """,
                autonomy_decision_id,
                workspace_key,
                str(skill_version_id),
                _action_risk_tier(action),
                hard_invariant_state,
                soft_threshold_state,
                action,
                confidence_band,
                evidence_fidelity,
                autonomy_support_state,
                dominant_reason_code,
            )
            await conn.execute(
                """
                UPDATE autoskill.evaluations
                SET result = result || jsonb_build_object('autonomy_fallback', $2::jsonb)
                WHERE evaluation_id = $1
                """,
                evaluation_id,
                _json(persisted_result_patch),
            )

        return ProposalGateFallbackRecord(
            autonomy_decision_id=autonomy_decision_id,
            adjudication_id=adjudication_id,
            action=action,
            decision_band=decision_band,
            confidence_band=confidence_band,
            evidence_fidelity=evidence_fidelity,
            reason_codes=list(reason_codes),
            evaluation_id=evaluation_id,
            skill_version_id=skill_version_id,
        )


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _bounded_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _confidence_band(value: float) -> str:
    confidence = _bounded_confidence(value)
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.55:
        return "medium"
    return "low"


def _action_risk_tier(action: str) -> str:
    if action in {"stage_ephemeral_candidate", "stage_canary"}:
        return "T2_trial_artifact"
    if action in {"auto_accept", "rollback"}:
        return "T3_owned_runtime_change"
    if action == "escalate_admin":
        return "T4_external_or_irreversible"
    return "T1_internal_record"
