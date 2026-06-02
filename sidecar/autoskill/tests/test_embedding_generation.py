import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
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
from fastapi import HTTPException


class MemoryPendingEmbeddingStore:
    def __init__(self, *, expected_embedding_dim: int = EMBEDDING_DIM) -> None:
        self.expected_embedding_dim = expected_embedding_dim
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
        embedding_profile_id=None,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[EmbeddingSourceText]:
        assert embedding_model
        self.last_profile_id = embedding_profile_id
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
        embedding_profile_id=None,
    ) -> EmbeddingUpsertResult:
        assert len(embedding) == self.expected_embedding_dim
        assert any(value != 0.0 for value in embedding)
        self.upserts.append(
            {
                "workspace_key": workspace_key,
                "object_type": object_type,
                "object_id": object_id,
                "embedding_model": embedding_model,
                "embedding_profile_id": embedding_profile_id,
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
                embedding_profile_id=embedding_profile_id,
                embedding_model=embedding_model,
                embedding_dim=len(embedding),
                text_hash="stored-hash",
                created_at=datetime.now(UTC),
            ),
            created=True,
        )

    async def search_embeddings(self, **_kwargs):
        return []


class MemoryEmbeddingProfileStore:
    def __init__(self, *, profile=None, active_profile=None) -> None:
        self.profile = profile
        self.active_profile = active_profile
        self.calls: list[dict[str, object]] = []
        self.active_calls: list[dict[str, object]] = []

    async def get_embedding_profile(self, *, workspace_key: str, profile_key: str):
        self.calls.append({"workspace_key": workspace_key, "profile_key": profile_key})
        return self.profile

    async def get_active_embedding_profile(self, *, workspace_key: str):
        self.active_calls.append({"workspace_key": workspace_key})
        return self.active_profile


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
    assert store.upserts[0]["embedding_profile_id"] is None
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


def test_generate_embeddings_api_uses_qualified_embedding_profile() -> None:
    store = MemoryPendingEmbeddingStore()
    profile_id = uuid4()
    profile_store = MemoryEmbeddingProfileStore(
        profile=SimpleNamespace(
            profile_id=profile_id,
            status="qualified",
            embedding_dim=1536,
            route_kind="hash",
            model="qualified-hash-profile",
            timeout_seconds=30.0,
        )
    )
    app = create_app(embedding_store=store, profile_store=profile_store)
    route = next(route for route in app.routes if route.path == "/v1/embeddings/generate")

    async def run():
        return await route.endpoint(
            request=EmbeddingGenerateRequest(
                workspace_id="dev-01",
                embedding_profile_key="embedding-default",
                limit=1,
            ),
        )

    response = asyncio.run(run())

    assert response.generated == 1
    assert response.embedding_model == "qualified-hash-profile"
    assert response.embedding_profile_id == str(profile_id)
    assert response.embedding_dim == 1536
    assert store.upserts[0]["embedding_model"] == "qualified-hash-profile"
    assert store.upserts[0]["embedding_profile_id"] == profile_id
    assert store.last_profile_id == profile_id
    assert profile_store.calls == [
        {"workspace_key": "dev-01", "profile_key": "embedding-default"}
    ]


def test_generate_embeddings_api_prefers_active_embedding_profile() -> None:
    store = MemoryPendingEmbeddingStore(expected_embedding_dim=8)
    profile_id = uuid4()
    profile_store = MemoryEmbeddingProfileStore(
        active_profile=SimpleNamespace(
            profile_id=profile_id,
            status="active",
            qualification={"verdict": "qualified"},
            embedding_dim=8,
            route_kind="hash",
            model="active-hash-profile",
            timeout_seconds=30.0,
        )
    )
    app = create_app(embedding_store=store, profile_store=profile_store)
    route = next(route for route in app.routes if route.path == "/v1/embeddings/generate")

    async def run():
        return await route.endpoint(
            request=EmbeddingGenerateRequest(workspace_id="dev-01", limit=1),
        )

    response = asyncio.run(run())

    assert response.generated == 1
    assert response.embedding_model == "active-hash-profile"
    assert response.embedding_profile_id == str(profile_id)
    assert store.upserts[0]["embedding_profile_id"] == profile_id
    assert profile_store.active_calls == [{"workspace_key": "dev-01"}]


def test_generate_embeddings_api_uses_qualified_non_default_embedding_dimension() -> None:
    store = MemoryPendingEmbeddingStore(expected_embedding_dim=8)
    profile_id = uuid4()
    profile_store = MemoryEmbeddingProfileStore(
        profile=SimpleNamespace(
            profile_id=profile_id,
            status="qualified",
            embedding_dim=8,
            route_kind="hash",
            model="qualified-small-hash-profile",
            timeout_seconds=30.0,
        )
    )
    app = create_app(embedding_store=store, profile_store=profile_store)
    route = next(route for route in app.routes if route.path == "/v1/embeddings/generate")

    async def run():
        return await route.endpoint(
            request=EmbeddingGenerateRequest(
                workspace_id="dev-01",
                embedding_profile_key="embedding-small",
                limit=1,
            ),
        )

    response = asyncio.run(run())

    assert response.generated == 1
    assert response.embedding_model == "qualified-small-hash-profile"
    assert response.embedding_profile_id == str(profile_id)
    assert response.embedding_dim == 8
    assert store.upserts[0]["embedding_profile_id"] == profile_id


def test_generate_embeddings_api_rejects_unqualified_embedding_profile() -> None:
    profile_store = MemoryEmbeddingProfileStore(
        profile=SimpleNamespace(
            profile_id=uuid4(),
            status="candidate",
            embedding_dim=1536,
            route_kind="hash",
            model="candidate-hash-profile",
            timeout_seconds=30.0,
        )
    )
    app = create_app(
        embedding_store=MemoryPendingEmbeddingStore(),
        profile_store=profile_store,
    )
    route = next(route for route in app.routes if route.path == "/v1/embeddings/generate")

    async def run():
        return await route.endpoint(
            request=EmbeddingGenerateRequest(
                workspace_id="dev-01",
                embedding_profile_key="embedding-default",
            ),
        )

    with pytest.raises(HTTPException) as error:
        asyncio.run(run())

    assert error.value.status_code == 409
    assert error.value.detail == "embedding profile is not qualified"
