from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autoskill.core.hashing import sha256_json
from autoskill.core.skillir import SkillIR
from autoskill.services.scanner import scan_text


@dataclass(frozen=True)
class ProbePlan:
    probe_hash: str
    kind: str
    maturity: str
    spec: dict[str, Any]
    expected: dict[str, Any]
    scanner_findings: list[dict[str, str]]

    @property
    def ok(self) -> bool:
        return not any(
            finding["severity"] in {"error", "critical"}
            for finding in self.scanner_findings
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "probe_hash": self.probe_hash,
            "kind": self.kind,
            "maturity": self.maturity,
            "spec": self.spec,
            "expected": self.expected,
            "scanner_findings": self.scanner_findings,
        }


def plan_candidate_probes(skill: SkillIR) -> list[ProbePlan]:
    """Create deterministic, artifact-grounded probe plans for a proposed candidate."""
    evidence_ids = list(skill.evidence_ids)
    target = _probe(
        skill=skill,
        kind="target",
        spec={
            "candidate_slug": skill.slug,
            "mode": "skill_visible",
            "evidence_ids": evidence_ids,
            "objective": "Verify the candidate procedure addresses the recurring evidence cluster.",
            "checks": [
                "runtime instructions cite the recurring workflow",
                "verification step can prove the intended improvement",
                "failure handling leaves a safe no-op path",
            ],
        },
        expected={
            "status": "pass",
            "min_traceability": 1.0,
            "requires_skill_visible_better_than_no_skill": True,
        },
    )
    no_skill = _probe(
        skill=skill,
        kind="no_skill_control",
        spec={
            "candidate_slug": skill.slug,
            "mode": "no_skill",
            "evidence_ids": evidence_ids,
            "objective": "Measure whether doing nothing or hiding the skill performs as well.",
            "checks": [
                "baseline can complete without the candidate",
                "candidate adds value beyond latency and token cost",
                "candidate does not merely restate existing active skills",
            ],
        },
        expected={
            "status": "compare",
            "candidate_must_improve_or_reduce_retries": True,
        },
    )
    regression = _probe(
        skill=skill,
        kind="regression",
        spec={
            "candidate_slug": skill.slug,
            "mode": "skill_visible",
            "evidence_ids": evidence_ids,
            "objective": "Reject the candidate if it broadens scope or shadows existing behavior.",
            "checks": [
                "do-not-use conditions remain enforceable",
                "required capabilities do not expand unexpectedly",
                "instructions do not introduce secret, network, or filesystem risk",
            ],
        },
        expected={
            "status": "pass",
            "no_new_blocking_scanner_findings": True,
            "no_shadowing_regression": True,
        },
    )
    return [target, no_skill, regression]


def _probe(
    *,
    skill: SkillIR,
    kind: str,
    spec: dict[str, Any],
    expected: dict[str, Any],
) -> ProbePlan:
    payload = {
        "schema": "autoskill.probe.v1",
        "candidate_slug": skill.slug,
        "kind": kind,
        "spec": spec,
        "expected": expected,
    }
    probe_hash = sha256_json(payload)
    findings = [
        {
            "severity": str(finding.severity),
            "code": finding.code,
            "message": finding.message,
        }
        for finding in scan_text(sha256_json(payload) + "\n" + str(payload))
    ]
    return ProbePlan(
        probe_hash=probe_hash,
        kind=kind,
        maturity="observed",
        spec={"schema": "autoskill.probe.v1", **spec},
        expected=expected,
        scanner_findings=findings,
    )
