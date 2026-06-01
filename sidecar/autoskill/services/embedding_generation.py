from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import sqrt
from typing import Protocol

from autoskill.db.embeddings import EMBEDDING_DIM, EmbeddingStore

DEFAULT_EMBEDDING_MODEL = "autoskill-hash-embedding.v1"


class TextEmbedder(Protocol):
    model: str

    def embed(self, text: str) -> list[float]:
        """Return one fixed-dimension embedding for already-redacted text."""


class HashingTextEmbedder:
    model = DEFAULT_EMBEDDING_MODEL

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
