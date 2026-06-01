import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
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
    OpenAICompatibleTextEmbedder,
    build_text_embedder_from_settings,
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
        assert embedding_model
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


def test_embedder_factory_uses_hash_provider() -> None:
    embedder = build_text_embedder_from_settings(
        SimpleNamespace(embedding_provider="hash", embedding_model="custom-hash-model")
    )

    assert isinstance(embedder, HashingTextEmbedder)
    assert embedder.model == "custom-hash-model"


def test_openai_compatible_embedder_posts_embedding_request(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps({"data": [{"embedding": [1.0] + [0.0] * 1535}]}).encode()

    def fake_urlopen(http_request, timeout):
        captured["url"] = http_request.full_url
        captured["timeout"] = timeout
        captured["authorization"] = http_request.headers["Authorization"]
        captured["payload"] = json.loads(http_request.data.decode())
        return FakeResponse()

    monkeypatch.setattr("autoskill.services.embedding_generation.request.urlopen", fake_urlopen)
    embedder = OpenAICompatibleTextEmbedder(
        base_url="http://127.0.0.1:9999/v1/",
        api_key="test-key",
        model="text-embedding-3-small",
        timeout_seconds=12.5,
    )

    embedding = embedder.embed("redacted text")

    assert len(embedding) == 1536
    assert captured == {
        "url": "http://127.0.0.1:9999/v1/embeddings",
        "timeout": 12.5,
        "authorization": "Bearer test-key",
        "payload": {"model": "text-embedding-3-small", "input": "redacted text"},
    }


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
