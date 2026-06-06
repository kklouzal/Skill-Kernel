import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from autoskill.api.app import (
    EmbeddingRecallAuditRequest,
    EmbeddingSearchRequest,
    EmbeddingUpsertRequest,
    create_app,
)
from autoskill.db.embeddings import (
    EMBEDDING_DIM,
    EmbeddingRecallAuditResult,
    EmbeddingRecord,
    EmbeddingSearchCandidate,
    EmbeddingUpsertResult,
)
from fastapi import HTTPException


class MemoryEmbeddingStore:
    def __init__(self) -> None:
        self.embedding: EmbeddingRecord | None = None
        self.calls: list[dict[str, object]] = []
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def upsert_embedding(
        self,
        *,
        workspace_key: str,
        object_type: str,
        object_id,
        embedding_model: str,
        embedding: list[float],
        text: str,
        skill_id=None,
        embedding_profile_id=None,
    ) -> EmbeddingUpsertResult:
        if len(embedding) != EMBEDDING_DIM:
            raise ValueError(f"embedding must have exactly {EMBEDDING_DIM} dimensions")
        self.calls.append(
            {
                "method": "upsert",
                "embedding_profile_id": embedding_profile_id,
                "embedding_model": embedding_model,
            }
        )
        record = EmbeddingRecord(
            embedding_id=uuid4(),
            workspace_id=uuid4(),
            workspace_key=workspace_key,
            object_type=object_type,
            object_id=object_id,
            skill_id=skill_id,
            embedding_profile_id=embedding_profile_id,
            embedding_model=embedding_model,
            embedding_dim=EMBEDDING_DIM,
            text_hash="hash-1",
            created_at=datetime.now(UTC),
        )
        created = self.embedding is None
        self.embedding = record
        return EmbeddingUpsertResult(embedding=record, created=created)

    async def search_embeddings(
        self,
        *,
        workspace_key: str,
        embedding_model: str,
        embedding: list[float],
        embedding_profile_id=None,
        object_type: str | None = None,
        limit: int = 10,
    ) -> list[EmbeddingSearchCandidate]:
        if len(embedding) != EMBEDDING_DIM:
            raise ValueError(f"embedding must have exactly {EMBEDDING_DIM} dimensions")
        self.calls.append(
            {
                "method": "search",
                "embedding_profile_id": embedding_profile_id,
                "embedding_model": embedding_model,
            }
        )
        if self.embedding is None:
            return []
        return [EmbeddingSearchCandidate(embedding=self.embedding, distance=0.0)]

    async def audit_recall(
        self,
        *,
        workspace_key: str,
        embedding_model: str,
        embedding_profile_id=None,
        object_type: str | None = None,
        sample_size: int = 10,
        k: int = 10,
        min_recall: float = 0.95,
    ) -> EmbeddingRecallAuditResult:
        return EmbeddingRecallAuditResult(
            sampled=1,
            k=k,
            min_recall=1.0,
            avg_recall=1.0,
            failures=[],
        )


def test_embeddings_api_upserts_and_searches() -> None:
    store = MemoryEmbeddingStore()
    app = create_app(embedding_store=store)
    upsert_route = next(route for route in app.routes if route.path == "/v1/embeddings/upsert")
    search_route = next(route for route in app.routes if route.path == "/v1/embeddings/search")
    object_id = uuid4()
    profile_id = uuid4()
    vector = [0.0] * EMBEDDING_DIM
    vector[0] = 1.0

    async def run() -> tuple[object, object]:
        upserted = await upsert_route.endpoint(
            request=EmbeddingUpsertRequest(
                workspace_id="dev-01",
                object_type="evidence_item",
                object_id=object_id,
                embedding_model="test-embedding-model",
                embedding_profile_id=profile_id,
                embedding=vector,
                text="redacted evidence summary",
            )
        )
        searched = await search_route.endpoint(
            request=EmbeddingSearchRequest(
                workspace_id="dev-01",
                embedding_model="test-embedding-model",
                embedding_profile_id=profile_id,
                embedding=vector,
            )
        )
        return upserted, searched

    upserted, searched = asyncio.run(run())

    assert upserted.created is True
    assert upserted.embedding["object_id"] == str(object_id)
    assert upserted.embedding["embedding_profile_id"] == str(profile_id)
    assert searched.candidates[0]["distance"] == 0.0


def test_embeddings_api_rejects_profileless_direct_operations() -> None:
    store = MemoryEmbeddingStore()
    app = create_app(embedding_store=store)
    upsert_route = next(route for route in app.routes if route.path == "/v1/embeddings/upsert")
    search_route = next(route for route in app.routes if route.path == "/v1/embeddings/search")
    audit_route = next(route for route in app.routes if route.path == "/v1/embeddings/recall-audit")
    vector = [0.0] * EMBEDDING_DIM
    vector[0] = 1.0

    async def run_upsert() -> None:
        await upsert_route.endpoint(
            request=EmbeddingUpsertRequest(
                workspace_id="dev-01",
                object_type="evidence_item",
                object_id=uuid4(),
                embedding_model="test-embedding-model",
                embedding=vector,
                text="redacted evidence summary",
            )
        )

    async def run_search() -> None:
        await search_route.endpoint(
            request=EmbeddingSearchRequest(
                workspace_id="dev-01",
                embedding_model="test-embedding-model",
                embedding=vector,
            )
        )

    async def run_audit() -> None:
        await audit_route.endpoint(
            request=EmbeddingRecallAuditRequest(
                workspace_id="dev-01",
                embedding_model="test-embedding-model",
            )
        )

    for operation in (run_upsert, run_search, run_audit):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(operation())
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == (
            "embedding_profile_id is required for direct vector operations"
        )

    assert store.calls == []


def test_embeddings_api_can_scope_to_embedding_profile_id() -> None:
    store = MemoryEmbeddingStore()
    app = create_app(embedding_store=store)
    upsert_route = next(route for route in app.routes if route.path == "/v1/embeddings/upsert")
    search_route = next(route for route in app.routes if route.path == "/v1/embeddings/search")
    object_id = uuid4()
    profile_id = uuid4()
    vector = [0.0] * EMBEDDING_DIM
    vector[0] = 1.0

    async def run() -> None:
        await upsert_route.endpoint(
            request=EmbeddingUpsertRequest(
                workspace_id="dev-01",
                object_type="evidence_item",
                object_id=object_id,
                embedding_model="shared-model-name",
                embedding_profile_id=profile_id,
                embedding=vector,
                text="redacted evidence summary",
            )
        )
        await search_route.endpoint(
            request=EmbeddingSearchRequest(
                workspace_id="dev-01",
                embedding_model="shared-model-name",
                embedding_profile_id=profile_id,
                embedding=vector,
            )
        )

    asyncio.run(run())

    assert store.calls == [
        {
            "method": "upsert",
            "embedding_profile_id": profile_id,
            "embedding_model": "shared-model-name",
        },
        {
            "method": "search",
            "embedding_profile_id": profile_id,
            "embedding_model": "shared-model-name",
        },
    ]


def test_embeddings_api_runs_recall_audit() -> None:
    store = MemoryEmbeddingStore()
    app = create_app(embedding_store=store)
    audit_route = next(route for route in app.routes if route.path == "/v1/embeddings/recall-audit")
    profile_id = uuid4()

    async def run():
        return await audit_route.endpoint(
            request=EmbeddingRecallAuditRequest(
                workspace_id="dev-01",
                embedding_model="test-embedding-model",
                embedding_profile_id=profile_id,
                sample_size=3,
                k=5,
            )
        )

    response = asyncio.run(run())

    assert response.sampled == 1
    assert response.k == 5
    assert response.failures == []


def test_embeddings_api_rejects_wrong_dimensions() -> None:
    store = MemoryEmbeddingStore()
    app = create_app(embedding_store=store)
    upsert_route = next(route for route in app.routes if route.path == "/v1/embeddings/upsert")

    async def run() -> None:
        await upsert_route.endpoint(
            request=EmbeddingUpsertRequest(
                workspace_id="dev-01",
                object_type="evidence_item",
                object_id=uuid4(),
                embedding_model="test-embedding-model",
                embedding_profile_id=uuid4(),
                embedding=[0.0],
                text="redacted evidence summary",
            )
        )

    with pytest.raises(HTTPException):
        asyncio.run(run())
