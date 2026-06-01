import asyncio
from uuid import UUID, uuid4

from autoskill.api.app import CandidateProposalRequest, create_app
from autoskill.db.candidates import CandidatePersistResult
from autoskill.db.retrieval import RetrievalCandidate
from autoskill.services.candidates import propose_candidate_skills
from autoskill.services.opportunity import mine_opportunities
from autoskill.tests.test_opportunity import (
    MemoryOpportunityEvidenceStore,
    MemoryOpportunityRetrievalStore,
    evidence_record,
)


class MemoryCandidateStore:
    def __init__(self) -> None:
        self.evolution_transaction_id: UUID | None = None
        self.proposal_count = 0

    async def persist_candidate_proposals(
        self,
        *,
        workspace_key: str,
        proposals: list[object],
        evolution_transaction_id: UUID | None = None,
    ) -> CandidatePersistResult:
        self.evolution_transaction_id = evolution_transaction_id
        self.proposal_count = len(proposals)
        return CandidatePersistResult(
            persisted=1,
            skipped=0,
            candidates=[],
            evolution_transaction_id=evolution_transaction_id,
        )


def test_candidate_proposal_builds_propose_only_skillir() -> None:
    evidence = MemoryOpportunityEvidenceStore(
        [
            evidence_record("message_received", "repair pdf table extraction"),
            evidence_record("message_received", "repair pdf table extraction"),
        ]
    )
    retrieval = MemoryOpportunityRetrievalStore([])

    async def run():
        opportunities = await mine_opportunities(
            evidence,
            retrieval,
            workspace_key="dev-01",
            min_support=2,
        )
        return propose_candidate_skills(opportunities)

    result = asyncio.run(run())
    proposal = result.proposals[0].to_json()

    assert result.proposed == 1
    assert result.skipped == 0
    assert proposal["recommendation"] == "propose_candidate"
    assert proposal["skillir"]["schema"] == "skillir.v1"
    assert proposal["skillir"]["slug"].startswith("autoskill-message-received")
    assert proposal["compiled_sha256"]
    assert proposal["scanner_findings"] == []
    assert [probe["kind"] for probe in proposal["probe_plan"]] == [
        "target",
        "no_skill_control",
        "regression",
    ]
    assert "Do not write files" in proposal["skillir"]["never"][0]


def test_candidate_proposal_skips_duplicate_active_match() -> None:
    evidence = MemoryOpportunityEvidenceStore(
        [
            evidence_record("message_received", "repair pdf table extraction"),
            evidence_record("message_received", "repair pdf table extraction"),
        ]
    )
    retrieval = MemoryOpportunityRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=uuid4(),
                summary="Repeated message received workflow evidence observed.",
                rank=0.8,
                metadata={"lifecycle_state": "active", "slug": "autoskill-message-received"},
            )
        ]
    )

    async def run():
        opportunities = await mine_opportunities(
            evidence,
            retrieval,
            workspace_key="dev-01",
            min_support=2,
        )
        return propose_candidate_skills(opportunities)

    result = asyncio.run(run())
    proposal = result.proposals[0].to_json()

    assert result.proposed == 0
    assert result.skipped == 1
    assert proposal["recommendation"] == "reuse_active"
    assert proposal["skillir"] is None
    assert proposal["skipped_reason"] == "opportunity recommendation is reuse_active"


def test_candidate_proposal_api_uses_opportunity_gate() -> None:
    evidence = MemoryOpportunityEvidenceStore(
        [
            evidence_record("message_received", "repair pdf table extraction"),
            evidence_record("message_received", "repair pdf table extraction"),
        ]
    )
    retrieval = MemoryOpportunityRetrievalStore([])
    app = create_app(evidence_store=evidence, retrieval_store=retrieval)
    route = next(route for route in app.routes if route.path == "/v1/candidates/propose")

    async def run():
        return await route.endpoint(
            request=CandidateProposalRequest(workspace_id="dev-01", min_support=2)
        )

    response = asyncio.run(run())

    assert response.proposed == 1
    assert response.proposals[0]["skillir"]["evidence_ids"]


def test_candidate_proposal_persistence_uses_evolution_transaction() -> None:
    evidence = MemoryOpportunityEvidenceStore(
        [
            evidence_record("message_received", "repair pdf table extraction"),
            evidence_record("message_received", "repair pdf table extraction"),
        ]
    )
    retrieval = MemoryOpportunityRetrievalStore([])
    candidates = MemoryCandidateStore()
    app = create_app(
        evidence_store=evidence,
        retrieval_store=retrieval,
        candidate_store=candidates,
    )
    route = next(route for route in app.routes if route.path == "/v1/candidates/propose")

    async def run():
        return await route.endpoint(
            request=CandidateProposalRequest(workspace_id="dev-01", min_support=2)
        )

    response = asyncio.run(run())

    assert response.proposed == 1
    assert candidates.proposal_count == 1
    assert candidates.evolution_transaction_id is not None
    assert response.persistence is not None
    assert response.persistence["evolution_transaction_id"] == str(
        candidates.evolution_transaction_id
    )
    assert response.persistence["transaction"]["status"] == "staged"
