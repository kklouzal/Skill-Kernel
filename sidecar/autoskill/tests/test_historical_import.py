import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from autoskill.api.app import (
    HistoricalImportChunkItem,
    HistoricalImportChunkRecordRequest,
    HistoricalImportDiscoverRequest,
    HistoricalImportSourceItem,
    HistoricalImportSourceRevokeRequest,
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
    HistoricalSourceRevokeResult,
    HistoricalSourceUpsertResult,
)
from autoskill.db.scheduler import ScheduleRecord, ScheduleUpsertResult
from autoskill.services.historical_discovery import (
    discover_historical_sources,
    ensure_historical_discovery_schedule,
)
from autoskill.services.worker import WorkerStores, run_worker_once
from autoskill.tests.test_jobs_api import MemoryJobStore


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

    async def revoke_source(
        self,
        *,
        workspace_key: str,
        historical_import_source_id,
    ) -> HistoricalSourceRevokeResult:
        source_key = None
        source = None
        for key, record in self.sources.items():
            if (
                record.workspace_key == workspace_key
                and record.historical_import_source_id == historical_import_source_id
            ):
                source_key = key
                source = record
                break
        if source_key is None or source is None:
            return HistoricalSourceRevokeResult(
                source=None,
                sources_revoked=0,
                chunks_revoked=0,
            )
        revoked_source = HistoricalSourceRecord(
            historical_import_source_id=source.historical_import_source_id,
            workspace_id=source.workspace_id,
            workspace_key=source.workspace_key,
            source_kind=source.source_kind,
            source_key=source.source_key,
            fingerprint=source.fingerprint,
            parser_version=source.parser_version,
            redaction_policy_version=source.redaction_policy_version,
            trust_level=source.trust_level,
            taint=source.taint,
            metadata=source.metadata,
            status="revoked",
            last_seen_at=source.last_seen_at,
            imported_at=source.imported_at,
            created_at=source.created_at,
            updated_at=datetime.now(UTC),
        )
        self.sources[source_key] = revoked_source
        chunks_revoked = 0
        for key, chunk in list(self.chunks.items()):
            if (
                chunk.workspace_key == workspace_key
                and chunk.historical_import_source_id == historical_import_source_id
                and chunk.status != "revoked"
            ):
                self.chunks[key] = HistoricalChunkRecord(
                    historical_import_chunk_id=chunk.historical_import_chunk_id,
                    workspace_id=chunk.workspace_id,
                    workspace_key=chunk.workspace_key,
                    historical_import_source_id=chunk.historical_import_source_id,
                    item_key=chunk.item_key,
                    chunk_index=chunk.chunk_index,
                    chunk_kind=chunk.chunk_kind,
                    content_hash=chunk.content_hash,
                    redacted_text=chunk.redacted_text,
                    token_estimate=chunk.token_estimate,
                    parser_version=chunk.parser_version,
                    redaction_policy_version=chunk.redaction_policy_version,
                    trust_level=chunk.trust_level,
                    taint=chunk.taint,
                    metadata=chunk.metadata,
                    status="revoked",
                    created_at=chunk.created_at,
                )
                chunks_revoked += 1
        return HistoricalSourceRevokeResult(
            source=revoked_source,
            sources_revoked=1,
            chunks_revoked=chunks_revoked,
        )


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


def test_historical_import_source_revocation_tombstones_chunks() -> None:
    store = MemoryHistoricalImportStore()

    async def run():
        source = await store.upsert_sources(
            workspace_key="dev-01",
            sources=[
                HistoricalSourceInput(
                    source_kind="transcript",
                    source_key="session.jsonl",
                    fingerprint="sha256:session",
                    parser_version="historical-import.v1",
                    redaction_policy_version="redaction.v1",
                )
            ],
        )
        await store.record_chunks(
            workspace_key="dev-01",
            chunks=[
                HistoricalChunkInput(
                    source_kind="transcript",
                    source_key="session.jsonl",
                    fingerprint="sha256:session",
                    item_key="session#0",
                    chunk_index=0,
                    redacted_text="redacted transcript",
                    parser_version="historical-import.v1",
                    redaction_policy_version="redaction.v1",
                )
            ],
        )
        revoked = await store.revoke_source(
            workspace_key="dev-01",
            historical_import_source_id=source.sources[0].historical_import_source_id,
        )
        return revoked

    revoked = asyncio.run(run())
    assert revoked.sources_revoked == 1
    assert revoked.chunks_revoked == 1
    assert revoked.source is not None
    assert revoked.source.status == "revoked"
    assert list(store.chunks.values())[0].status == "revoked"


def test_historical_import_source_revocation_api_route() -> None:
    store = MemoryHistoricalImportStore()
    app = create_app(historical_import_store=store)
    routes = {(route.path, next(iter(route.methods))): route for route in app.routes}

    async def run():
        source = await store.upsert_sources(
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
        await store.record_chunks(
            workspace_key="dev-01",
            chunks=[
                HistoricalChunkInput(
                    source_kind="workspace_memory",
                    source_key="MEMORY.md",
                    fingerprint="sha256:memory",
                    item_key="MEMORY.md#0",
                    chunk_index=0,
                    redacted_text="redacted memory",
                    parser_version="historical-import.v1",
                    redaction_policy_version="redaction.v1",
                )
            ],
        )
        return await routes[("/v1/historical-import/sources/revoke", "POST")].endpoint(
            request=HistoricalImportSourceRevokeRequest(
                workspace_id="dev-01",
                historical_import_source_id=source.sources[0].historical_import_source_id,
            )
        )

    revoked = asyncio.run(run())
    assert revoked.sources_revoked == 1
    assert revoked.chunks_revoked == 1
    assert revoked.source["status"] == "revoked"


def test_historical_discovery_dry_run_classifies_sources_without_raw_paths(tmp_path) -> None:
    root = tmp_path / "workspace"
    sessions = root / "sessions"
    skill_dir = root / "skills" / "example"
    sessions.mkdir(parents=True)
    skill_dir.mkdir(parents=True)
    (root / "AGENTS.md").write_text("workspace policy", encoding="utf-8")
    (root / "MEMORY.md").write_text("durable note", encoding="utf-8")
    (sessions / "sessions.json").write_text('{"sessions":[]}', encoding="utf-8")
    (sessions / "abc.jsonl").write_text('{"role":"user","content":"hello"}\n', encoding="utf-8")
    (skill_dir / "SKILL.md").write_text("---\nname: Example\n---\nDO thing\n", encoding="utf-8")
    store = MemoryHistoricalImportStore()

    inventory = asyncio.run(
        discover_historical_sources(
            store,
            workspace_key="dev-01",
            roots=[root],
            max_files=20,
            preview_only=True,
        )
    )

    assert inventory.scanned_roots == 1
    assert inventory.scanned_files == 5
    assert inventory.upsert is None
    assert inventory.source_counts["workspace_context"] == 1
    assert inventory.source_counts["workspace_memory"] == 1
    assert inventory.source_counts["session_store"] == 1
    assert inventory.source_counts["transcript"] == 1
    assert inventory.source_counts["existing_skill"] == 1
    assert all(item.source_key.startswith("path-sha256:") for item in inventory.items)
    assert all(not item.metadata["stored_raw_path"] for item in inventory.items)
    assert not store.sources


def test_historical_discovery_can_upsert_inventory_only_sources(tmp_path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "TASKFLOW.md").write_text("# flow\n", encoding="utf-8")
    store = MemoryHistoricalImportStore()

    inventory = asyncio.run(
        discover_historical_sources(
            store,
            workspace_key="dev-01",
            roots=[root],
            max_files=5,
            preview_only=False,
        )
    )

    assert inventory.upsert is not None
    assert inventory.upsert.created == 1
    assert list(store.sources.values())[0].source_kind == "taskflow_record"
    assert list(store.sources.values())[0].status == "inventory_only"


def test_historical_discovery_api_route_preview_and_upsert(tmp_path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "AGENTS.md").write_text("workspace policy", encoding="utf-8")
    store = MemoryHistoricalImportStore()
    app = create_app(historical_import_store=store)
    routes = {(route.path, next(iter(route.methods))): route for route in app.routes}

    async def run():
        preview = await routes[("/v1/historical-import/discover", "POST")].endpoint(
            request=HistoricalImportDiscoverRequest(
                workspace_id="dev-01",
                roots=[root],
                preview_only=True,
            )
        )
        upsert = await routes[("/v1/historical-import/discover", "POST")].endpoint(
            request=HistoricalImportDiscoverRequest(
                workspace_id="dev-01",
                roots=[root],
                preview_only=False,
            )
        )
        return preview, upsert

    preview, upsert = asyncio.run(run())
    assert preview.scanned_files == 1
    assert preview.upsert is None
    assert upsert.upsert is not None
    assert upsert.upsert["created"] == 1
    assert list(store.sources.values())[0].source_kind == "workspace_context"


class MemoryHistoricalDiscoveryScheduleStore:
    def __init__(self) -> None:
        self.upserts: list[dict[str, object]] = []

    async def upsert_schedule(
        self,
        *,
        workspace_key: str,
        name: str,
        job_kind: str,
        interval_seconds: int,
        next_run_at: datetime,
        payload: dict[str, object] | None = None,
        enabled: bool = True,
    ) -> ScheduleUpsertResult:
        self.upserts.append(
            {
                "workspace_key": workspace_key,
                "name": name,
                "job_kind": job_kind,
                "interval_seconds": interval_seconds,
                "payload": payload or {},
                "enabled": enabled,
            }
        )
        return ScheduleUpsertResult(
            schedule=ScheduleRecord(
                schedule_id=uuid4(),
                workspace_key=workspace_key,
                name=name,
                job_kind=job_kind,
                enabled=enabled,
                interval_seconds=interval_seconds,
                next_run_at=next_run_at,
                payload=payload or {},
            ),
            created=True,
        )


def test_historical_discovery_schedule_is_bounded_without_raw_roots(tmp_path) -> None:
    scheduler = MemoryHistoricalDiscoveryScheduleStore()

    result = asyncio.run(
        ensure_historical_discovery_schedule(
            scheduler,
            workspace_key="dev-01",
            roots=[tmp_path],
            interval_seconds=10,
            max_files=25,
            max_bytes=4096,
        )
    )

    assert result is not None
    assert scheduler.upserts[0]["name"] == "historical_import.discover"
    assert scheduler.upserts[0]["job_kind"] == "historical_import.discover"
    assert scheduler.upserts[0]["interval_seconds"] == 900
    assert scheduler.upserts[0]["payload"] == {
        "workspace_id": "dev-01",
        "max_files": 25,
        "max_bytes": 4096,
    }


def test_historical_discovery_worker_job_records_inventory(tmp_path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "MEMORY.md").write_text("memory note", encoding="utf-8")
    jobs = MemoryJobStore()
    historical = MemoryHistoricalImportStore()

    async def run():
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="historical_import.discover",
            idempotency_key="historical-discover:dev-01",
            payload={"workspace_id": "dev-01", "max_files": 10},
        )
        return await run_worker_once(
            WorkerStores(
                jobs=jobs,
                scheduler=MemoryHistoricalDiscoveryScheduleStore(),
                evidence=None,  # type: ignore[arg-type]
                embeddings=None,  # type: ignore[arg-type]
                historical_import=historical,
                historical_import_roots=[root],
            ),
            worker_id="worker-1",
            pool="maintenance",
        )

    result = asyncio.run(run())
    assert result.claimed
    assert result.status == "succeeded"
    assert result.output is not None
    assert result.output["scanned_files"] == 1
    assert result.output["upsert"]["created"] == 1
    assert list(historical.sources.values())[0].source_kind == "workspace_memory"
