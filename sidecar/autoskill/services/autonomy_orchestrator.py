from __future__ import annotations

import json
from dataclasses import replace
from typing import Any
from uuid import UUID

from autoskill.db.autonomy import AutonomyControlStore, AutonomyReliabilityMetricRecord
from autoskill.db.evaluations import EvaluationRunItem, EvaluationRunResult
from autoskill.db.profiles import ModelProfileRecord, ProfileStore
from autoskill.services.llm import LLMClient, LLMCompletionRequest, LLMMessage

DECISION_FAMILY = "skill_plan_semantic_adjudication"

NEEDS_INTERVENTION_ACTIONS = {
    "auto_accept",
    "collect_more_evidence",
    "run_more_probes",
    "run_re_adjudication",
    "stage_ephemeral_candidate",
    "stage_canary",
    "reduce_scope",
    "auto_reject",
    "no_op_reschedule",
}

ACTION_ALIASES = {
    "generate_more_probes": "run_more_probes",
    "run_additional_retrieval": "collect_more_evidence",
    "assemble_richer_permitted_evidence": "collect_more_evidence",
    "use_raw_vault_context_if_policy_allows": "collect_more_evidence",
    "canary_with_smaller_exposure": "stage_canary",
    "canary_only": "stage_canary",
    "build_ephemeral_candidate": "stage_ephemeral_candidate",
    "compile_more_conservatively": "reduce_scope",
    "create_ephemeral_candidate": "stage_ephemeral_candidate",
    "decompose_candidate": "reduce_scope",
    "ephemeral_candidate": "stage_ephemeral_candidate",
    "try_ephemeral_candidate": "stage_ephemeral_candidate",
    "auto_reject_with_reason": "auto_reject",
    "re_adjudicate": "run_re_adjudication",
    "run_llm_re_adjudication": "run_re_adjudication",
    "run_independent_verifier_adjudication": "run_re_adjudication",
    "run_verifier_adjudication": "run_re_adjudication",
    "run_counterfactual_trial": "run_more_probes",
    "record_pending_candidate": "no_op_reschedule",
    "no_op_with_reschedule": "no_op_reschedule",
    "no_skill": "no_op_reschedule",
}

ADJUDICATION_PROMPT_ACTIONS = frozenset(NEEDS_INTERVENTION_ACTIONS) | frozenset(
    ACTION_ALIASES
)


class ProposalGateAutonomyOrchestrator:
    def __init__(
        self,
        *,
        profiles: ProfileStore,
        llm: LLMClient,
        autonomy: AutonomyControlStore,
        profile_key: str | None = None,
    ) -> None:
        self.profiles = profiles
        self.llm = llm
        self.autonomy = autonomy
        self.profile_key = profile_key

    async def resolve_run(
        self,
        result: EvaluationRunResult,
        *,
        workspace_key: str | None,
        job_id: UUID | None = None,
    ) -> EvaluationRunResult:
        updated: list[EvaluationRunItem] = []
        for item in result.evaluations:
            if item.status != "needs_intervention":
                updated.append(item)
                continue
            updated.append(
                await self.resolve_item(
                    item,
                    workspace_key=workspace_key
                    or _string(item.result.get("workspace_key"))
                    or "unknown",
                    job_id=job_id,
                )
            )
        if updated == result.evaluations:
            return result
        return replace(result, evaluations=updated)

    async def resolve_item(
        self,
        item: EvaluationRunItem,
        *,
        workspace_key: str,
        job_id: UUID | None = None,
    ) -> EvaluationRunItem:
        assurance = _dict(item.result.get("autonomy_assurance"))
        hard_failures = [str(code) for code in assurance.get("hard_invariant_failures") or []]
        reason_codes = [str(code) for code in item.result.get("reason_codes") or []]
        if hard_failures:
            return item

        calibration_metric = await self.autonomy.get_latest_reliability_metric(
            workspace_key=workspace_key,
            calibration_family=DECISION_FAMILY,
        )
        profile = await _select_qualified_autonomous_profile(
            self.profiles,
            workspace_key=workspace_key,
            preferred_profile_key=self.profile_key,
        )
        if profile is None:
            return await self._record_without_llm(
                item,
                workspace_key=workspace_key,
                job_id=job_id,
                calibration_metric=calibration_metric,
                reason_codes=[
                    *reason_codes,
                    "qualified-autonomous-model-profile-unavailable",
                ],
            )

        try:
            verdict = await self._run_llm_adjudication(
                item,
                workspace_key=workspace_key,
                profile=profile,
                calibration_metric=calibration_metric,
            )
        except Exception as exc:
            return await self._record_without_llm(
                item,
                workspace_key=workspace_key,
                job_id=job_id,
                calibration_metric=calibration_metric,
                reason_codes=[
                    *reason_codes,
                    "llm-adjudication-unavailable",
                ],
                error=f"{type(exc).__name__}: {exc}"[:300],
            )

        normalized = _normalize_verdict(verdict)
        confidence = _confidence(normalized)
        action = _admissible_action(normalized, confidence=confidence)
        decision_band = _decision_band(action)
        fallback = _fallback_patch(
            action=action,
            decision_band=decision_band,
            reason_codes=reason_codes,
            llm_verdict=normalized,
            confidence=confidence,
            model_profile_id=profile.profile_id,
            invocation_id=_string(normalized.get("llm_invocation_id")),
            deterministic_checks={
                "schema_valid": True,
                "hard_invariants_passed": True,
                "scanner_override": False,
                "runtime_write_authorized": False,
                "admissible": True,
            },
            evidence_ids=[str(item_id) for item_id in _evidence_ids(item.result)],
            calibration_metric=calibration_metric,
        )
        record = await self.autonomy.record_proposal_gate_fallback(
            workspace_key=workspace_key,
            evaluation_id=item.evaluation_id,
            skill_version_id=item.skill_version_id,
            skill_id=_optional_uuid(item.result.get("skill_id")),
            job_id=job_id,
            model_profile_id=profile.profile_id,
            llm_verdict=normalized,
            confidence=confidence,
            deterministic_checks=fallback["deterministic_checks"],
            action=action,
            decision_band=decision_band,
            confidence_decomposition=_dict(normalized.get("confidence_decomposition")),
            hard_invariants={"failures": []},
            soft_thresholds={
                "misses": list(assurance.get("soft_threshold_misses") or []),
                "fallback_actions": list(assurance.get("autonomous_fallback_actions") or []),
            },
            reason_codes=fallback["reason_codes"],
            evidence_ids=_evidence_ids(item.result),
            result_patch=fallback,
        )
        return replace(
            item,
            result={
                **item.result,
                "autonomy_fallback": {
                    **fallback,
                    "autonomy_decision_id": str(record.autonomy_decision_id),
                    "adjudication_id": str(record.adjudication_id),
                },
            },
        )

    async def _run_llm_adjudication(
        self,
        item: EvaluationRunItem,
        *,
        workspace_key: str,
        profile: ModelProfileRecord,
        calibration_metric: AutonomyReliabilityMetricRecord | None,
    ) -> dict[str, Any]:
        completion = await self.llm.complete(
            _adjudication_request(
                workspace_key=workspace_key,
                profile_key=profile.profile_key,
                item=item,
                purpose="proposal_gate.needs_intervention_adjudication",
                calibration_metric=calibration_metric,
            )
        )
        try:
            parsed = _parse_json_object(completion.text)
        except json.JSONDecodeError as first_error:
            retry = await self.llm.complete(
                _adjudication_request(
                    workspace_key=workspace_key,
                    profile_key=profile.profile_key,
                    item=item,
                    purpose="proposal_gate.needs_intervention_adjudication.retry",
                    calibration_metric=calibration_metric,
                    retry_error=f"{type(first_error).__name__}: {first_error}"[:200],
                )
            )
            try:
                parsed = _parse_json_object(retry.text)
            except json.JSONDecodeError as retry_error:
                return {
                    "action": "run_re_adjudication",
                    "confidence": 0.25,
                    "confidence_decomposition": {
                        "model_confidence": 0.25,
                        "evidence_coverage": 0.0,
                        "source_fidelity": 0.0,
                        "scanner_risk": 0.0,
                    },
                    "evidence_fidelity": "redacted_derivative",
                    "reason_codes": [
                        "llm-json-invalid",
                        "autonomous-re-adjudication-required",
                    ],
                    "uncertainty_notes": [
                        "LLM response was not valid JSON after autonomous retry."
                    ],
                    "schema_status": "invalid",
                    "error": f"{type(retry_error).__name__}: {retry_error}"[:300],
                    "llm_invocation_id": str(retry.invocation.llm_invocation_id),
                    "model_profile_id": str(profile.profile_id),
                    "profile_key": profile.profile_key,
                }
            completion = retry
        return {
            **parsed,
            "llm_invocation_id": str(completion.invocation.llm_invocation_id),
            "model_profile_id": str(profile.profile_id),
            "profile_key": profile.profile_key,
        }

    async def _record_without_llm(
        self,
        item: EvaluationRunItem,
        *,
        workspace_key: str,
        job_id: UUID | None,
        calibration_metric: AutonomyReliabilityMetricRecord | None,
        reason_codes: list[str],
        error: str | None = None,
    ) -> EvaluationRunItem:
        fallback = _fallback_patch(
            action="no_op_reschedule",
            decision_band="improve_evidence",
            reason_codes=reason_codes,
            llm_verdict={
                "schema_status": "not_run",
                "evidence_fidelity": "redacted_derivative",
                "reason_codes": reason_codes,
                **({"error": error} if error else {}),
            },
            confidence=0.0,
            model_profile_id=None,
            invocation_id=None,
            deterministic_checks={
                "schema_valid": False,
                "hard_invariants_passed": True,
                "scanner_override": False,
                "runtime_write_authorized": False,
                "admissible": True,
            },
            evidence_ids=[str(item_id) for item_id in _evidence_ids(item.result)],
            calibration_metric=calibration_metric,
        )
        assurance = _dict(item.result.get("autonomy_assurance"))
        record = await self.autonomy.record_proposal_gate_fallback(
            workspace_key=workspace_key,
            evaluation_id=item.evaluation_id,
            skill_version_id=item.skill_version_id,
            skill_id=_optional_uuid(item.result.get("skill_id")),
            job_id=job_id,
            model_profile_id=None,
            llm_verdict=fallback["llm_verdict"],
            confidence=0.0,
            deterministic_checks=fallback["deterministic_checks"],
            action="no_op_reschedule",
            decision_band="improve_evidence",
            confidence_decomposition=fallback["confidence_decomposition"],
            hard_invariants={"failures": []},
            soft_thresholds={
                "misses": list(assurance.get("soft_threshold_misses") or []),
                "fallback_actions": list(assurance.get("autonomous_fallback_actions") or []),
            },
            reason_codes=fallback["reason_codes"],
            evidence_ids=_evidence_ids(item.result),
            result_patch=fallback,
        )
        return replace(
            item,
            result={
                **item.result,
                "autonomy_fallback": {
                    **fallback,
                    "autonomy_decision_id": str(record.autonomy_decision_id),
                    "adjudication_id": str(record.adjudication_id),
                },
            },
        )


def _adjudication_request(
    *,
    workspace_key: str,
    profile_key: str,
    item: EvaluationRunItem,
    purpose: str,
    calibration_metric: AutonomyReliabilityMetricRecord | None,
    retry_error: str | None = None,
) -> LLMCompletionRequest:
    user_payload: dict[str, Any] = {
        "task": "choose_autonomous_fallback_for_proposal_gate_stall",
        "allowed_actions": sorted(ADJUDICATION_PROMPT_ACTIONS),
        "schema": {
            "action": "one allowed action",
            "confidence": "0..1",
            "confidence_decomposition": {
                "model_confidence": "0..1",
                "evidence_coverage": "0..1",
                "source_fidelity": "0..1",
                "scanner_risk": "0..1",
            },
            "evidence_fidelity": "metadata_only|redacted_derivative|raw_vault_linked",
            "reason_codes": ["short-machine-readable"],
            "uncertainty_notes": ["content-safe"],
        },
        "evaluation": _evaluation_packet(item),
        "calibration_support": _calibration_support_packet(calibration_metric),
    }
    if retry_error:
        user_payload["retry"] = {
            "previous_response_problem": retry_error,
            "instruction": "Return minified JSON only, no markdown fence or prose.",
        }
    return LLMCompletionRequest(
        workspace_key=workspace_key,
        profile_key=profile_key,
        purpose=purpose,
        messages=[
            LLMMessage(
                role="system",
                content=(
                    "Return exactly one minified JSON object. No markdown, no prose. "
                    "Do not request raw content, authorize runtime writes, or override "
                    "scanner, regression, adversarial, rollback, privacy, or path gates."
                ),
            ),
            LLMMessage(
                role="user",
                content=json.dumps(user_payload, sort_keys=True, separators=(",", ":")),
            ),
        ],
        max_output_tokens=320,
        temperature=0.0,
        response_format={"type": "json_object"},
    )


async def _select_qualified_autonomous_profile(
    profiles: ProfileStore,
    *,
    workspace_key: str,
    preferred_profile_key: str | None,
) -> ModelProfileRecord | None:
    if preferred_profile_key:
        profile = await profiles.get_model_profile(
            workspace_key=workspace_key,
            profile_key=preferred_profile_key,
        )
        if profile is not None and _is_qualified_autonomous(profile):
            return profile
        return None
    for profile in await profiles.list_model_profiles(
        workspace_key=workspace_key,
        status="qualified_autonomous",
        limit=10,
    ):
        if _is_qualified_autonomous(profile):
            return profile
    for profile in await profiles.list_model_profiles(workspace_key=workspace_key, limit=25):
        if _is_qualified_autonomous(profile):
            return profile
    return None


def _is_qualified_autonomous(profile: ModelProfileRecord) -> bool:
    verdict = str(profile.qualification.get("latest_qualification_verdict") or "")
    return (
        profile.kind == "model"
        and (
            profile.status == "qualified_autonomous"
            or (profile.status == "qualified" and verdict == "qualified_autonomous")
        )
        and profile.route_kind == "openai_compatible"
    )


def _evaluation_packet(item: EvaluationRunItem) -> dict[str, Any]:
    result = item.result
    return {
        "evaluation_id": str(item.evaluation_id),
        "skill_version_id": str(item.skill_version_id),
        "status": item.status,
        "candidate_slug": result.get("candidate_slug"),
        "reason_codes": list(result.get("reason_codes") or []),
        "evidence_ids": [str(item_id) for item_id in _evidence_ids(result)],
        "probe_results": [
            {
                "kind": probe.get("kind"),
                "status": probe.get("status"),
                "score": probe.get("score"),
                "reason": probe.get("reason"),
            }
            for probe in list(result.get("probe_results") or [])[:20]
            if isinstance(probe, dict)
        ],
        "autonomy_assurance": {
            key: _dict(result.get("autonomy_assurance")).get(key)
            for key in (
                "hard_invariant_failures",
                "soft_threshold_misses",
                "autonomous_fallback_actions",
                "threshold_deadlock_candidate",
                "administrative_escalation_allowed",
                "evidence_mode",
            )
        },
    }


def _fallback_patch(
    *,
    action: str,
    decision_band: str,
    reason_codes: list[str],
    llm_verdict: dict[str, Any],
    confidence: float,
    model_profile_id: UUID | None,
    invocation_id: str | None,
    deterministic_checks: dict[str, Any],
    evidence_ids: list[str],
    calibration_metric: AutonomyReliabilityMetricRecord | None,
) -> dict[str, Any]:
    verdict_reasons = [str(code) for code in llm_verdict.get("reason_codes") or []]
    return {
        "schema": "autoskill.proposal-gate-autonomy-fallback.v1",
        "decision_family": DECISION_FAMILY,
        "selected_action": action,
        "decision_band": decision_band,
        "reason_codes": _dedupe([*reason_codes, *verdict_reasons]),
        "llm_invocation_id": invocation_id,
        "model_profile_id": str(model_profile_id) if model_profile_id else None,
        "confidence": _bounded_confidence(confidence),
        "confidence_band": _confidence_band(confidence),
        "confidence_decomposition": _confidence_decomposition(llm_verdict, confidence),
        "evidence_fidelity": str(llm_verdict.get("evidence_fidelity") or "redacted_derivative"),
        "evidence_ids": evidence_ids,
        "calibration_support": _calibration_support_packet(calibration_metric),
        "deterministic_checks": deterministic_checks,
        "llm_verdict": {
            key: llm_verdict.get(key)
            for key in (
                "action",
                "requested_action",
                "confidence",
                "confidence_decomposition",
                "evidence_fidelity",
                "reason_codes",
                "uncertainty_notes",
                "schema_status",
                "error",
            )
            if key in llm_verdict
        },
        "runtime_writes_authorized": False,
        "administrative_escalation_allowed": False,
    }


def _calibration_support_packet(
    metric: AutonomyReliabilityMetricRecord | None,
) -> dict[str, Any]:
    if metric is None:
        return {
            "calibration_family": DECISION_FAMILY,
            "status": "none",
            "sample_count": 0,
            "coverage_rate": 0.0,
        }
    return {
        "calibration_family": metric.calibration_family,
        "status": metric.calibration_support,
        "sample_count": metric.sample_count,
        "coverage_rate": metric.coverage_rate,
        "abstention_rate": metric.abstention_rate,
        "false_accept_rate": metric.false_accept_rate,
        "false_reject_rate": metric.false_reject_rate,
        "unnecessary_abstention_rate": metric.unnecessary_abstention_rate,
    }


def _normalize_verdict(value: dict[str, Any]) -> dict[str, Any]:
    requested_action = str(value.get("action") or "")
    action = ACTION_ALIASES.get(requested_action, requested_action)
    return {
        **value,
        "requested_action": requested_action,
        "action": action if action in NEEDS_INTERVENTION_ACTIONS else "collect_more_evidence",
    }


def _admissible_action(verdict: dict[str, Any], *, confidence: float) -> str:
    action = str(verdict.get("action") or "collect_more_evidence")
    if action in {"stage_ephemeral_candidate", "stage_canary"} and confidence < 0.55:
        return "collect_more_evidence"
    if action == "auto_accept":
        return "stage_canary"
    return action if action in NEEDS_INTERVENTION_ACTIONS else "collect_more_evidence"


def _decision_band(action: str) -> str:
    if action == "auto_reject":
        return "clear_reject"
    if action == "reduce_scope":
        return "narrow_scope"
    if action == "stage_canary":
        return "canary_only"
    if action == "stage_ephemeral_candidate":
        return "improve_evidence"
    return "improve_evidence"


def _confidence(value: dict[str, Any]) -> float:
    try:
        return _bounded_confidence(float(value.get("confidence", 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _confidence_decomposition(value: dict[str, Any], fallback: float) -> dict[str, float]:
    source = _dict(value.get("confidence_decomposition"))
    return {
        "model_confidence": _bounded_float(source.get("model_confidence"), fallback),
        "evidence_coverage": _bounded_float(source.get("evidence_coverage"), fallback),
        "source_fidelity": _bounded_float(source.get("source_fidelity"), fallback),
        "scanner_risk": _bounded_float(source.get("scanner_risk"), 0.0),
    }


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(stripped[start : end + 1])
    return parsed if isinstance(parsed, dict) else {}


def _evidence_ids(result: dict[str, Any]) -> list[UUID]:
    parsed: list[UUID] = []
    for item in result.get("evidence_ids") or []:
        value = _optional_uuid(item)
        if value is not None:
            parsed.append(value)
    return parsed


def _optional_uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _bounded_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _bounded_float(value: object, fallback: float) -> float:
    try:
        return _bounded_confidence(float(value))
    except (TypeError, ValueError):
        return _bounded_confidence(fallback)


def _confidence_band(value: float) -> str:
    confidence = _bounded_confidence(value)
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.55:
        return "medium"
    return "low"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
