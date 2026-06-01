from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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

    def to_json(self) -> dict[str, object]:
        return {
            "status": self.status,
            "probe_results": [result.to_json() for result in self.probe_results],
            "reason_codes": self.reason_codes,
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
        )

    probe_results = [_evaluate_probe(skill_ir=skill_ir, probe=probe) for probe in probes]
    if any(result.status == "failed" for result in probe_results):
        status = "failed"
        reason_codes = ["probe-failed"]
    elif any(result.status == "needs_intervention" for result in probe_results):
        status = "needs_intervention"
        reason_codes = ["intervention-required"]
    else:
        status = "passed"
        reason_codes = ["all-deterministic-probes-passed"]

    return ProposalGateEvaluation(
        status=status,
        probe_results=probe_results,
        reason_codes=reason_codes,
    )


def _evaluate_probe(*, skill_ir: dict[str, Any], probe: dict[str, Any]) -> ProbeEvaluation:
    kind = str(probe["kind"])
    spec = _dict(probe.get("spec"))
    expected = _dict(probe.get("expected"))
    if kind == "target":
        return _evaluate_target_probe(skill_ir=skill_ir, probe=probe, spec=spec)
    if kind == "regression":
        return _evaluate_regression_probe(skill_ir=skill_ir, probe=probe, spec=spec)
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
