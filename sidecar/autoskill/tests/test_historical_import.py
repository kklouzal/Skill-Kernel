import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from autoskill.api.app import (
    HistoricalImportChunkItem,
    HistoricalImportChunkRecordRequest,
    HistoricalImportSourceItem,
    HistoricalImportSourceUpsertRequest,
    create_app,
)
from autoskill.core.redaction import redact_text
from autoskill.db.historical import (
    HistoricalChunkInput,
    HistoricalChunkRecord,
    HistoricalChunkRecordResult,
    HistoricalImportStore,
    HistoricalSourceInput,
    HistoricalSourceRecord,
    HistoricalSourceUpsertResult,
)


class MemoryHistoricalImportStore(HistoricalImportStore):
    def __init__(self) -> None:
        self.sources: dict[tuple[str, str, str, str], HistoricalSourceRecord] = {}
        self.chunks: dict[tuple[str, str, str, str, int, str], HistoricalChunkRecord] = {}

    async def upsert_sources(
        self,
        *,
        workspace_key: str,
        sources: list[HistoricalSourceInput],
    ) -> HistoricalSourceUpsertResult:
        created = 0
        updated = 0
        now = datetime.now(UTC)
        records: list[HistoricalSourceRecord] = []
        for source in sources:
            key = (
                workspace_key,
                source.source_kind,
                source.source_key,
                source.fingerprint,
            )
            existing = self.sources.get(key)
            if existing is None:
                created += 1
                record = HistoricalSourceRecord(
                    historical_import_source_id=uuid4(),
                    workspace_id=uuid4(),
                    workspace_key=workspace_key,
                    source_kind=source.source_kind,
                    source_key=source.source_key,
                    fingerprint=source.fingerprint,
                    parser_version=source.parser_version,
                    redaction_policy_version=source.redaction_policy_version,
                    trust_level=source.trust_level,
                    taint=source.taint or {},
                    metadata=source.metadata or {},
                    status=source.status,
                    last_seen_at=now,
                    imported_at=now if source.status == "imported" else None,
                    created_at=now,
                    updated_at=now,
                )
            else:
                updated += 1
                record = HistoricalSourceRecord(
                    historical_import_source_id=existing.historical_import_source_id,
                    workspace_id=existing.workspace_id,
                    workspace_key=workspace_key,
                    source_kind=source.source_kind,
                    source_key=source.source_key,
                    fingerprint=source.fingerprint,
                    parser_version=source.parser_version,
                    redaction_policy_version=source.redaction_policy_version,
                    trust_level=source.trust_level,
                    taint=source.taint or {},
                    metadata=source.metadata or {},
                    status=source.status,
                    last_seen_at=now,
                    imported_at=now if source.status == "imported" else existing.imported_at,
                    created_at=existing.created_at,
                    updated_at=now,
                )
            self.sources[key] = record
            records.append(record)
        return HistoricalSourceUpsertResult(created=created, updated=updated, sources=records)

    async def list_sources(
        self,
        *,
        workspace_key: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[HistoricalSourceRecord]:
        records = list(self.sources.values())
        if workspace_key is not None:
            records = [record for record in records if record.workspace_key == workspace_key]
        if status is not None:
            records = [record for record in records if record.status == status]
        return records[:limit]

    async def record_chunks(
        self,
        *,
        workspace_key: str,
        chunks: list[HistoricalChunkInput],
    ) -> HistoricalChunkRecordResult:
        created = 0
        skipped = 0
        now = datetime.now(UTC)
        records: list[HistoricalChunkRecord] = []
        for chunk in chunks:
            source_key = (
                workspace_key,
                chunk.source_kind,
                chunk.source_key,
                chunk.fingerprint,
            )
            source = self.sources[source_key]
            redacted_text = redact_text(chunk.redacted_text)
            content_hash = f"hash:{redacted_text}"
            key = (
                workspace_key,
                str(source.historical_import_source_id),
                chunk.item_key,
                str(chunk.chunk_index),
                chunk.chunk_kind,
                content_hash,
            )
            if key in self.chunks:
                skipped += 1
                continue
            created += 1
            record = HistoricalChunkRecord(
                historical_import_chunk_id=uuid4(),
                workspace_id=source.workspace_id,
                workspace_key=workspace_key,
                historical_import_source_id=source.historical_import_source_id,
                item_key=chunk.item_key,
                chunk_index=chunk.chunk_index,
                chunk_kind=chunk.chunk_kind,
                content_hash=content_hash,
                redacted_text=redacted_text,
                token_estimate=chunk.token_estimate,
                parser_version=chunk.parser_version,
                redaction_policy_version=chunk.redaction_policy_version,
                trust_level=chunk.trust_level,
                taint=chunk.taint or {},
                metadata=chunk.metadata or {},
                status="observed",
                created_at=now,
            )
            self.chunks[key] = record
            records.append(record)
        return HistoricalChunkRecordResult(created=created, skipped=skipped, chunks=records)


def test_historical_import_source_inventory_is_idempotent() -> None:
    store = MemoryHistoricalImportStore()

    async def run():
        first = await store.upsert_sources(
            workspace_key="dev-01",
            sources=[
                HistoricalSourceInput(
                    source_kind="session_store",
                    source_key="agent:main/sessions",
                    fingerprint="sha256:session-root",
                    parser_version="historical-import.v1",
                    redaction_policy_version="redaction.v1",
                    taint={"raw_historical": True},
                    metadata={"dry_run": True},
                    status="inventory_only",
                )
            ],
        )
        second = await store.upsert_sources(
            workspace_key="dev-01",
            sources=[
                HistoricalSourceInput(
                    source_kind="session_store",
                    source_key="agent:main/sessions",
                    fingerprint="sha256:session-root",
                    parser_version="historical-import.v1",
                    redaction_policy_version="redaction.v1",
                    taint={"raw_historical": True},
                    metadata={"dry_run": False},
                    status="imported",
                )
            ],
        )
        listed = await store.list_sources(workspace_key="dev-01")
        return first, second, listed

    first, second, listed = asyncio.run(run())
    assert first.created == 1
    assert second.updated == 1
    assert listed[0].status == "imported"
    assert listed[0].taint == {"raw_historical": True}
    assert listed[0].metadata == {"dry_run": False}


def test_historical_import_records_only_redacted_chunks() -> None:
    store = MemoryHistoricalImportStore()

    async def run():
        await store.upsert_sources(
            workspace_key="dev-01",
            sources=[
                HistoricalSourceInput(
                    source_kind="workspace_memory",
                    source_key="MEMORY.md",
                    fingerprint="sha256:memory",
                    parser_version="historical-import.v1",
                    redaction_policy_version="redaction.v1",
                )
            ],
        )
        first = await store.record_chunks(
            workspace_key="dev-01",
            chunks=[
                HistoricalChunkInput(
                    source_kind="workspace_memory",
                    source_key="MEMORY.md",
                    fingerprint="sha256:memory",
                    item_key="MEMORY.md#chunk-0",
                    chunk_index=0,
                    redacted_text=(
                        "Contact test@example.com with "
                        "sk-abcdefghijklmnopqrstuvwxyz for bounded output."
                    ),
                    parser_version="historical-import.v1",
                    redaction_policy_version="redaction.v1",
                    token_estimate=6,
                    taint={"raw_text_stripped": True},
                )
            ],
        )
        duplicate = await store.record_chunks(
            workspace_key="dev-01",
            chunks=[
                HistoricalChunkInput(
                    source_kind="workspace_memory",
                    source_key="MEMORY.md",
                    fingerprint="sha256:memory",
                    item_key="MEMORY.md#chunk-0",
                    chunk_index=0,
                    redacted_text=(
                        "Contact test@example.com with "
                        "sk-abcdefghijklmnopqrstuvwxyz for bounded output."
                    ),
                    parser_version="historical-import.v1",
                    redaction_policy_version="redaction.v1",
                    token_estimate=6,
                )
            ],
        )
        return first, duplicate

    first, duplicate = asyncio.run(run())
    assert first.created == 1
    assert "test@example.com" not in first.chunks[0].redacted_text
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in first.chunks[0].redacted_text
    assert "[REDACTED_EMAIL]" in first.chunks[0].redacted_text
    assert first.chunks[0].taint == {"raw_text_stripped": True}
    assert duplicate.skipped == 1


def test_historical_chunk_input_storage_redacts_secret_like_text() -> None:
    chunk = HistoricalChunkInput(
        source_kind="transcript",
        source_key="session.jsonl",
        fingerprint="sha256:session",
        item_key="session#0",
        chunk_index=0,
        redacted_text="contact test@example.com with sk-abcdefghijklmnopqrstuvwxyz",
        parser_version="historical-import.v1",
        redaction_policy_version="redaction.v1",
    )

    redacted = chunk.storage_redacted()

    assert "test@example.com" not in redacted.redacted_text
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in redacted.redacted_text
    assert "[REDACTED_EMAIL]" in redacted.redacted_text
    assert redacted.taint == {"storage_redacted": True}


def test_historical_import_api_routes_use_control_surface() -> None:
    store = MemoryHistoricalImportStore()
    app = create_app(historical_import_store=store)
    routes = {(route.path, next(iter(route.methods))): route for route in app.routes}

    async def run():
        upsert = await routes[("/v1/historical-import/sources", "POST")].endpoint(
            request=HistoricalImportSourceUpsertRequest(
                workspace_id="dev-01",
                sources=[
                    HistoricalImportSourceItem(
                        source_kind="taskflow_record",
                        source_key="skillkernel-autoskill-v1",
                        fingerprint="sha256:taskflow",
                        parser_version="historical-import.v1",
                        redaction_policy_version="redaction.v1",
                        status="inventory_only",
                    )
                ],
            )
        )
        chunks = await routes[("/v1/historical-import/chunks", "POST")].endpoint(
            request=HistoricalImportChunkRecordRequest(
                workspace_id="dev-01",
                chunks=[
                    HistoricalImportChunkItem(
                        source_kind="taskflow_record",
                        source_key="skillkernel-autoskill-v1",
                        fingerprint="sha256:taskflow",
                        item_key="taskflow#0",
                        chunk_index=0,
                        redacted_text="redacted taskflow checkpoint",
                        parser_version="historical-import.v1",
                        redaction_policy_version="redaction.v1",
                    )
                ],
            )
        )
        listed = await routes[("/v1/historical-import/sources", "GET")].endpoint(
            workspace_id="dev-01"
        )
        return upsert, chunks, listed

    upsert, chunks, listed = asyncio.run(run())
    assert upsert.created == 1
    assert chunks.created == 1
    assert listed.sources[0]["source_kind"] == "taskflow_record"
