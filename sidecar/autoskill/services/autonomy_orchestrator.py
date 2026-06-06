from __future__ import annotations

import json
from dataclasses import replace
from typing import Any
from uuid import UUID

from autoskill.db.autonomy import AutonomyControlStore
from autoskill.db.evaluations import EvaluationRunItem, EvaluationRunResult
from autoskill.db.profiles import ModelProfileRecord, ProfileStore
from autoskill.services.llm import LLMClient, LLMCompletionRequest, LLMMessage

DECISION_FAMILY = "skill_plan_semantic_adjudication"

NEEDS_INTERVENTION_ACTIONS = {
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
    "assemble_richer_permitted_evidence": "collect_more_evidence",
    "canary_with_smaller_exposure": "stage_canary",
    "create_ephemeral_candidate": "stage_ephemeral_candidate",
    "ephemeral_candidate": "stage_ephemeral_candidate",
    "auto_reject_with_reason": "auto_reject",
}


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
            )
        except Exception as exc:
            return await self._record_without_llm(
                item,
                workspace_key=workspace_key,
                job_id=job_id,
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
    ) -> dict[str, Any]:
        completion = await self.llm.complete(
            LLMCompletionRequest(
                workspace_key=workspace_key,
                profile_key=profile.profile_key,
                purpose="proposal_gate.needs_intervention_adjudication",
                messages=[
                    LLMMessage(
                        role="system",
                        content=(
                            "You are the SkillKernel semantic adjudicator. "
                            "Return one JSON object only. Do not request raw "
                            "content, do not authorize runtime writes, and do "
                            "not override scanner, regression, adversarial, "
                            "rollback, privacy, or path-containment gates."
                        ),
                    ),
                    LLMMessage(
                        role="user",
                        content=json.dumps(
                            {
                                "task": "choose_autonomous_fallback_for_proposal_gate_stall",
                                "allowed_actions": sorted(NEEDS_INTERVENTION_ACTIONS),
                                "required_schema": {
                                    "action": sorted(NEEDS_INTERVENTION_ACTIONS),
                                    "confidence": "number between 0 and 1",
                                    "confidence_decomposition": {
                                        "model_confidence": "number",
                                        "evidence_coverage": "number",
                                        "source_fidelity": "number",
                                        "scanner_risk": "number",
                                    },
                                    "evidence_fidelity": "metadata_only|redacted_derivative|raw_vault_linked",
                                    "reason_codes": ["short-machine-readable-reasons"],
                                    "uncertainty_notes": ["content-safe notes"],
                                },
                                "evaluation": _evaluation_packet(item),
                            },
                            sort_keys=True,
                        ),
                    ),
                ],
                max_output_tokens=700,
                temperature=0.0,
            )
        )
        parsed = _parse_json_object(completion.text)
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
    return (
        profile.kind == "model"
        and profile.status == "qualified_autonomous"
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
        "deterministic_checks": deterministic_checks,
        "llm_verdict": {
            key: llm_verdict.get(key)
            for key in (
                "action",
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


def _normalize_verdict(value: dict[str, Any]) -> dict[str, Any]:
    action = ACTION_ALIASES.get(str(value.get("action") or ""), str(value.get("action") or ""))
    return {
        **value,
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
