from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from math import sqrt
from typing import Protocol
from urllib import request
from uuid import UUID

from autoskill.db.embeddings import EMBEDDING_DIM, EmbeddingStore

DEFAULT_EMBEDDING_MODEL = "autoskill-hash-embedding.v1"
PRODUCTION_EMBEDDING_PROVIDERS = {"openclaw", "openai_compatible"}
HASH_EMBEDDING_DEGRADED_REASON = "hash_embedding_provider_test_mode"
EMBEDDING_ENDPOINT_MISSING_REASON = "embedding_endpoint_not_configured"
OPENCLAW_EMBEDDING_ROUTE_UNAVAILABLE_REASON = "openclaw_embedding_route_unavailable"


class TextEmbedder(Protocol):
    model: str
    embedding_dim: int

    def embed(self, text: str) -> list[float]:
        """Return one fixed-dimension embedding for already-redacted text."""


class HashingTextEmbedder:
    def __init__(
        self,
        *,
        model: str = DEFAULT_EMBEDDING_MODEL,
        embedding_dim: int = EMBEDDING_DIM,
    ) -> None:
        self.model = model
        self.embedding_dim = embedding_dim

    def embed(self, text: str) -> list[float]:
        values: list[float] = []
        seed = text.encode("utf-8")
        for index in range(self.embedding_dim):
            digest = sha256(seed + b"\0" + str(index).encode("ascii")).digest()
            integer = int.from_bytes(digest[:8], "big", signed=False)
            values.append((integer / ((1 << 64) - 1)) * 2.0 - 1.0)

        magnitude = sqrt(sum(value * value for value in values))
        if magnitude == 0.0:
            values[0] = 1.0
            return values
        return [value / magnitude for value in values]


class OpenAICompatibleTextEmbedder:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        embedding_dim: int = EMBEDDING_DIM,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.embedding_dim = embedding_dim
        self.timeout_seconds = timeout_seconds

    def embed(self, text: str) -> list[float]:
        payload = json.dumps(
            {
                "model": self.model,
                "input": text,
                "dimensions": self.embedding_dim,
            }
        ).encode("utf-8")
        http_request = request.Request(
            f"{self.base_url}/embeddings",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        embedding = body["data"][0]["embedding"]
        if len(embedding) != self.embedding_dim:
            raise ValueError(
                "embedding provider returned "
                f"{len(embedding)} dimensions; expected {self.embedding_dim}"
            )
        return [float(value) for value in embedding]


@dataclass(frozen=True)
class EmbeddingProviderPolicy:
    provider: str
    production_ready: bool
    degraded: bool
    reason_code: str | None
    jobs_paused: bool


def embedding_provider_policy(settings: object) -> EmbeddingProviderPolicy:
    provider = str(getattr(settings, "embedding_provider", "hash"))
    if provider == "hash":
        return EmbeddingProviderPolicy(
            provider=provider,
            production_ready=False,
            degraded=True,
            reason_code=HASH_EMBEDDING_DEGRADED_REASON,
            jobs_paused=True,
        )
    if provider == "openai_compatible":
        ready = bool(
            getattr(settings, "embedding_api_base_url", None)
            and getattr(settings, "embedding_api_key", None)
        )
        return EmbeddingProviderPolicy(
            provider=provider,
            production_ready=ready,
            degraded=not ready,
            reason_code=None if ready else EMBEDDING_ENDPOINT_MISSING_REASON,
            jobs_paused=not ready,
        )
    if provider == "openclaw":
        return EmbeddingProviderPolicy(
            provider=provider,
            production_ready=False,
            degraded=True,
            reason_code=OPENCLAW_EMBEDDING_ROUTE_UNAVAILABLE_REASON,
            jobs_paused=True,
        )
    return EmbeddingProviderPolicy(
        provider=provider,
        production_ready=False,
        degraded=True,
        reason_code=f"unsupported_embedding_provider:{provider}",
        jobs_paused=True,
    )


def build_text_embedder_from_settings(
    settings: object,
    *,
    allow_degraded_hash: bool | None = None,
) -> TextEmbedder:
    provider = str(getattr(settings, "embedding_provider", "hash"))
    model = str(getattr(settings, "embedding_model", DEFAULT_EMBEDDING_MODEL))
    if provider == "hash":
        allow_hash = (
            bool(getattr(settings, "embedding_hash_provider_allowed", False))
            if allow_degraded_hash is None
            else allow_degraded_hash
        )
        if not allow_hash:
            raise ValueError(
                "hash embedding provider is test/dev-only degraded mode; configure "
                "an openclaw or openai_compatible embedding profile for production "
                "embedding generation"
            )
        return HashingTextEmbedder(model=model)
    if provider == "openai_compatible":
        base_url = getattr(settings, "embedding_api_base_url", None)
        api_key = getattr(settings, "embedding_api_key", None)
        embedding_dim = int(getattr(settings, "embedding_dim", EMBEDDING_DIM) or EMBEDDING_DIM)
        if not base_url or not api_key:
            raise ValueError(
                "embedding_api_base_url and embedding_api_key are required for openai_compatible"
            )
        return OpenAICompatibleTextEmbedder(
            base_url=str(base_url),
            api_key=str(api_key),
            model=model,
            embedding_dim=embedding_dim,
            timeout_seconds=float(getattr(settings, "embedding_timeout_seconds", 30.0)),
        )
    raise ValueError(f"unsupported embedding provider: {provider}")


def build_text_embedder_from_profile(
    profile: object,
    *,
    embedding_api_key: str | None = None,
    embedding_api_base_url: str | None = None,
    allow_degraded_hash: bool = False,
) -> TextEmbedder:
    status = getattr(profile, "status", None)
    qualification = getattr(profile, "qualification", {}) or {}
    if status not in {"qualified", "active"}:
        raise ValueError("embedding profile is not qualified")
    if status == "active" and qualification.get("verdict") not in {None, "qualified"}:
        raise ValueError("active embedding profile has a failing qualification verdict")
    route_kind = str(getattr(profile, "route_kind", ""))
    model = str(getattr(profile, "model", ""))
    embedding_dim = int(getattr(profile, "embedding_dim", 0) or 0)
    if embedding_dim <= 0:
        raise ValueError("embedding profile must declare a positive embedding_dim")
    if route_kind == "hash":
        if not allow_degraded_hash:
            raise ValueError(
                "hash embedding profile is test/dev-only degraded mode; configure "
                "an openclaw or openai_compatible embedding profile"
            )
        return HashingTextEmbedder(model=model, embedding_dim=embedding_dim)
    if route_kind == "openai_compatible":
        base_url = getattr(profile, "endpoint_ref", None) or embedding_api_base_url
        if not base_url or not embedding_api_key:
            raise ValueError(
                "qualified openai_compatible profile requires endpoint and API key"
            )
        return OpenAICompatibleTextEmbedder(
            base_url=str(base_url),
            api_key=embedding_api_key,
            model=model,
            embedding_dim=embedding_dim,
            timeout_seconds=float(getattr(profile, "timeout_seconds", 30.0)),
        )
    raise ValueError(f"embedding profile route_kind is not supported: {route_kind}")


@dataclass(frozen=True)
class EmbeddingGenerationResult:
    scanned: int
    generated: int
    created: int
    updated: int
    embedding_model: str
    embedding_profile_id: str | None
    embedding_dim: int
    sources: list[dict[str, object]]

    def to_json(self) -> dict[str, object]:
        return {
            "scanned": self.scanned,
            "generated": self.generated,
            "created": self.created,
            "updated": self.updated,
            "embedding_model": self.embedding_model,
            "embedding_profile_id": self.embedding_profile_id,
            "embedding_dim": self.embedding_dim,
            "sources": self.sources,
        }


async def generate_pending_embeddings(
    store: EmbeddingStore,
    *,
    embedder: TextEmbedder | None = None,
    embedding_model: str | None = None,
    embedding_profile_id: UUID | None = None,
    workspace_key: str | None = None,
    limit: int = 100,
) -> EmbeddingGenerationResult:
    if embedder is None:
        raise ValueError("embedding generation requires an explicit text embedder")
    selected_embedder = embedder
    model = embedding_model or selected_embedder.model
    sources = await store.list_unembedded_sources(
        embedding_model=model,
        embedding_profile_id=embedding_profile_id,
        workspace_key=workspace_key,
        limit=limit,
    )

    created = 0
    updated = 0
    source_summaries: list[dict[str, object]] = []
    for source in sources:
        result = await store.upsert_embedding(
            workspace_key=source.workspace_key,
            object_type=source.object_type,
            object_id=source.object_id,
            skill_id=source.skill_id,
            embedding_model=model,
            embedding=selected_embedder.embed(source.text),
            text=source.text,
            embedding_profile_id=embedding_profile_id,
        )
        if result.created:
            created += 1
        else:
            updated += 1
        source_summaries.append(source.to_json())

    return EmbeddingGenerationResult(
        scanned=len(sources),
        generated=len(sources),
        created=created,
        updated=updated,
        embedding_model=model,
        embedding_profile_id=str(embedding_profile_id) if embedding_profile_id else None,
        embedding_dim=selected_embedder.embedding_dim,
        sources=source_summaries,
    )
