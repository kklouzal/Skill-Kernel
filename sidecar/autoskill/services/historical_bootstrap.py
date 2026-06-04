from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autoskill.db.evidence import EvidenceRecord, EvidenceStore
from autoskill.db.retrieval import RetrievalStore
from autoskill.services.candidates import CandidateProposalResult, propose_candidate_skills
from autoskill.services.opportunity import OpportunityMineResult, mine_opportunities


@dataclass(frozen=True)
class HistoricalBootstrapConsolidationResult:
    scanned: int
    historical_scanned: int
    opportunities: OpportunityMineResult
    proposals: CandidateProposalResult

    def to_json(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "historical_scanned": self.historical_scanned,
            "opportunities": self.opportunities.to_json(),
            "proposals": self.proposals.to_json(),
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
    return HistoricalBootstrapConsolidationResult(
        scanned=len(records),
        historical_scanned=len(historical_records),
        opportunities=opportunities,
        proposals=proposals,
    )


def _historical_bootstrap_evidence(record: EvidenceRecord) -> bool:
    if not isinstance(record.payload, dict):
        return False
    if record.kind == "historical_chunk_observation":
        return True
    if record.kind != "recurring_evidence_cluster":
        return False
    return any(str(item).startswith("historical") for item in record.taint)


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
        raise NotImplementedError
