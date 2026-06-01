import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from autoskill.api.app import EmbeddingSearchRequest, EmbeddingUpsertRequest, create_app
from autoskill.db.embeddings import (
    EMBEDDING_DIM,
    EmbeddingRecord,
    EmbeddingSearchCandidate,
    EmbeddingUpsertResult,
)
from fastapi import HTTPException


class MemoryEmbeddingStore:
    def __init__(self) -> None:
        self.embedding: EmbeddingRecord | None = None
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
    ) -> EmbeddingUpsertResult:
        if len(embedding) != EMBEDDING_DIM:
            raise ValueError(f"embedding must have exactly {EMBEDDING_DIM} dimensions")
        record = EmbeddingRecord(
            embedding_id=uuid4(),
            workspace_id=uuid4(),
            workspace_key=workspace_key,
            object_type=object_type,
            object_id=object_id,
            skill_id=skill_id,
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
        object_type: str | None = None,
        limit: int = 10,
    ) -> list[EmbeddingSearchCandidate]:
        if len(embedding) != EMBEDDING_DIM:
            raise ValueError(f"embedding must have exactly {EMBEDDING_DIM} dimensions")
        if self.embedding is None:
            return []
        return [EmbeddingSearchCandidate(embedding=self.embedding, distance=0.0)]


def test_embeddings_api_upserts_and_searches() -> None:
    store = MemoryEmbeddingStore()
    app = create_app(embedding_store=store)
    upsert_route = next(route for route in app.routes if route.path == "/v1/embeddings/upsert")
    search_route = next(route for route in app.routes if route.path == "/v1/embeddings/search")
    object_id = uuid4()
    vector = [0.0] * EMBEDDING_DIM
    vector[0] = 1.0

    async def run() -> tuple[object, object]:
        upserted = await upsert_route.endpoint(
            request=EmbeddingUpsertRequest(
                workspace_id="dev-01",
                object_type="evidence_item",
                object_id=object_id,
                embedding_model="test-embedding-model",
                embedding=vector,
                text="redacted evidence summary",
            )
        )
        searched = await search_route.endpoint(
            request=EmbeddingSearchRequest(
                workspace_id="dev-01",
                embedding_model="test-embedding-model",
                embedding=vector,
            )
        )
        return upserted, searched

    upserted, searched = asyncio.run(run())

    assert upserted.created is True
    assert upserted.embedding["object_id"] == str(object_id)
    assert searched.candidates[0]["distance"] == 0.0


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
                embedding=[0.0],
                text="redacted evidence summary",
            )
        )

    with pytest.raises(HTTPException):
        asyncio.run(run())
