from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autoskill.services.scanner import scan_text

ACCEPTANCE_POLICY = {
    "scanner_pass": True,
    "target_probe_min_pass_rate": 0.85,
    "regression_failure_hard_budget": 0,
    "adversarial_critical_budget": 0,
    "max_token_delta_without_utility_gain": 0,
    "min_utility_delta": 0.03,
}

SOFT_THRESHOLD_FALLBACKS = {
    "target-pass-rate-below-threshold": [
        "generate_more_probes",
        "collect_more_evidence",
        "run_re_adjudication",
        "no_op_reschedule",
    ],
    "token-delta-without-utility-gain": [
        "reduce_scope",
        "compile_more_conservatively",
        "decompose_candidate",
        "run_counterfactual_trial",
    ],
    "utility-delta-below-threshold": [
        "run_counterfactual_trial",
        "canary_with_smaller_exposure",
        "collect_more_evidence",
        "auto_reject_with_reason",
    ],
    "intervention-required": [
        "assemble_richer_permitted_evidence",
        "generate_more_probes",
        "run_counterfactual_trial",
        "no_op_reschedule",
    ],
}

HARD_INVARIANT_REASON_CODES = {
    "scanner-blocked",
    "regression-failure-budget-exceeded",
    "adversarial-critical-budget-exceeded",
}


@dataclass(frozen=True)
class ProbeEvaluation:
    probe_hash: str
    kind: str
    status: str
    score: float
    reason: str

    def to_json(self) -> dict[str, object]:
        return {
            "probe_hash": self.probe_hash,
            "kind": self.kind,
            "status": self.status,
            "score": self.score,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProposalGateEvaluation:
    status: str
    probe_results: list[ProbeEvaluation]
    reason_codes: list[str]
    acceptance_policy: dict[str, float | int | bool]
    acceptance_metrics: dict[str, float | int]
    autonomy_assurance: dict[str, Any]

    def to_json(self) -> dict[str, object]:
        return {
            "status": self.status,
            "probe_results": [result.to_json() for result in self.probe_results],
            "reason_codes": self.reason_codes,
            "acceptance_policy": self.acceptance_policy,
            "acceptance_metrics": self.acceptance_metrics,
            "autonomy_assurance": self.autonomy_assurance,
        }


def evaluate_proposal_gate(
    *,
    skill_ir: dict[str, Any],
    scanner_status: str,
    probes: list[dict[str, Any]],
) -> ProposalGateEvaluation:
    if scanner_status != "passed":
        return ProposalGateEvaluation(
            status="blocked",
            probe_results=[
                _result(probe, status="blocked", score=0.0, reason="scanner did not pass")
                for probe in probes
            ],
            reason_codes=["scanner-blocked"],
            acceptance_policy=ACCEPTANCE_POLICY,
            acceptance_metrics=_acceptance_metrics([], probes=[]),
            autonomy_assurance=_autonomy_assurance(
                status="blocked",
                probe_results=[],
                reason_codes=["scanner-blocked"],
                acceptance_metrics=_acceptance_metrics([], probes=[]),
            ),
        )

    probe_results = [_evaluate_probe(skill_ir=skill_ir, probe=probe) for probe in probes]
    acceptance_metrics = _acceptance_metrics(probe_results, probes=probes)
    if any(result.status == "failed" for result in probe_results):
        status = "failed"
        reason_codes = ["probe-failed"]
    elif any(result.status == "needs_intervention" for result in probe_results):
        status = "needs_intervention"
        reason_codes = ["intervention-required"]
    elif policy_reason_codes := _acceptance_policy_reason_codes(acceptance_metrics):
        status = "failed"
        reason_codes = policy_reason_codes
    else:
        status = "passed"
        reason_codes = ["all-deterministic-probes-passed"]

    return ProposalGateEvaluation(
        status=status,
        probe_results=probe_results,
        reason_codes=reason_codes,
        acceptance_policy=ACCEPTANCE_POLICY,
        acceptance_metrics=acceptance_metrics,
        autonomy_assurance=_autonomy_assurance(
            status=status,
            probe_results=probe_results,
            reason_codes=reason_codes,
            acceptance_metrics=acceptance_metrics,
        ),
    )


def detect_threshold_deadlocks(
    evaluation_results: list[dict[str, Any]],
    *,
    min_repeated_stalls: int = 3,
) -> list[dict[str, Any]]:
    """Summarize repeated soft-threshold stalls without weakening hard gates."""

    cohorts: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = {}
    for result in evaluation_results:
        assurance = _dict(result.get("autonomy_assurance"))
        if not assurance.get("threshold_deadlock_candidate"):
            continue
        if assurance.get("hard_invariant_failures"):
            continue
        soft_misses = tuple(str(item) for item in assurance.get("soft_threshold_misses") or [])
        if not soft_misses:
            continue
        cohort_key = str(
            result.get("skill_version_id")
            or result.get("candidate_slug")
            or _dict(result.get("result")).get("candidate_slug")
            or "unknown"
        )
        cohorts.setdefault((cohort_key, soft_misses), []).append(result)

    findings: list[dict[str, Any]] = []
    for (cohort_key, soft_misses), rows in sorted(cohorts.items()):
        if len(rows) < max(1, min_repeated_stalls):
            continue
        fallbacks = _dedupe(
            action
            for reason_code in soft_misses
            for action in SOFT_THRESHOLD_FALLBACKS.get(reason_code, [])
        )
        findings.append(
            {
                "finding_kind": "threshold_deadlock",
                "cohort_key": cohort_key,
                "stall_count": len(rows),
                "soft_threshold_misses": list(soft_misses),
                "hard_invariant_failures": [],
                "autonomous_fallback_actions": fallbacks,
                "administrative_escalation_allowed": False,
                "reason": (
                    "soft thresholds repeatedly stalled while no hard invariant "
                    "failure was present"
                ),
            }
        )
    return findings


def _evaluate_probe(*, skill_ir: dict[str, Any], probe: dict[str, Any]) -> ProbeEvaluation:
    kind = str(probe["kind"])
    spec = _dict(probe.get("spec"))
    expected = _dict(probe.get("expected"))
    if kind == "target":
        return _evaluate_target_probe(skill_ir=skill_ir, probe=probe, spec=spec)
    if kind == "regression":
        return _evaluate_regression_probe(skill_ir=skill_ir, probe=probe, spec=spec)
    if kind == "adversarial":
        return _evaluate_adversarial_probe(skill_ir=skill_ir, probe=probe, expected=expected)
    if kind == "no_skill_control":
        return _evaluate_no_skill_probe(probe=probe, spec=spec, expected=expected)
    return _result(probe, status="failed", score=0.0, reason=f"unknown probe kind: {kind}")


def _evaluate_target_probe(
    *,
    skill_ir: dict[str, Any],
    probe: dict[str, Any],
    spec: dict[str, Any],
) -> ProbeEvaluation:
    evidence_ids = list(skill_ir.get("evidence_ids") or [])
    has_required_sections = all(
        skill_ir.get(section)
        for section in ("applicability", "steps", "verification", "failure_handling", "never")
    )
    probe_evidence = list(spec.get("evidence_ids") or [])
    if not evidence_ids or not probe_evidence:
        return _result(probe, status="failed", score=0.0, reason="missing cited evidence")
    if not has_required_sections:
        return _result(
            probe,
            status="failed",
            score=0.0,
            reason="missing required SkillIR sections",
        )
    return _result(
        probe,
        status="passed",
        score=1.0,
        reason="candidate is traceable to evidence and has required runtime sections",
    )


def _evaluate_no_skill_probe(
    *,
    probe: dict[str, Any],
    spec: dict[str, Any],
    expected: dict[str, Any],
) -> ProbeEvaluation:
    if not spec.get("evidence_ids"):
        return _result(probe, status="failed", score=0.0, reason="missing baseline evidence")
    replay = _dict(spec.get("intervention_replay"))
    if replay:
        return _evaluate_intervention_replay(probe=probe, replay=replay)
    if expected.get("candidate_must_improve_or_reduce_retries"):
        return _result(
            probe,
            status="needs_intervention",
            score=0.5,
            reason="requires future skill-visible versus no-skill comparison",
        )
    return _result(probe, status="passed", score=1.0, reason="no-skill control recorded")


def _evaluate_intervention_replay(
    *,
    probe: dict[str, Any],
    replay: dict[str, Any],
) -> ProbeEvaluation:
    no_skill = _dict(replay.get("no_skill"))
    skill_visible = _dict(replay.get("skill_visible"))
    if not no_skill or not skill_visible:
        return _result(
            probe,
            status="needs_intervention",
            score=0.5,
            reason="intervention replay requires no-skill and skill-visible outcomes",
        )
    no_skill_success = bool(no_skill.get("success"))
    skill_success = bool(skill_visible.get("success"))
    no_skill_retries = _optional_float(no_skill.get("retries"))
    skill_retries = _optional_float(skill_visible.get("retries"))
    no_skill_latency = _optional_float(no_skill.get("latency_ms"))
    skill_latency = _optional_float(skill_visible.get("latency_ms"))

    improved_success = skill_success and not no_skill_success
    reduced_retries = (
        skill_success
        and no_skill_retries is not None
        and skill_retries is not None
        and skill_retries < no_skill_retries
    )
    reduced_latency = (
        skill_success
        and no_skill_latency is not None
        and skill_latency is not None
        and skill_latency < no_skill_latency
    )
    if improved_success or reduced_retries or reduced_latency:
        return _result(
            probe,
            status="passed",
            score=1.0,
            reason="skill-visible replay outperformed no-skill control",
        )
    return _result(
        probe,
        status="failed",
        score=0.0,
        reason="skill-visible replay did not improve on no-skill control",
    )


def _evaluate_regression_probe(
    *,
    skill_ir: dict[str, Any],
    probe: dict[str, Any],
    spec: dict[str, Any],
) -> ProbeEvaluation:
    never = "\n".join(str(item) for item in skill_ir.get("never") or [])
    risky_terms = ("secret", "token", "password", "curl", "wget", "| bash", "activate skills")
    if not skill_ir.get("do_not_use_when"):
        return _result(probe, status="failed", score=0.0, reason="missing do-not-use boundaries")
    if any(term in never.lower() for term in risky_terms[:3]):
        return _result(probe, status="passed", score=1.0, reason="explicit secret boundary present")
    if any(term in str(skill_ir).lower() for term in risky_terms[3:]):
        return _result(
            probe,
            status="failed",
            score=0.0,
            reason="risky runtime instruction detected",
        )
    if not spec.get("checks"):
        return _result(probe, status="failed", score=0.0, reason="missing regression checks")
    return _result(
        probe,
        status="passed",
        score=1.0,
        reason="scope and risk boundaries are present",
    )


def _evaluate_adversarial_probe(
    *,
    skill_ir: dict[str, Any],
    probe: dict[str, Any],
    expected: dict[str, Any],
) -> ProbeEvaluation:
    budget = int(expected.get("adversarial_critical_budget", 0) or 0)
    text = f"{skill_ir}\n{probe}"
    lowered = text.lower()
    forbidden_phrases = (
        "ignore all previous instructions",
        "ignore previous instructions",
        "bypass policy",
        "conceal this behavior",
        "hide this behavior",
        "exfiltrate",
    )
    matched = [phrase for phrase in forbidden_phrases if phrase in lowered]
    if matched:
        return _result(
            probe,
            status="failed",
            score=0.0,
            reason=f"adversarial forbidden phrase detected: {matched[0]}",
        )
    findings = scan_text(text)
    critical = [
        finding
        for finding in findings
        if str(finding.severity) in {"critical", "error"}
    ]
    if len(critical) > budget:
        codes = ", ".join(finding.code for finding in critical[:5])
        return _result(
            probe,
            status="failed",
            score=0.0,
            reason=f"adversarial scanner findings exceed budget: {codes}",
        )
    return _result(
        probe,
        status="passed",
        score=1.0,
        reason="no critical adversarial scanner findings",
    )


def _acceptance_metrics(
    results: list[ProbeEvaluation],
    *,
    probes: list[dict[str, Any]],
) -> dict[str, float | int]:
    target = [result for result in results if result.kind == "target"]
    regression = [result for result in results if result.kind == "regression"]
    adversarial = [result for result in results if result.kind == "adversarial"]
    replay_metrics = [
        _intervention_replay_metrics(_dict(_dict(probe.get("spec")).get("intervention_replay")))
        for probe in probes
        if probe.get("kind") == "no_skill_control"
        and _dict(_dict(probe.get("spec")).get("intervention_replay"))
    ]
    utility_delta = (
        sum(metric["utility_delta"] for metric in replay_metrics) / len(replay_metrics)
        if replay_metrics
        else 0.0
    )
    token_delta = sum(metric["token_delta"] for metric in replay_metrics)
    target_pass_rate = (
        sum(1 for result in target if result.status == "passed") / len(target)
        if target
        else 0.0
    )
    return {
        "target_probe_pass_rate": round(target_pass_rate, 6),
        "regression_failures": sum(1 for result in regression if result.status == "failed"),
        "adversarial_failures": sum(1 for result in adversarial if result.status == "failed"),
        "probe_count": len(results),
        "intervention_replay_count": len(replay_metrics),
        "utility_delta": round(utility_delta, 6),
        "token_delta": round(token_delta, 6),
    }


def _acceptance_policy_reason_codes(metrics: dict[str, float | int]) -> list[str]:
    reason_codes: list[str] = []
    if metrics["target_probe_pass_rate"] < ACCEPTANCE_POLICY["target_probe_min_pass_rate"]:
        reason_codes.append("target-pass-rate-below-threshold")
    if metrics["regression_failures"] > ACCEPTANCE_POLICY["regression_failure_hard_budget"]:
        reason_codes.append("regression-failure-budget-exceeded")
    if metrics["adversarial_failures"] > ACCEPTANCE_POLICY["adversarial_critical_budget"]:
        reason_codes.append("adversarial-critical-budget-exceeded")
    if metrics["intervention_replay_count"] > 0:
        utility_delta = float(metrics["utility_delta"])
        token_delta = float(metrics["token_delta"])
        if (
            token_delta > ACCEPTANCE_POLICY["max_token_delta_without_utility_gain"]
            and utility_delta <= 0
        ):
            reason_codes.append("token-delta-without-utility-gain")
        if utility_delta < ACCEPTANCE_POLICY["min_utility_delta"]:
            reason_codes.append("utility-delta-below-threshold")
    return reason_codes


def _autonomy_assurance(
    *,
    status: str,
    probe_results: list[ProbeEvaluation],
    reason_codes: list[str],
    acceptance_metrics: dict[str, float | int],
) -> dict[str, Any]:
    hard_failures = _hard_invariant_failures(
        probe_results=probe_results,
        reason_codes=reason_codes,
    )
    soft_misses = _soft_threshold_misses(
        status=status,
        probe_results=probe_results,
        reason_codes=reason_codes,
    )
    fallback_actions = _dedupe(
        action
        for reason_code in soft_misses
        for action in SOFT_THRESHOLD_FALLBACKS.get(reason_code, [])
    )
    threshold_deadlock_candidate = bool(soft_misses) and not hard_failures
    return {
        "decision_family": "skill_plan_semantic_adjudication",
        "policy_version": "proposal_gate_acceptance_policy.v1",
        "hard_invariant_failures": hard_failures,
        "soft_threshold_misses": soft_misses,
        "autonomous_fallback_actions": fallback_actions,
        "threshold_deadlock_candidate": threshold_deadlock_candidate,
        "threshold_deadlock_min_repeated_stalls": 3 if threshold_deadlock_candidate else None,
        "administrative_escalation_allowed": False,
        "administrative_escalation_reason_required": [
            "policy_forbids_needed_raw_access",
            "raw_reveal_requested",
            "external_owned_root_mutation_requested",
            "irreversible_infrastructure_change_requested",
            "required_infrastructure_unavailable",
            "repeated_contradictory_adjudications_after_fallback",
            "predelegated_authority_absent_for_T4_action",
        ],
        "calibration_support_status": "fixed_policy_pending_replay_calibration",
        "evidence_mode": _evidence_mode(acceptance_metrics),
    }


def _hard_invariant_failures(
    *,
    probe_results: list[ProbeEvaluation],
    reason_codes: list[str],
) -> list[str]:
    failures = [code for code in reason_codes if code in HARD_INVARIANT_REASON_CODES]
    for result in probe_results:
        if result.status != "failed":
            continue
        if result.kind in {"regression", "adversarial"}:
            failures.append(f"{result.kind}-probe-failed")
    return _dedupe(failures)


def _soft_threshold_misses(
    *,
    status: str,
    probe_results: list[ProbeEvaluation],
    reason_codes: list[str],
) -> list[str]:
    misses = [code for code in reason_codes if code in SOFT_THRESHOLD_FALLBACKS]
    for result in probe_results:
        if result.status != "failed":
            continue
        if result.kind in {"target", "no_skill_control"}:
            misses.append(f"{result.kind}-evidence-insufficient")
    if status == "needs_intervention":
        misses.append("intervention-required")
    return _dedupe(misses)


def _evidence_mode(metrics: dict[str, float | int]) -> str:
    if int(metrics.get("intervention_replay_count", 0) or 0) > 0:
        return "semantic_derivative_only"
    if int(metrics.get("probe_count", 0) or 0) > 0:
        return "metadata_plus_probe_plan"
    return "metadata_only"


def _dedupe(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _intervention_replay_metrics(replay: dict[str, Any]) -> dict[str, float]:
    no_skill = _dict(replay.get("no_skill"))
    skill_visible = _dict(replay.get("skill_visible"))
    explicit_utility_delta = _first_float(
        replay.get("utility_delta"),
        replay.get("marginal_utility_delta"),
        skill_visible.get("utility_delta"),
        skill_visible.get("marginal_utility_delta"),
    )
    no_skill_tokens = _first_float(
        no_skill.get("tokens"),
        no_skill.get("token_count"),
        no_skill.get("total_tokens"),
        no_skill.get("context_tokens"),
    )
    skill_tokens = _first_float(
        skill_visible.get("tokens"),
        skill_visible.get("token_count"),
        skill_visible.get("total_tokens"),
        skill_visible.get("context_tokens"),
    )
    token_delta = (
        skill_tokens - no_skill_tokens
        if no_skill_tokens is not None and skill_tokens is not None
        else 0.0
    )
    utility_delta = (
        explicit_utility_delta
        if explicit_utility_delta is not None
        else _derived_utility(no_skill=no_skill, skill_visible=skill_visible)
    )
    return {"utility_delta": utility_delta, "token_delta": token_delta}


def _derived_utility(*, no_skill: dict[str, Any], skill_visible: dict[str, Any]) -> float:
    no_skill_success = bool(no_skill.get("success"))
    skill_success = bool(skill_visible.get("success"))
    utility = float(skill_success) - float(no_skill_success)

    no_skill_retries = _optional_float(no_skill.get("retries"))
    skill_retries = _optional_float(skill_visible.get("retries"))
    if no_skill_retries is not None and skill_retries is not None:
        utility += max(0.0, no_skill_retries - skill_retries) * 0.05

    no_skill_latency = _optional_float(no_skill.get("latency_ms"))
    skill_latency = _optional_float(skill_visible.get("latency_ms"))
    if (
        no_skill_latency is not None
        and skill_latency is not None
        and no_skill_latency > 0
        and skill_latency < no_skill_latency
    ):
        utility += min(0.1, ((no_skill_latency - skill_latency) / no_skill_latency) * 0.1)

    no_skill_tool_errors = _optional_float(no_skill.get("tool_errors"))
    skill_tool_errors = _optional_float(skill_visible.get("tool_errors"))
    if no_skill_tool_errors is not None and skill_tool_errors is not None:
        utility += max(0.0, no_skill_tool_errors - skill_tool_errors) * 0.1
    return utility


def _result(
    probe: dict[str, Any],
    *,
    status: str,
    score: float,
    reason: str,
) -> ProbeEvaluation:
    return ProbeEvaluation(
        probe_hash=str(probe["probe_hash"]),
        kind=str(probe["kind"]),
        status=status,
        score=score,
        reason=reason,
    )


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_float(*values: object) -> float | None:
    for value in values:
        parsed = _optional_float(value)
        if parsed is not None:
            return parsed
    return None
