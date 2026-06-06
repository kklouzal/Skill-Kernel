from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from autoskill.db.evidence import EvidenceDeriveResult, EvidenceRecord, EvidenceStore
from autoskill.db.retrieval import RetrievalStore
from autoskill.db.usage import UsageTopologyRecommendation
from autoskill.services.candidates import (
    CandidateProposalResult,
    propose_candidate_skills,
)
from autoskill.services.opportunity import OpportunityMineResult, mine_opportunities


@dataclass(frozen=True)
class HistoricalBootstrapTopologyResult:
    scanned: int
    accepted: int
    blocked: int
    recommendations: list[UsageTopologyRecommendation]

    def to_json(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "accepted": self.accepted,
            "blocked": self.blocked,
            "activation_allowed": False,
            "recommendations": [
                {
                    **recommendation.to_json(),
                    "mode": "propose_only",
                    "runtime_file_writes": "forbidden",
                    "historical_evidence_only": True,
                }
                for recommendation in self.recommendations
            ],
        }


@dataclass(frozen=True)
class HistoricalBootstrapConsolidationResult:
    scanned: int
    historical_scanned: int
    opportunities: OpportunityMineResult
    proposals: CandidateProposalResult
    topology: HistoricalBootstrapTopologyResult

    def to_json(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "historical_scanned": self.historical_scanned,
            "opportunities": self.opportunities.to_json(),
            "proposals": self.proposals.to_json(),
            "topology": self.topology.to_json(),
            "activation_allowed": False,
        }


async def consolidate_historical_bootstrap(
    evidence_store: EvidenceStore,
    retrieval_store: RetrievalStore,
    *,
    workspace_key: str,
    limit: int = 250,
    min_support: int = 2,
) -> HistoricalBootstrapConsolidationResult:
    records = await evidence_store.list_evidence(workspace_key=workspace_key, limit=limit)
    historical_records = [record for record in records if _historical_bootstrap_evidence(record)]
    filtered = _FilteredEvidenceStore(historical_records)
    opportunities = await mine_opportunities(
        filtered,
        retrieval_store,
        workspace_key=workspace_key,
        limit=len(historical_records) or 1,
        min_support=min_support,
    )
    proposals = propose_candidate_skills(opportunities)
    topology = _historical_topology_recommendations(
        historical_records,
        min_support=min_support,
    )
    return HistoricalBootstrapConsolidationResult(
        scanned=len(records),
        historical_scanned=len(historical_records),
        opportunities=opportunities,
        proposals=proposals,
        topology=topology,
    )


def _historical_bootstrap_evidence(record: EvidenceRecord) -> bool:
    if not isinstance(record.payload, dict):
        return False
    if record.kind == "historical_chunk_observation":
        return True
    if record.kind != "recurring_evidence_cluster":
        return False
    return any(str(item).startswith("historical") for item in record.taint)


def _historical_topology_recommendations(
    records: list[EvidenceRecord],
    *,
    min_support: int,
) -> HistoricalBootstrapTopologyResult:
    recommendations = [
        recommendation
        for record in records
        for recommendation in _topology_recommendations_from_record(
            record,
            min_support=min_support,
        )
    ]
    return HistoricalBootstrapTopologyResult(
        scanned=len(records),
        accepted=sum(1 for recommendation in recommendations if recommendation.accepted),
        blocked=sum(1 for recommendation in recommendations if not recommendation.accepted),
        recommendations=recommendations,
    )


def _topology_recommendations_from_record(
    record: EvidenceRecord,
    *,
    min_support: int,
) -> list[UsageTopologyRecommendation]:
    payload = record.payload if isinstance(record.payload, dict) else {}
    candidates = _topology_payload_candidates(payload)
    recommendations: list[UsageTopologyRecommendation] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        operation = str(
            candidate.get("recommended_operation")
            or candidate.get("operation_kind")
            or candidate.get("topology_operation_kind")
            or ""
        )
        if operation not in {"improve", "compose", "decompose"}:
            continue
        support_count = _int_value(
            candidate.get("support_count")
            or candidate.get("support")
            or payload.get("support_count")
            or 0
        )
        skill_ids = _uuid_list(
            candidate.get("skill_ids")
            or candidate.get("subject_skill_ids")
            or candidate.get("candidate_skill_ids")
            or []
        )
        evidence_ids = _uuid_list(
            candidate.get("evidence_ids")
            or candidate.get("source_evidence_ids")
            or [record.evidence_id]
        )
        success_count = _int_value(candidate.get("success_count") or 0)
        failure_count = _int_value(candidate.get("failure_count") or 0)
        sequence_count = _int_value(candidate.get("sequence_count") or 0)
        context_signal_count = _int_value(candidate.get("context_signal_count") or 0)
        token_waste = _int_value(candidate.get("token_waste") or 0)
        blockers = _topology_blockers(
            operation=operation,
            skill_ids=skill_ids,
            support_count=support_count,
            success_count=success_count,
            failure_count=failure_count,
            sequence_count=sequence_count,
            context_signal_count=context_signal_count,
            min_support=min_support,
        )
        recommendations.append(
            UsageTopologyRecommendation(
                skill_usage_cluster_id=None,
                cluster_key=str(
                    candidate.get("cluster_key")
                    or payload.get("signature")
                    or f"historical:{operation}:{record.evidence_hash}"
                ),
                skill_ids=skill_ids,
                evidence_ids=evidence_ids,
                recommended_operation=operation,
                support_count=support_count,
                success_count=success_count,
                failure_count=failure_count,
                sequence_count=sequence_count,
                operation_score=_topology_score(
                    operation=operation,
                    support_count=support_count,
                    success_count=success_count,
                    failure_count=failure_count,
                    sequence_count=sequence_count,
                    context_signal_count=context_signal_count,
                    token_waste=token_waste,
                ),
                blockers=blockers,
                metadata={
                    "source": "historical_bootstrap",
                    "historical_evidence_only": True,
                    "source_record_id": str(record.evidence_id),
                    "source_kind": record.kind,
                    "taint": sorted(str(item) for item in record.taint),
                    "context_signal_count": context_signal_count,
                    "token_waste": token_waste,
                    "thresholds": {"min_support": min_support},
                },
            )
        )
    return recommendations


def _topology_payload_candidates(payload: dict[str, Any]) -> list[object]:
    explicit = payload.get("topology_recommendations")
    if isinstance(explicit, list):
        return explicit
    recommendation = payload.get("topology_recommendation")
    if isinstance(recommendation, dict):
        return [recommendation]
    if any(
        key in payload
        for key in (
            "recommended_operation",
            "operation_kind",
            "topology_operation_kind",
        )
    ):
        return [payload]
    return []


def _topology_blockers(
    *,
    operation: str,
    skill_ids: list[UUID],
    support_count: int,
    success_count: int,
    failure_count: int,
    sequence_count: int,
    context_signal_count: int,
    min_support: int,
) -> list[str]:
    blockers: list[str] = []
    if support_count < min_support:
        blockers.append("historical topology support below threshold")
    if operation == "compose" and len(skill_ids) < 2:
        blockers.append("compose recommendation requires at least two skills")
    if operation == "compose" and success_count <= 0:
        blockers.append("historical compose lacks successful outcome evidence")
    if operation == "compose" and failure_count > success_count:
        blockers.append("historical compose failure count exceeds success count")
    if operation == "compose" and sequence_count <= 0:
        blockers.append("historical compose lacks stable sequence evidence")
    if operation == "improve" and failure_count + context_signal_count <= 0:
        blockers.append("historical improve lacks negative outcome evidence")
    if operation == "decompose" and context_signal_count <= 0:
        blockers.append("historical decompose lacks context-waste evidence")
    return blockers


def _topology_score(
    *,
    operation: str,
    support_count: int,
    success_count: int,
    failure_count: int,
    sequence_count: int,
    context_signal_count: int,
    token_waste: int,
) -> float:
    if operation in {"improve", "decompose"}:
        return float(
            support_count
            + (failure_count * 2)
            + (context_signal_count * 2)
            + success_count
            + min(token_waste / 250.0, 4.0)
        )
    return float(support_count + (success_count * 2) + sequence_count - failure_count)


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _uuid_list(values: object) -> list[UUID]:
    if not isinstance(values, list):
        values = [values]
    stable: list[UUID] = []
    seen: set[str] = set()
    for value in values:
        try:
            uuid_value = value if isinstance(value, UUID) else UUID(str(value))
        except (TypeError, ValueError):
            continue
        marker = str(uuid_value)
        if marker in seen:
            continue
        seen.add(marker)
        stable.append(uuid_value)
    return stable


class _FilteredEvidenceStore:
    def __init__(self, records: list[EvidenceRecord]) -> None:
        self.records = records

    async def list_evidence(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[EvidenceRecord]:
        return self.records[:limit]

    async def derive_from_raw_events(self, **_kwargs: object):
        return EvidenceDeriveResult(scanned=0, created=0, duplicate=0, evidence=[])
