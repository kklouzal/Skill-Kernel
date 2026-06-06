import asyncio
from uuid import uuid4

from autoskill.api.app import RetrievalQueryRequest, create_app
from autoskill.db.retrieval import RetrievalCandidate, RetrievalResult


class MemoryRetrievalStore:
    def __init__(self) -> None:
        self.queries: list[dict[str, object]] = []
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def lexical_query(
        self,
        *,
        workspace_key: str,
        query: str,
        trace_id=None,
        span_id=None,
        parent_span_id=None,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
        record_decision: bool = True,
    ) -> RetrievalResult:
        self.queries.append(
            {
                "query": query,
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
            }
        )
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

    async def expand_skill_graph(
        self,
        *,
        workspace_key: str,
        skill_ids: list,
        edge_kinds: list[str] | None = None,
        limit: int = 25,
    ) -> list[RetrievalCandidate]:
        return []

    async def record_context_hint(
        self,
        *,
        retrieval_log_id,
        rendered_skill_ids: list,
        decision: str,
        suppressed: list[dict[str, object]],
        reason_codes: list[str],
    ) -> None:
        return None


def test_retrieval_query_api_returns_candidates() -> None:
    store = MemoryRetrievalStore()
    app = create_app(retrieval_store=store)
    route = next(route for route in app.routes if route.path == "/v1/retrieval/query")
    trace_id = uuid4()
    span_id = uuid4()

    async def run() -> object:
        return await route.endpoint(
            request=RetrievalQueryRequest(
                workspace_id="dev-01",
                query="tool call",
                trace_id=trace_id,
                span_id=span_id,
                session_id="session-1",
                turn_id="turn-1",
            )
        )

    result = asyncio.run(run())

    assert result.decision == "candidates_found"
    assert result.retrieval_log_id is not None
    assert result.candidates[0]["object_type"] == "evidence_item"
    assert result.candidates[0]["metadata"]["maturity"] == "observed"
    assert store.queries == [
        {
            "query": "tool call",
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": None,
        }
    ]


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
