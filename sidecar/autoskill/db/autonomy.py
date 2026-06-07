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


@dataclass(frozen=True)
class AdministrativeEscalationRecord:
    escalation_event_id: UUID
    escalation_kind: str
    decision_family: str
    target_kind: str
    target_id: str
    dominant_reason_code: str
    attempted_autonomous_alternatives: list[dict[str, Any]]
    recommended_admin_action: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": "autoskill.administrative-escalation.v1",
            "escalation_event_id": str(self.escalation_event_id),
            "escalation_kind": self.escalation_kind,
            "decision_family": self.decision_family,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "dominant_reason_code": self.dominant_reason_code,
            "attempted_autonomous_alternatives": self.attempted_autonomous_alternatives,
            "recommended_admin_action": self.recommended_admin_action,
        }


@dataclass(frozen=True)
class AutonomyCalibrationObservationRecord:
    calibration_observation_id: UUID
    calibration_family: str
    autonomy_decision_id: UUID | None
    adjudication_id: UUID | None
    action_risk_tier: str
    predicted_confidence: float
    selected_action: str
    outcome_status: str

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": "autoskill.autonomy-calibration-observation.v1",
            "calibration_observation_id": str(self.calibration_observation_id),
            "calibration_family": self.calibration_family,
            "autonomy_decision_id": (
                str(self.autonomy_decision_id) if self.autonomy_decision_id else None
            ),
            "adjudication_id": str(self.adjudication_id) if self.adjudication_id else None,
            "action_risk_tier": self.action_risk_tier,
            "predicted_confidence": self.predicted_confidence,
            "selected_action": self.selected_action,
            "outcome_status": self.outcome_status,
        }


@dataclass(frozen=True)
class AutonomyReliabilityMetricRecord:
    reliability_metric_id: UUID
    calibration_family: str
    sample_count: int
    coverage_rate: float
    false_accept_rate: float | None
    false_reject_rate: float | None
    abstention_rate: float
    unnecessary_abstention_rate: float | None
    calibration_support: str

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": "autoskill.autonomy-reliability-metric.v1",
            "reliability_metric_id": str(self.reliability_metric_id),
            "calibration_family": self.calibration_family,
            "sample_count": self.sample_count,
            "coverage_rate": self.coverage_rate,
            "false_accept_rate": self.false_accept_rate,
            "false_reject_rate": self.false_reject_rate,
            "abstention_rate": self.abstention_rate,
            "unnecessary_abstention_rate": self.unnecessary_abstention_rate,
            "calibration_support": self.calibration_support,
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

    async def record_administrative_escalation(
        self,
        *,
        workspace_key: str,
        escalation_kind: str,
        decision_family: str,
        target_kind: str,
        target_id: str,
        dominant_reason_code: str,
        attempted_autonomous_alternatives: list[dict[str, Any]],
        recommended_admin_action: str | None = None,
        autonomy_decision_id: UUID | None = None,
        adjudication_id: UUID | None = None,
        evidence_packet_id: UUID | None = None,
        source_fidelity: str | None = None,
        hard_invariants: dict[str, Any] | None = None,
    ) -> AdministrativeEscalationRecord:
        """Persist a hard-boundary administrative escalation and read-model row."""

    async def record_calibration_outcome(
        self,
        *,
        workspace_key: str,
        autonomy_decision_id: UUID,
        outcome_status: str,
        outcome: dict[str, Any] | None = None,
        false_accept: bool | None = None,
        false_reject: bool | None = None,
        unnecessary_abstention: bool | None = None,
        harm_finding: bool | None = None,
        utility_score: float | None = None,
        context_token_delta: int | None = None,
    ) -> AutonomyCalibrationObservationRecord | None:
        """Attach a delayed outcome to a persisted semantic calibration observation."""


class NullAutonomyControlStore:
    def __init__(self) -> None:
        self.records: list[ProposalGateFallbackRecord] = []
        self.escalations: list[AdministrativeEscalationRecord] = []
        self.calibration_observations: list[AutonomyCalibrationObservationRecord] = []
        self.reliability_metrics: list[AutonomyReliabilityMetricRecord] = []

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
        self._record_pending_calibration(
            autonomy_decision_id=record.autonomy_decision_id,
            adjudication_id=record.adjudication_id,
            action=action,
            confidence=confidence,
        )
        return record

    async def record_administrative_escalation(
        self,
        *,
        workspace_key: str,
        escalation_kind: str,
        decision_family: str,
        target_kind: str,
        target_id: str,
        dominant_reason_code: str,
        attempted_autonomous_alternatives: list[dict[str, Any]],
        recommended_admin_action: str | None = None,
        autonomy_decision_id: UUID | None = None,
        adjudication_id: UUID | None = None,
        evidence_packet_id: UUID | None = None,
        source_fidelity: str | None = None,
        hard_invariants: dict[str, Any] | None = None,
    ) -> AdministrativeEscalationRecord:
        record = AdministrativeEscalationRecord(
            escalation_event_id=uuid4(),
            escalation_kind=escalation_kind,
            decision_family=decision_family,
            target_kind=target_kind,
            target_id=target_id,
            dominant_reason_code=dominant_reason_code,
            attempted_autonomous_alternatives=list(attempted_autonomous_alternatives),
            recommended_admin_action=recommended_admin_action,
        )
        self.escalations.append(record)
        return record

    async def record_calibration_outcome(
        self,
        *,
        workspace_key: str,
        autonomy_decision_id: UUID,
        outcome_status: str,
        outcome: dict[str, Any] | None = None,
        false_accept: bool | None = None,
        false_reject: bool | None = None,
        unnecessary_abstention: bool | None = None,
        harm_finding: bool | None = None,
        utility_score: float | None = None,
        context_token_delta: int | None = None,
    ) -> AutonomyCalibrationObservationRecord | None:
        for index, record in enumerate(self.calibration_observations):
            if record.autonomy_decision_id == autonomy_decision_id:
                updated = AutonomyCalibrationObservationRecord(
                    calibration_observation_id=record.calibration_observation_id,
                    calibration_family=record.calibration_family,
                    autonomy_decision_id=record.autonomy_decision_id,
                    adjudication_id=record.adjudication_id,
                    action_risk_tier=record.action_risk_tier,
                    predicted_confidence=record.predicted_confidence,
                    selected_action=record.selected_action,
                    outcome_status=_outcome_status(outcome_status),
                )
                self.calibration_observations[index] = updated
                self._refresh_reliability_metrics(record.calibration_family)
                return updated
        return None

    def _record_pending_calibration(
        self,
        *,
        autonomy_decision_id: UUID,
        adjudication_id: UUID,
        action: str,
        confidence: float,
    ) -> None:
        self.calibration_observations.append(
            AutonomyCalibrationObservationRecord(
                calibration_observation_id=uuid4(),
                calibration_family="skill_plan_semantic_adjudication",
                autonomy_decision_id=autonomy_decision_id,
                adjudication_id=adjudication_id,
                action_risk_tier=_action_risk_tier(action),
                predicted_confidence=_bounded_confidence(confidence),
                selected_action=action,
                outcome_status="pending",
            )
        )
        self._refresh_reliability_metrics("skill_plan_semantic_adjudication")

    def _refresh_reliability_metrics(self, calibration_family: str) -> None:
        records = [
            record
            for record in self.calibration_observations
            if record.calibration_family == calibration_family
        ]
        if not records:
            return
        observed = [
            record
            for record in records
            if record.outcome_status not in {"pending", "unknown"}
        ]
        abstentions = [
            record
            for record in records
            if record.selected_action
            in {
                "collect_more_evidence",
                "run_more_probes",
                "run_re_adjudication",
                "reduce_scope",
                "no_op_reschedule",
            }
        ]
        self.reliability_metrics.append(
            AutonomyReliabilityMetricRecord(
                reliability_metric_id=uuid4(),
                calibration_family=calibration_family,
                sample_count=len(records),
                coverage_rate=len(observed) / len(records),
                false_accept_rate=None,
                false_reject_rate=None,
                abstention_rate=len(abstentions) / len(records),
                unnecessary_abstention_rate=None,
                calibration_support=(
                    "empirical_supported"
                    if len(observed) >= 30
                    else "empirical_low_support"
                ),
            )
        )


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
            await self._record_pending_calibration(
                conn,
                workspace_id=workspace_id,
                calibration_family="skill_plan_semantic_adjudication",
                autonomy_decision_id=autonomy_decision_id,
                adjudication_id=adjudication_id,
                model_profile_id=model_profile_id,
                action=action,
                confidence=confidence,
                confidence_decomposition=confidence_decomposition,
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

    async def record_administrative_escalation(
        self,
        *,
        workspace_key: str,
        escalation_kind: str,
        decision_family: str,
        target_kind: str,
        target_id: str,
        dominant_reason_code: str,
        attempted_autonomous_alternatives: list[dict[str, Any]],
        recommended_admin_action: str | None = None,
        autonomy_decision_id: UUID | None = None,
        adjudication_id: UUID | None = None,
        evidence_packet_id: UUID | None = None,
        source_fidelity: str | None = None,
        hard_invariants: dict[str, Any] | None = None,
    ) -> AdministrativeEscalationRecord:
        escalation_event_id = uuid4()
        attempted_actions = [
            str(item.get("action"))
            for item in attempted_autonomous_alternatives
            if isinstance(item, dict) and str(item.get("action") or "").strip()
        ]
        if not attempted_actions:
            attempted_actions = ["record_policy_block"]
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            await conn.execute(
                """
                INSERT INTO autoskill.administrative_escalation_events (
                  escalation_event_id,
                  workspace_id,
                  autonomy_decision_id,
                  adjudication_id,
                  escalation_kind,
                  evidence_packet_id,
                  decision_family,
                  source_fidelity,
                  hard_invariants,
                  attempted_autonomous_alternatives,
                  recommended_admin_action,
                  status
                )
                VALUES (
                  $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb,
                  $10::text[], $11, 'open'
                )
                """,
                escalation_event_id,
                workspace_id,
                autonomy_decision_id,
                adjudication_id,
                escalation_kind,
                evidence_packet_id,
                decision_family,
                source_fidelity,
                _json(hard_invariants or {}),
                attempted_actions,
                recommended_admin_action,
            )
            await conn.execute(
                """
                INSERT INTO autoskill.admin_administrative_escalation_status (
                  event_id,
                  workspace_key,
                  hard_boundary_kind,
                  decision_family,
                  target_kind,
                  target_id,
                  attempted_autonomous_alternatives,
                  resolution_state,
                  dominant_reason_code
                )
                VALUES (
                  $1, $2, $3, $4, $5, $6, $7::jsonb, 'open', $8
                )
                ON CONFLICT (event_id) DO UPDATE
                SET hard_boundary_kind = EXCLUDED.hard_boundary_kind,
                    decision_family = EXCLUDED.decision_family,
                    target_kind = EXCLUDED.target_kind,
                    target_id = EXCLUDED.target_id,
                    attempted_autonomous_alternatives = EXCLUDED.attempted_autonomous_alternatives,
                    resolution_state = EXCLUDED.resolution_state,
                    dominant_reason_code = EXCLUDED.dominant_reason_code
                """,
                escalation_event_id,
                workspace_key,
                escalation_kind,
                decision_family,
                target_kind,
                target_id,
                _json(attempted_autonomous_alternatives),
                dominant_reason_code,
            )
        return AdministrativeEscalationRecord(
            escalation_event_id=escalation_event_id,
            escalation_kind=escalation_kind,
            decision_family=decision_family,
            target_kind=target_kind,
            target_id=target_id,
            dominant_reason_code=dominant_reason_code,
            attempted_autonomous_alternatives=list(attempted_autonomous_alternatives),
            recommended_admin_action=recommended_admin_action,
        )

    async def record_calibration_outcome(
        self,
        *,
        workspace_key: str,
        autonomy_decision_id: UUID,
        outcome_status: str,
        outcome: dict[str, Any] | None = None,
        false_accept: bool | None = None,
        false_reject: bool | None = None,
        unnecessary_abstention: bool | None = None,
        harm_finding: bool | None = None,
        utility_score: float | None = None,
        context_token_delta: int | None = None,
    ) -> AutonomyCalibrationObservationRecord | None:
        bounded_outcome_status = _outcome_status(outcome_status)
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                UPDATE autoskill.autonomy_calibration_observations
                SET outcome_status = $3,
                    outcome_observed_at = now(),
                    outcome = $4::jsonb,
                    false_accept = $5,
                    false_reject = $6,
                    unnecessary_abstention = $7,
                    harm_finding = $8,
                    utility_score = $9,
                    context_token_delta = $10
                WHERE workspace_id = $1
                  AND autonomy_decision_id = $2
                RETURNING
                  calibration_observation_id,
                  calibration_family,
                  autonomy_decision_id,
                  adjudication_id,
                  action_risk_tier,
                  predicted_confidence,
                  selected_action,
                  outcome_status
                """,
                workspace_id,
                autonomy_decision_id,
                bounded_outcome_status,
                _json(outcome or {}),
                false_accept,
                false_reject,
                unnecessary_abstention,
                harm_finding,
                utility_score,
                context_token_delta,
            )
            if row is None:
                return None
            await self._refresh_reliability_metrics(
                conn,
                workspace_id=workspace_id,
                calibration_family=row["calibration_family"],
            )
        return AutonomyCalibrationObservationRecord(
            calibration_observation_id=row["calibration_observation_id"],
            calibration_family=row["calibration_family"],
            autonomy_decision_id=row["autonomy_decision_id"],
            adjudication_id=row["adjudication_id"],
            action_risk_tier=row["action_risk_tier"],
            predicted_confidence=float(row["predicted_confidence"]),
            selected_action=row["selected_action"],
            outcome_status=row["outcome_status"],
        )

    async def _record_pending_calibration(
        self,
        conn: Any,
        *,
        workspace_id: UUID,
        calibration_family: str,
        autonomy_decision_id: UUID,
        adjudication_id: UUID,
        model_profile_id: UUID | None,
        action: str,
        confidence: float,
        confidence_decomposition: dict[str, Any],
    ) -> None:
        await conn.execute(
            """
            INSERT INTO autoskill.autonomy_calibration_observations (
              calibration_observation_id,
              workspace_id,
              calibration_family,
              model_profile_id,
              adjudication_id,
              autonomy_decision_id,
              action_risk_tier,
              predicted_confidence,
              confidence_components,
              selected_action,
              outcome_status
            )
            VALUES (
              $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, 'pending'
            )
            """,
            uuid4(),
            workspace_id,
            calibration_family,
            model_profile_id,
            adjudication_id,
            autonomy_decision_id,
            _action_risk_tier(action),
            _bounded_confidence(confidence),
            _json(confidence_decomposition),
            action,
        )
        await self._refresh_reliability_metrics(
            conn,
            workspace_id=workspace_id,
            calibration_family=calibration_family,
        )

    async def _refresh_reliability_metrics(
        self,
        conn: Any,
        *,
        workspace_id: UUID,
        calibration_family: str,
    ) -> None:
        await conn.execute(
            """
            WITH observations AS (
              SELECT *
              FROM autoskill.autonomy_calibration_observations
              WHERE workspace_id = $2
                AND calibration_family = $3
                AND created_at >= now() - interval '30 days'
            ),
            aggregates AS (
              SELECT
                count(*)::integer AS sample_count,
                min(created_at) AS window_start,
                now() AS window_end,
                avg(
                  CASE
                    WHEN outcome_status NOT IN ('pending', 'unknown') THEN 1.0
                    ELSE 0.0
                  END
                ) AS coverage_rate,
                avg(CASE WHEN false_accept IS NULL THEN NULL WHEN false_accept THEN 1.0 ELSE 0.0 END) AS false_accept_rate,
                avg(CASE WHEN false_reject IS NULL THEN NULL WHEN false_reject THEN 1.0 ELSE 0.0 END) AS false_reject_rate,
                avg(
                  CASE
                    WHEN selected_action IN (
                      'collect_more_evidence',
                      'run_more_probes',
                      'run_re_adjudication',
                      'reduce_scope',
                      'no_op_reschedule'
                    ) THEN 1.0
                    ELSE 0.0
                  END
                ) AS abstention_rate,
                avg(
                  CASE
                    WHEN unnecessary_abstention IS NULL THEN NULL
                    WHEN unnecessary_abstention THEN 1.0
                    ELSE 0.0
                  END
                ) AS unnecessary_abstention_rate,
                avg(
                  CASE
                    WHEN outcome_status = 'success' THEN abs(predicted_confidence - 1.0)
                    WHEN outcome_status = 'failure' THEN abs(predicted_confidence - 0.0)
                    ELSE NULL
                  END
                ) AS calibration_error,
                avg(
                  CASE
                    WHEN outcome_status = 'success' THEN power(predicted_confidence - 1.0, 2)
                    WHEN outcome_status = 'failure' THEN power(predicted_confidence - 0.0, 2)
                    ELSE NULL
                  END
                ) AS brier_like_score,
                avg(CASE WHEN harm_finding IS NULL THEN NULL WHEN harm_finding THEN 1.0 ELSE 0.0 END) AS harm_finding_rate,
                sum(utility_score) / NULLIF(sum(abs(context_token_delta)), 0) AS utility_per_context_token,
                jsonb_build_array(
                  jsonb_build_object(
                    'confidence_min', 0.0,
                    'confidence_max', 0.5,
                    'sample_count', count(*) FILTER (WHERE predicted_confidence < 0.5)
                  ),
                  jsonb_build_object(
                    'confidence_min', 0.5,
                    'confidence_max', 0.85,
                    'sample_count', count(*) FILTER (WHERE predicted_confidence >= 0.5 AND predicted_confidence < 0.85)
                  ),
                  jsonb_build_object(
                    'confidence_min', 0.85,
                    'confidence_max', 1.0,
                    'sample_count', count(*) FILTER (WHERE predicted_confidence >= 0.85)
                  )
                ) AS reliability_bins
              FROM observations
            )
            INSERT INTO autoskill.autonomy_reliability_metrics (
              reliability_metric_id,
              workspace_id,
              calibration_family,
              window_start,
              window_end,
              sample_count,
              coverage_rate,
              false_accept_rate,
              false_reject_rate,
              abstention_rate,
              unnecessary_abstention_rate,
              calibration_error,
              brier_like_score,
              harm_finding_rate,
              utility_per_context_token,
              reliability_bins,
              calibration_support
            )
            SELECT
              $1, $2, $3,
              coalesce(window_start, now()),
              window_end,
              sample_count,
              coverage_rate,
              false_accept_rate,
              false_reject_rate,
              abstention_rate,
              unnecessary_abstention_rate,
              calibration_error,
              brier_like_score,
              harm_finding_rate,
              utility_per_context_token,
              reliability_bins,
              CASE
                WHEN sample_count = 0 THEN 'none'
                WHEN sample_count < 30 OR coverage_rate < 0.5 THEN 'empirical_low_support'
                ELSE 'empirical_supported'
              END
            FROM aggregates
            WHERE sample_count > 0
            """,
            uuid4(),
            workspace_id,
            calibration_family,
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


def _outcome_status(value: str) -> str:
    status = str(value).strip().lower()
    allowed = {"pending", "success", "failure", "mixed", "unknown", "revoked"}
    if status not in allowed:
        return "unknown"
    return status
