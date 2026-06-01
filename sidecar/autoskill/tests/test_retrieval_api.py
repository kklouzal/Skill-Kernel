import asyncio
from uuid import uuid4

from autoskill.api.app import RetrievalQueryRequest, create_app
from autoskill.db.retrieval import RetrievalCandidate, RetrievalResult


class MemoryRetrievalStore:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def lexical_query(
        self,
        *,
        workspace_key: str,
        query: str,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
    ) -> RetrievalResult:
        self.queries.append(query)
        if not query.strip():
            return RetrievalResult(
                retrieval_log_id=None,
                decision="empty_query",
                candidates=[],
            )
        candidate = RetrievalCandidate(
            object_type="evidence_item",
            object_id=uuid4(),
            skill_id=None,
            summary="Observed redacted tool_call_end event from openclaw-plugin in s/t.",
            rank=0.5,
            metadata={"kind": "event_observation", "maturity": "observed"},
        )
        return RetrievalResult(
            retrieval_log_id=uuid4(),
            decision="candidates_found",
            candidates=[candidate],
        )


def test_retrieval_query_api_returns_candidates() -> None:
    store = MemoryRetrievalStore()
    app = create_app(retrieval_store=store)
    route = next(route for route in app.routes if route.path == "/v1/retrieval/query")

    async def run() -> object:
        return await route.endpoint(
            request=RetrievalQueryRequest(
                workspace_id="dev-01",
                query="tool call",
                session_id="session-1",
                turn_id="turn-1",
            )
        )

    result = asyncio.run(run())

    assert result.decision == "candidates_found"
    assert result.retrieval_log_id is not None
    assert result.candidates[0]["object_type"] == "evidence_item"
    assert result.candidates[0]["metadata"]["maturity"] == "observed"
    assert store.queries == ["tool call"]


def test_retrieval_query_api_handles_empty_queries() -> None:
    store = MemoryRetrievalStore()
    app = create_app(retrieval_store=store)
    route = next(route for route in app.routes if route.path == "/v1/retrieval/query")

    async def run() -> object:
        return await route.endpoint(
            request=RetrievalQueryRequest(workspace_id="dev-01", query="   ")
        )

    result = asyncio.run(run())

    assert result.decision == "empty_query"
    assert result.retrieval_log_id is None
    assert result.candidates == []
