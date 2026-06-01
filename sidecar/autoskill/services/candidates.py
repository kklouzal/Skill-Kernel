from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autoskill.core.skillir import SkillIR
from autoskill.services.compiler import compile_skill
from autoskill.services.opportunity import OpportunityCandidate, OpportunityMineResult
from autoskill.services.probes import ProbePlan, plan_candidate_probes


@dataclass(frozen=True)
class CandidateSkillProposal:
    candidate_slug: str
    recommendation: str
    evidence_ids: list[str]
    skipped_reason: str | None
    skillir: SkillIR | None
    compiled_runtime_text: str | None
    compiled_sha256: str | None
    scanner_findings: list[dict[str, str]]
    probe_plan: list[ProbePlan]

    def to_json(self) -> dict[str, Any]:
        skillir = self.skillir.model_dump(by_alias=True, mode="json") if self.skillir else None
        return {
            "candidate_slug": self.candidate_slug,
            "recommendation": self.recommendation,
            "evidence_ids": self.evidence_ids,
            "skipped_reason": self.skipped_reason,
            "skillir": skillir,
            "compiled_sha256": self.compiled_sha256,
            "scanner_findings": self.scanner_findings,
            "probe_plan": [probe.to_json() for probe in self.probe_plan],
        }


@dataclass(frozen=True)
class CandidateProposalResult:
    scanned: int
    proposed: int
    skipped: int
    proposals: list[CandidateSkillProposal]

    def to_json(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "proposed": self.proposed,
            "skipped": self.skipped,
            "proposals": [proposal.to_json() for proposal in self.proposals],
        }


def propose_candidate_skills(opportunities: OpportunityMineResult) -> CandidateProposalResult:
    proposals = [_proposal_from_opportunity(candidate) for candidate in opportunities.candidates]
    proposed = sum(1 for proposal in proposals if proposal.skillir is not None)
    return CandidateProposalResult(
        scanned=opportunities.scanned,
        proposed=proposed,
        skipped=len(proposals) - proposed,
        proposals=proposals,
    )


def _proposal_from_opportunity(candidate: OpportunityCandidate) -> CandidateSkillProposal:
    if candidate.recommendation != "propose_candidate":
        return CandidateSkillProposal(
            candidate_slug=candidate.candidate_slug,
            recommendation=candidate.recommendation,
            evidence_ids=candidate.evidence_ids,
            skipped_reason=f"opportunity recommendation is {candidate.recommendation}",
            skillir=None,
            compiled_runtime_text=None,
            compiled_sha256=None,
            scanner_findings=[],
            probe_plan=[],
        )

    skill = SkillIR(
        slug=candidate.candidate_slug,
        name=candidate.candidate_slug,
        description=_compact_description(candidate.candidate_description),
        applicability=[
            candidate.candidate_description,
            "Use only after active and archived skill matching found no sufficient reusable skill.",
        ],
        inputs=[
            "Cited evidence IDs from the recurring opportunity cluster.",
            "Current active/archive duplicate-match result.",
        ],
        preconditions=[
            "The operator or autonomous policy is in propose-only or stronger guarded mode.",
            "No runtime skill file or support artifact has been written for this proposal.",
        ],
        steps=[
            "Review the cited evidence cluster and identify the stable reusable procedure.",
            "Compare the proposed behavior against active and archived skill matches.",
            "Draft the smallest procedural skill that covers the recurring workflow.",
            "Add verification and failure handling before any staged activation attempt.",
        ],
        outputs=[
            "A propose-only SkillIR candidate with cited evidence and planned probes.",
        ],
        effects=[
            "Records reusable procedure intent without activating runtime skill files.",
        ],
        state_delta=[
            "May create inactive candidate rows, body-index documents, probes, and evaluations.",
        ],
        side_effects=[
            "Does not mutate active or archived skill roots.",
        ],
        termination=[
            "Stop after candidate persistence and proposal-gate probe planning.",
        ],
        idempotency="retry_safe",
        verification=[
            "Every proposed runtime instruction is traceable to cited evidence IDs.",
            "Scanner findings are non-blocking before the proposal can advance.",
            "The candidate remains propose-only until probes and regression checks are created.",
        ],
        failure_handling=[
            "Skip creation when active matches cover the workflow.",
            "Prefer archived promotion when archived matches cover the workflow.",
            "Leave the opportunity as evidence-only when scanner or provenance checks fail.",
        ],
        failure_modes=[
            "Observed evidence is insufficient for intervention validation.",
            "Active or archived skill matching finds a better reuse path.",
        ],
        do_not_use_when=[
            "The workflow is one-off, user-specific, or lacks repeated evidence.",
            "The proposal would duplicate an active or promotable archived skill.",
        ],
        never=[
            "Do not write files, activate skills, or mutate archives from this proposal step.",
            "Do not include raw private transcript text or secrets in runtime skill text.",
        ],
        evidence_ids=candidate.evidence_ids,
        risk_notes=[
            "Deterministic scaffold only; requires evaluation before activation.",
            "Generated from recurring observed evidence, not intervention-validated evidence.",
        ],
    )
    compiled = compile_skill(skill)
    probe_plan = plan_candidate_probes(skill)
    return CandidateSkillProposal(
        candidate_slug=candidate.candidate_slug,
        recommendation=candidate.recommendation,
        evidence_ids=candidate.evidence_ids,
        skipped_reason=None,
        skillir=skill,
        compiled_runtime_text=compiled.skill_md,
        compiled_sha256=compiled.sha256,
        scanner_findings=[
            {
                "severity": str(finding.severity),
                "code": finding.code,
                "message": finding.message,
            }
            for finding in compiled.scanner_findings
        ],
        probe_plan=probe_plan,
    )


def _compact_description(description: str) -> str:
    compact = " ".join(description.split())
    if len(compact) <= 180:
        return compact
    return compact[:177].rstrip() + "..."
