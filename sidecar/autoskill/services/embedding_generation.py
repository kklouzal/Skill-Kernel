from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from math import sqrt
from typing import Protocol
from urllib import request

from autoskill.db.embeddings import EMBEDDING_DIM, EmbeddingStore

DEFAULT_EMBEDDING_MODEL = "autoskill-hash-embedding.v1"


class TextEmbedder(Protocol):
    model: str

    def embed(self, text: str) -> list[float]:
        """Return one fixed-dimension embedding for already-redacted text."""


class HashingTextEmbedder:
    def __init__(self, *, model: str = DEFAULT_EMBEDDING_MODEL) -> None:
        self.model = model

    def embed(self, text: str) -> list[float]:
        values: list[float] = []
        seed = text.encode("utf-8")
        for index in range(EMBEDDING_DIM):
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
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def embed(self, text: str) -> list[float]:
        payload = json.dumps({"model": self.model, "input": text}).encode("utf-8")
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
        if len(embedding) != EMBEDDING_DIM:
            raise ValueError(
                f"embedding provider returned {len(embedding)} dimensions; expected {EMBEDDING_DIM}"
            )
        return [float(value) for value in embedding]


def build_text_embedder_from_settings(settings: object) -> TextEmbedder:
    provider = str(getattr(settings, "embedding_provider", "hash"))
    model = str(getattr(settings, "embedding_model", DEFAULT_EMBEDDING_MODEL))
    if provider == "hash":
        return HashingTextEmbedder(model=model)
    if provider == "openai_compatible":
        base_url = getattr(settings, "embedding_api_base_url", None)
        api_key = getattr(settings, "embedding_api_key", None)
        if not base_url or not api_key:
            raise ValueError(
                "embedding_api_base_url and embedding_api_key are required for openai_compatible"
            )
        return OpenAICompatibleTextEmbedder(
            base_url=str(base_url),
            api_key=str(api_key),
            model=model,
            timeout_seconds=float(getattr(settings, "embedding_timeout_seconds", 30.0)),
        )
    raise ValueError(f"unsupported embedding provider: {provider}")


@dataclass(frozen=True)
class EmbeddingGenerationResult:
    scanned: int
    generated: int
    created: int
    updated: int
    embedding_model: str
    sources: list[dict[str, object]]

    def to_json(self) -> dict[str, object]:
        return {
            "scanned": self.scanned,
            "generated": self.generated,
            "created": self.created,
            "updated": self.updated,
            "embedding_model": self.embedding_model,
            "sources": self.sources,
        }


async def generate_pending_embeddings(
    store: EmbeddingStore,
    *,
    embedder: TextEmbedder | None = None,
    embedding_model: str | None = None,
    workspace_key: str | None = None,
    limit: int = 100,
) -> EmbeddingGenerationResult:
    selected_embedder = embedder or HashingTextEmbedder()
    model = embedding_model or selected_embedder.model
    sources = await store.list_unembedded_sources(
        embedding_model=model,
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
        sources=source_summaries,
    )
