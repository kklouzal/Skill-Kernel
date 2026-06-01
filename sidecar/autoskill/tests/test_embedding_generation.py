import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from autoskill.api.app import EmbeddingGenerateRequest, create_app
from autoskill.db.embeddings import (
    EMBEDDING_DIM,
    EmbeddingRecord,
    EmbeddingSourceText,
    EmbeddingUpsertResult,
)
from autoskill.services.embedding_generation import (
    DEFAULT_EMBEDDING_MODEL,
    HashingTextEmbedder,
    generate_pending_embeddings,
)


class MemoryPendingEmbeddingStore:
    def __init__(self) -> None:
        self.sources = [
            EmbeddingSourceText(
                object_type="evidence_item",
                object_id=uuid4(),
                workspace_key="dev-01",
                skill_id=None,
                text="Observed redacted workflow evidence.",
                text_hash="source-hash-1",
            ),
            EmbeddingSourceText(
                object_type="body_index_document",
                object_id=uuid4(),
                workspace_key="dev-01",
                skill_id=uuid4(),
                text="WHEN this skill applies, verify the deterministic gate.",
                text_hash="source-hash-2",
            ),
        ]
        self.upserts: list[dict[str, object]] = []

    async def list_unembedded_sources(
        self,
        *,
        embedding_model: str,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[EmbeddingSourceText]:
        assert embedding_model == DEFAULT_EMBEDDING_MODEL
        assert workspace_key in {None, "dev-01"}
        return self.sources[:limit]

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
        assert len(embedding) == EMBEDDING_DIM
        assert any(value != 0.0 for value in embedding)
        self.upserts.append(
            {
                "workspace_key": workspace_key,
                "object_type": object_type,
                "object_id": object_id,
                "embedding_model": embedding_model,
                "skill_id": skill_id,
                "text": text,
            }
        )
        return EmbeddingUpsertResult(
            embedding=EmbeddingRecord(
                embedding_id=uuid4(),
                workspace_id=uuid4(),
                workspace_key=workspace_key,
                object_type=object_type,
                object_id=object_id,
                skill_id=skill_id,
                embedding_model=embedding_model,
                embedding_dim=EMBEDDING_DIM,
                text_hash="stored-hash",
                created_at=datetime.now(UTC),
            ),
            created=True,
        )

    async def search_embeddings(self, **_kwargs):
        return []


def test_hashing_text_embedder_is_deterministic_and_normalized() -> None:
    embedder = HashingTextEmbedder()

    first = embedder.embed("redacted evidence")
    second = embedder.embed("redacted evidence")
    different = embedder.embed("different redacted evidence")

    assert first == second
    assert first != different
    assert len(first) == EMBEDDING_DIM
    assert 0.99 < sum(value * value for value in first) < 1.01


def test_generate_pending_embeddings_upserts_all_sources() -> None:
    store = MemoryPendingEmbeddingStore()

    result = asyncio.run(generate_pending_embeddings(store, workspace_key="dev-01", limit=10))

    assert result.scanned == 2
    assert result.generated == 2
    assert result.created == 2
    assert result.updated == 0
    assert len(store.upserts) == 2
    assert store.upserts[0]["object_type"] == "evidence_item"
    assert store.upserts[1]["skill_id"] is not None


def test_generate_embeddings_api_runs_control_primitive() -> None:
    store = MemoryPendingEmbeddingStore()
    app = create_app(embedding_store=store)
    route = next(route for route in app.routes if route.path == "/v1/embeddings/generate")

    async def run():
        return await route.endpoint(
            request=EmbeddingGenerateRequest(workspace_id="dev-01", limit=1),
        )

    response = asyncio.run(run())

    assert response.generated == 1
    assert response.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert response.sources[0]["object_type"] == "evidence_item"
