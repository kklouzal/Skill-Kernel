import asyncio
from uuid import uuid4

from autoskill.db.retrieval import RetrievalCandidate, RetrievalResult
from autoskill.services.broker import ContextHintRequest, build_context_hint


class MemoryBrokerRetrievalStore:
    def __init__(self, candidates: list[RetrievalCandidate]) -> None:
        self.candidates = candidates
        self.calls: list[dict[str, object]] = []

    async def lexical_query(
        self,
        *,
        workspace_key: str,
        query: str,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
    ) -> RetrievalResult:
        self.calls.append(
            {
                "workspace_key": workspace_key,
                "query": query,
                "session_id": session_id,
                "turn_id": turn_id,
                "limit": limit,
            }
        )
        return RetrievalResult(
            retrieval_log_id=uuid4(),
            decision="candidates_found" if self.candidates else "no_candidates",
            candidates=self.candidates,
        )


def test_context_broker_renders_scanned_skill_candidates() -> None:
    skill_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="WHEN PDF tables are malformed, use the deterministic repair workflow.",
                rank=0.9,
                metadata={"secret_scan_status": "passed"},
            ),
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="Duplicate body for the same skill should be suppressed.",
                rank=0.8,
                metadata={"secret_scan_status": "passed"},
            ),
        ]
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                session_id="session-1",
                turn_id="turn-1",
                user_intent="repair pdf table extraction",
                max_tokens=120,
            ),
        )

    response = asyncio.run(run())

    assert response.decision == "skill_hint"
    assert response.skill_ids == [str(skill_id)]
    assert "AutoSkill broker hint" in response.hint
    assert "PDF tables" in response.hint
    assert response.suppressed[0]["reason"] == "duplicate-skill"
    assert store.calls[0]["limit"] == 8


def test_context_broker_defers_evidence_only_matches() -> None:
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="evidence_item",
                object_id=uuid4(),
                skill_id=None,
                summary="Observed raw evidence should not be injected into prompt context.",
                rank=0.6,
                metadata={"maturity": "observed"},
            )
        ]
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(workspace_id="dev-01", user_intent="raw evidence"),
        )

    response = asyncio.run(run())

    assert response.decision == "defer_skill"
    assert response.hint == ""
    assert response.cache_status == "evidence-only"
    assert response.suppressed[0]["reason"] == "not-runtime-skill"


def test_context_broker_blocks_unscanned_body_documents() -> None:
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=uuid4(),
                summary="This candidate lacks a passing scan.",
                rank=0.6,
                metadata={"secret_scan_status": "pending"},
            )
        ]
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(workspace_id="dev-01", user_intent="candidate"),
        )

    response = asyncio.run(run())

    assert response.decision == "defer_skill"
    assert response.skill_ids == []
    assert response.suppressed[0]["reason"] == "secret-scan-not-passed"
