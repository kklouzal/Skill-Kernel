import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from autoskill.api.app import (
    HistoricalImportChunkItem,
    HistoricalImportChunkRecordRequest,
    HistoricalImportDiscoverRequest,
    HistoricalImportParseRequest,
    HistoricalImportSourceItem,
    HistoricalImportSourceRevokeRequest,
    HistoricalImportSourceUpsertRequest,
    create_app,
)
from autoskill.core.audit import AuditRecord, verify_hash_chain
from autoskill.core.redaction import redact_text
from autoskill.db.historical import (
    HistoricalChunkInput,
    HistoricalChunkRecord,
    HistoricalChunkRecordResult,
    HistoricalImportRunRecord,
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
    resolve_historical_import_roots,
)
from autoskill.services.historical_import import import_historical_sources
from autoskill.services.worker import WorkerStores, run_worker_once
from autoskill.tests.test_governance import MemoryGovernanceStore
from autoskill.tests.test_jobs_api import MemoryJobStore


class MemoryAuditStore:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    async def append_record(self, record: AuditRecord, *, workspace_key: str) -> AuditRecord:
        previous_hash = self.records[-1].audit_hash if self.records else None
        sealed = record.model_copy(update={"previous_hash": previous_hash}).sealed()
        self.records.append(sealed)
        return sealed

    async def list_recent(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        return list(reversed(self.records))[:limit]

    async def verify_chain(self, *, workspace_key: str | None = None, limit: int = 1000) -> bool:
        return verify_hash_chain(self.records[-limit:])


class MemoryHistoricalImportStore(HistoricalImportStore):
    def __init__(self) -> None:
        self.sources: dict[tuple[str, str, str, str], HistoricalSourceRecord] = {}
        self.chunks: dict[tuple[str, str, str, str, int, str], HistoricalChunkRecord] = {}
        self.runs: dict[str, HistoricalImportRunRecord] = {}

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
            metadata = chunk.metadata or {}
            source_item = metadata.get("source_item")
            source_item = source_item if isinstance(source_item, dict) else {}
            lineage = metadata.get("lineage")
            lineage = lineage if isinstance(lineage, dict) else {}
            record_index = source_item.get("record_index")
            record = HistoricalChunkRecord(
                historical_import_chunk_id=uuid4(),
                workspace_id=source.workspace_id,
                workspace_key=workspace_key,
                historical_import_source_id=source.historical_import_source_id,
                item_key=chunk.item_key,
                chunk_index=chunk.chunk_index,
                source_item_locator_hash=(
                    source_item.get("locator_hash")
                    or lineage.get("source_item_locator_hash")
                ),
                source_item_kind=source_item.get("item_kind"),
                item_key_hash=(
                    source_item.get("item_key_hash") or lineage.get("item_key_hash")
                ),
                line_range_hash=source_item.get("line_range_hash"),
                record_index=record_index if isinstance(record_index, int) else None,
                chunk_kind=chunk.chunk_kind,
                content_hash=content_hash,
                redacted_text=redacted_text,
                token_estimate=chunk.token_estimate,
                parser_version=chunk.parser_version,
                redaction_policy_version=chunk.redaction_policy_version,
                trust_level=chunk.trust_level,
                taint=chunk.taint or {},
                metadata=metadata,
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
                    source_item_locator_hash=chunk.source_item_locator_hash,
                    source_item_kind=chunk.source_item_kind,
                    item_key_hash=chunk.item_key_hash,
                    line_range_hash=chunk.line_range_hash,
                    record_index=chunk.record_index,
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

    async def record_import_run(
        self,
        *,
        workspace_key: str,
        run_kind: str,
        idempotency_key: str,
        status: str,
        checkpoint: dict[str, object] | None = None,
        stats: dict[str, object] | None = None,
    ) -> HistoricalImportRunRecord:
        now = datetime.now(UTC)
        existing = self.runs.get(idempotency_key)
        run = HistoricalImportRunRecord(
            historical_import_run_id=(
                existing.historical_import_run_id if existing is not None else uuid4()
            ),
            workspace_id=existing.workspace_id if existing is not None else uuid4(),
            workspace_key=workspace_key,
            run_kind=run_kind,
            idempotency_key=idempotency_key,
            status=status,
            checkpoint=checkpoint or {},
            stats=stats or {},
            started_at=existing.started_at if existing is not None else now,
            completed_at=now if status in {"completed", "failed", "cancelled"} else None,
            updated_at=now,
        )
        self.runs[idempotency_key] = run
        return run


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
    governance = MemoryGovernanceStore()
    jobs = MemoryJobStore()
    audit = MemoryAuditStore()
    app = create_app(
        historical_import_store=store,
        governance_store=governance,
        job_store=jobs,
        audit_store=audit,
    )
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
    assert revoked.revocation["request_kind"] == "operator_revoke"
    assert revoked.revocation["root_object_type"] == "historical_import_source"
    assert revoked.job["created"] is True
    assert revoked.job["job"]["job_kind"] == "revocations.invalidate"
    assert audit.records[-1].action == "historical_import.source_revoke"
    assert audit.records[-1].subject_id == str(revoked.source["historical_import_source_id"])
    assert audit.records[-1].details["chunks_revoked"] == 1
    assert asyncio.run(audit.verify_chain(workspace_key="dev-01")) is True


def test_historical_revocation_invalidation_worker_completes_operator_revoke() -> None:
    governance = MemoryGovernanceStore()
    jobs = MemoryJobStore()

    async def run():
        revocation = await governance.request_revocation(
            workspace_key="dev-01",
            request_kind="operator_revoke",
            root_object_type="historical_import_source",
            root_object_id=uuid4(),
            traversal_summary={
                "impacted_objects": [
                    {"object_type": "historical_import_source", "object_id": str(uuid4())},
                    {"object_type": "historical_import_chunk", "object_id": str(uuid4())},
                    {"object_type": "evidence_item", "object_id": str(uuid4())},
                ]
            },
        )
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="revocations.invalidate",
            idempotency_key="revocations.invalidate:test",
            payload={"workspace_id": "dev-01", "request_kind": "operator_revoke"},
        )
        result = await run_worker_once(
            WorkerStores(
                jobs=jobs,
                scheduler=None,
                evidence=None,
                embeddings=None,
                governance=governance,
            ),
            worker_id="mutation-test",
            pool="mutation",
        )
        return revocation, result

    revocation, result = asyncio.run(run())
    assert result.status == "succeeded"
    assert result.output["completed"] == 1
    completed = next(
        item
        for item in governance.revocations
        if item.revocation_request_id == revocation.revocation_request_id
    )
    assert completed.status == "completed"
    assert completed.traversal_summary["status"] == "completed"
    assert completed.traversal_summary["invalidation"]["objects"] == 3


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


def test_historical_discovery_classifies_background_task_records(tmp_path) -> None:
    root = tmp_path / "workspace"
    tasks = root / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "runs.jsonl").write_text(
        '{"task_id":"task-1","status":"done","goal":"repair flaky test"}\n',
        encoding="utf-8",
    )
    store = MemoryHistoricalImportStore()

    inventory = asyncio.run(
        discover_historical_sources(
            store,
            workspace_key="dev-01",
            roots=[root],
            max_files=5,
            preview_only=True,
        )
    )

    assert inventory.source_counts["task_record"] == 1
    item = inventory.items[0]
    assert item.source_kind == "task_record"
    assert item.taint["task_ledger"] is True
    assert item.metadata["import_recommendation"] == "metadata_only_import_with_task_taint"


def test_historical_discovery_classifies_plugin_media_and_observability_sources(
    tmp_path,
) -> None:
    root = tmp_path / "workspace"
    plugin = root / "plugin" / "autoskill"
    hook = plugin / "hooks" / "before-prompt-build"
    observability = root / "observability"
    media = root / "media"
    hook.mkdir(parents=True)
    observability.mkdir(parents=True)
    media.mkdir(parents=True)
    (plugin / "package.json").write_text(
        '{"name":"skillkernel-plugin","version":"0.1.0","scripts":{"test":"node --test"}}',
        encoding="utf-8",
    )
    (plugin / "src.js").write_text("console.log('do not import body')", encoding="utf-8")
    (hook / "HOOK.md").write_text("# Hook\nRuntime metadata only.\n", encoding="utf-8")
    (observability / "trace.jsonl").write_text(
        '{"trace_id":"abc","status":"ok"}\n',
        encoding="utf-8",
    )
    (media / "screenshot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
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

    assert inventory.source_counts["plugin_manifest"] == 1
    assert inventory.source_counts["plugin_source"] == 1
    assert inventory.source_counts["plugin_hook_manifest"] == 1
    assert inventory.source_counts["observability_export"] == 1
    assert inventory.source_counts["media_artifact"] == 1
    assert all(item.source_key.startswith("path-sha256:") for item in inventory.items)
    assert all(not item.metadata["stored_raw_path"] for item in inventory.items)
    source_item = next(item for item in inventory.items if item.source_kind == "plugin_source")
    assert source_item.taint["source_body_not_imported"] is True
    media_item = next(item for item in inventory.items if item.source_kind == "media_artifact")
    assert media_item.taint["media_body_not_imported"] is True


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


def test_historical_root_resolution_discovers_openclaw_defaults(
    tmp_path, monkeypatch
) -> None:
    openclaw_root = tmp_path / ".openclaw"
    agents = openclaw_root / "agents"
    workspace = openclaw_root / "workspace"
    internal_runs = openclaw_root / "internal-agent-runs"
    agents.mkdir(parents=True)
    workspace.mkdir()
    internal_runs.mkdir()
    monkeypatch.setenv("OPENCLAW_STATE_DIR", str(openclaw_root))

    class Settings:
        openclaw_state_dir_env = "OPENCLAW_STATE_DIR"
        openclaw_home_env = "OPENCLAW_HOME"
        openclaw_state_dir_default = "~/.openclaw"
        workspace_roots: list[str] = []
        session_store_roots: list[str] = []
        trajectory_roots: list[str] = []
        transcript_corpus_roots: list[str] = []

    roots = resolve_historical_import_roots(
        Settings(),
        workspace_root=workspace,
    )

    assert roots == [agents, workspace, internal_runs]


def test_historical_root_resolution_respects_explicit_roots(tmp_path) -> None:
    explicit = tmp_path / "selected"
    ignored = tmp_path / ".openclaw" / "agents"
    explicit.mkdir()
    ignored.mkdir(parents=True)

    class Settings:
        openclaw_state_dir_env = "OPENCLAW_STATE_DIR"
        openclaw_home_env = "OPENCLAW_HOME"
        openclaw_state_dir_default = str(tmp_path / ".openclaw")
        workspace_roots: list[str] = []
        session_store_roots: list[str] = []
        trajectory_roots: list[str] = []
        transcript_corpus_roots: list[str] = []

    roots = resolve_historical_import_roots(
        Settings(),
        explicit_roots=[explicit],
    )

    assert roots == [explicit]


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


def test_historical_import_parses_transcripts_and_markdown_sections(tmp_path) -> None:
    root = tmp_path / "workspace"
    sessions = root / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "abc.jsonl").write_text(
        '{"role":"user","content":"Fix the failing pytest case"}\n'
        '{"role":"tool","content":"ModuleNotFoundError for package"}\n',
        encoding="utf-8",
    )
    (root / "MEMORY.md").write_text(
        "# Build notes\nAlways run pytest before deploy.\n",
        encoding="utf-8",
    )
    store = MemoryHistoricalImportStore()

    result = asyncio.run(
        import_historical_sources(
            store,
            workspace_key="dev-01",
            roots=[root],
            max_files=10,
            max_chunks=10,
            idempotency_key="historical-import:test",
        )
    )

    assert result.parsed_sources == 2
    assert result.chunks.created == 3
    assert result.run.status == "completed"
    assert result.run.checkpoint["parsed_sources"] == 2
    kinds = {chunk.chunk_kind for chunk in store.chunks.values()}
    assert "transcript_turn" in kinds
    assert "workspace_memory_section" in kinds
    assert any(chunk.taint.get("raw_transcript") for chunk in store.chunks.values())
    memory_chunk = next(
        chunk for chunk in store.chunks.values() if chunk.chunk_kind == "workspace_memory_section"
    )
    assert memory_chunk.taint["memory_poisoning_suspected"] is True
    assert memory_chunk.metadata["lineage_version"] == "historical-lineage.v2"
    assert memory_chunk.metadata["lineage"]["source_kind"] == "workspace_memory"
    assert memory_chunk.metadata["lineage"]["item_key"] == memory_chunk.item_key
    assert memory_chunk.metadata["source_item"]["item_kind"] == "markdown_section"
    assert memory_chunk.metadata["source_item"]["item_key_hash"]
    assert (
        memory_chunk.metadata["source_item"]["locator_hash"]
        == memory_chunk.metadata["lineage"]["source_item_locator_hash"]
    )
    assert memory_chunk.metadata["source_item"]["line_range_hash"]
    assert (
        memory_chunk.source_item_locator_hash
        == memory_chunk.metadata["source_item"]["locator_hash"]
    )
    assert memory_chunk.source_item_kind == "markdown_section"
    assert memory_chunk.item_key_hash == memory_chunk.metadata["source_item"]["item_key_hash"]
    assert memory_chunk.line_range_hash == memory_chunk.metadata["source_item"][
        "line_range_hash"
    ]


def test_historical_import_parses_taskflow_jsonl_as_metadata_only(
    tmp_path,
) -> None:
    root = tmp_path / "workspace"
    taskflow = root / "taskflow"
    taskflow.mkdir(parents=True)
    (taskflow / "runs.jsonl").write_text(
        (
            '{"flow_id":"flow-1","status":"running","currentStep":"validate",'
            '"goal":"Fix test@example.com without storing raw mail",'
            '"raw_prompt":"do not persist"}\n'
            '{"task_id":"task-2","status":"blocked","nextStep":"rerun canary"}\n'
        ),
        encoding="utf-8",
    )
    store = MemoryHistoricalImportStore()

    result = asyncio.run(
        import_historical_sources(
            store,
            workspace_key="dev-01",
            roots=[root],
            max_files=10,
            max_chunks=10,
            idempotency_key="historical-import:taskflow-jsonl",
        )
    )

    assert result.parsed_sources == 1
    assert result.chunks.created == 2
    chunks = list(store.chunks.values())
    assert {chunk.chunk_kind for chunk in chunks} == {"taskflow_record_metadata"}
    assert all(chunk.metadata["metadata_only"] is True for chunk in chunks)
    assert all(chunk.taint["task_ledger"] is True for chunk in chunks)
    assert all("raw_prompt" not in chunk.redacted_text for chunk in chunks)
    assert all("test@example.com" not in chunk.redacted_text for chunk in chunks)
    first = chunks[0]
    assert first.metadata["safe_metadata_keys"] == [
        "currentStep",
        "flow_id",
        "goal",
        "status",
    ]
    assert first.metadata["lineage"]["source_kind"] == "taskflow_record"
    assert first.metadata["lineage"]["item_key"] == first.item_key
    assert first.metadata["lineage_version"] == "historical-lineage.v2"
    assert first.metadata["source_item"]["item_kind"] == "taskflow_record"
    assert first.metadata["source_item"]["record_index"] == 0
    assert first.metadata["source_item"]["locator_hash"]
    assert first.source_item_locator_hash == first.metadata["source_item"]["locator_hash"]
    assert first.source_item_kind == "taskflow_record"
    assert first.item_key_hash == first.metadata["source_item"]["item_key_hash"]
    assert first.record_index == 0
    assert first.metadata["source_path_stored"] is False


def test_historical_import_parses_task_record_jsonl_as_metadata_only(
    tmp_path,
) -> None:
    root = tmp_path / "workspace"
    tasks = root / "subagents"
    tasks.mkdir(parents=True)
    (tasks / "runs.jsonl").write_text(
        (
            '{"task_id":"task-1","parent_session_key":"parent-a",'
            '"child_session_key":"child-b","runtime_kind":"acp",'
            '"status":"succeeded","goal":"Fix test@example.com",'
            '"raw_prompt":"do not persist"}\n'
        ),
        encoding="utf-8",
    )
    store = MemoryHistoricalImportStore()

    result = asyncio.run(
        import_historical_sources(
            store,
            workspace_key="dev-01",
            roots=[root],
            max_files=10,
            max_chunks=10,
            idempotency_key="historical-import:task-record-jsonl",
        )
    )

    assert result.parsed_sources == 1
    assert result.chunks.created == 1
    first = next(iter(store.chunks.values()))
    assert first.chunk_kind == "task_record_metadata"
    assert first.metadata["lineage"]["source_kind"] == "task_record"
    assert first.taint["task_ledger"] is True
    assert first.taint["metadata_only"] is True
    assert first.metadata["metadata_only"] is True
    assert first.metadata["source_item"]["item_kind"] == "task_record"
    assert first.source_item_kind == "task_record"
    assert "raw_prompt" not in first.redacted_text
    assert "test@example.com" not in first.redacted_text
    assert first.metadata["safe_metadata_keys"] == [
        "child_session_key",
        "goal",
        "parent_session_key",
        "runtime_kind",
        "status",
        "task_id",
    ]
    assert first.metadata["source_path_stored"] is False


def test_historical_import_parses_transcript_corpus_exports(tmp_path) -> None:
    root = tmp_path / "workspace"
    corpus = root / "transcripts" / "2026-06-02" / "session-a"
    corpus.mkdir(parents=True)
    (corpus / "metadata.json").write_text(
        (
            '{"selector":"daily","session_id":"session-a","agent_id":"main",'
            '"title":"pytest repair","raw_prompt":"do not persist me"}'
        ),
        encoding="utf-8",
    )
    (corpus / "summary.md").write_text(
        "# Summary\nUser corrected a failing pytest workflow.\n",
        encoding="utf-8",
    )
    (corpus / "transcript.jsonl").write_text(
        '{"role":"user","content":"Run pytest for test@example.com"}\n'
        '{"role":"assistant","content":"Used uv run pytest successfully"}\n',
        encoding="utf-8",
    )
    store = MemoryHistoricalImportStore()

    result = asyncio.run(
        import_historical_sources(
            store,
            workspace_key="dev-01",
            roots=[root],
            max_files=10,
            max_chunks=10,
            idempotency_key="historical-import:transcript-corpus",
        )
    )

    assert result.discovery.source_counts["transcript_corpus"] == 3
    assert result.parsed_sources == 3
    kinds = {chunk.chunk_kind for chunk in store.chunks.values()}
    assert kinds == {
        "transcript_corpus_metadata",
        "transcript_corpus_summary",
        "transcript_corpus_turn",
    }
    metadata_chunk = next(
        chunk for chunk in store.chunks.values() if chunk.chunk_kind == "transcript_corpus_metadata"
    )
    assert "raw_prompt" not in metadata_chunk.redacted_text
    assert metadata_chunk.metadata["metadata_only"] is True
    assert "session_id" in metadata_chunk.metadata["safe_keys"]
    summary_chunk = next(
        chunk for chunk in store.chunks.values() if chunk.chunk_kind == "transcript_corpus_summary"
    )
    assert summary_chunk.taint["compaction_summary"] is True
    assert summary_chunk.metadata["confidence"] == "derived_summary"
    turn_chunks = [
        chunk for chunk in store.chunks.values() if chunk.chunk_kind == "transcript_corpus_turn"
    ]
    assert len(turn_chunks) == 2
    assert all(chunk.taint["transcript_corpus"] for chunk in turn_chunks)
    assert all("test@example.com" not in chunk.redacted_text for chunk in turn_chunks)
    assert all(
        chunk.metadata["lineage_version"] == "historical-lineage.v2"
        for chunk in turn_chunks
    )
    assert all(chunk.metadata["source_item"]["item_kind"] == "line_record" for chunk in turn_chunks)
    assert all(chunk.metadata["source_item"]["line_range_hash"] for chunk in turn_chunks)


def test_historical_import_parses_plugin_and_media_sources_as_metadata_only(
    tmp_path,
) -> None:
    root = tmp_path / "workspace"
    plugin = root / "plugin" / "autoskill"
    hook = plugin / "hooks" / "before-prompt-build"
    media = root / "media"
    plugin.mkdir(parents=True)
    hook.mkdir(parents=True)
    media.mkdir(parents=True)
    (plugin / "package.json").write_text(
        (
            '{"name":"skillkernel-plugin","version":"0.1.0",'
            '"description":"test@example.com should redact",'
            '"dependencies":{"secret-package":"1.0.0"},'
            '"scripts":{"test":"node --test"}}'
        ),
        encoding="utf-8",
    )
    (plugin / "src.js").write_text(
        "const token = 'sk-abcdefghijklmnopqrstuvwxyz';\n",
        encoding="utf-8",
    )
    (hook / "HOOK.md").write_text(
        "# Hook\nDo not ingest this hook body as historical evidence.\n",
        encoding="utf-8",
    )
    (media / "capture.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    store = MemoryHistoricalImportStore()

    result = asyncio.run(
        import_historical_sources(
            store,
            workspace_key="dev-01",
            roots=[root],
            max_files=20,
            max_chunks=20,
            idempotency_key="historical-import:plugin-media",
        )
    )

    assert result.parsed_sources == 4
    kinds = {chunk.chunk_kind for chunk in store.chunks.values()}
    assert kinds == {
        "media_artifact_metadata",
        "plugin_hook_manifest_metadata",
        "plugin_manifest_metadata",
        "plugin_source_metadata",
    }
    manifest_chunk = next(
        chunk for chunk in store.chunks.values() if chunk.chunk_kind == "plugin_manifest_metadata"
    )
    assert "test@example.com" not in manifest_chunk.redacted_text
    assert manifest_chunk.metadata["metadata_only"] is True
    assert manifest_chunk.taint["plugin_surface"] is True
    source_chunk = next(
        chunk for chunk in store.chunks.values() if chunk.chunk_kind == "plugin_source_metadata"
    )
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in source_chunk.redacted_text
    assert "const token" not in source_chunk.redacted_text
    assert source_chunk.metadata["body_imported"] is False
    assert source_chunk.taint["source_body_not_imported"] is True
    media_chunk = next(
        chunk for chunk in store.chunks.values() if chunk.chunk_kind == "media_artifact_metadata"
    )
    assert media_chunk.metadata["body_imported"] is False
    assert media_chunk.taint["media_body_not_imported"] is True


def test_historical_import_is_idempotent_for_duplicate_chunks(tmp_path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "TASKFLOW.md").write_text("# Gate\nRun replay before promote.\n", encoding="utf-8")
    store = MemoryHistoricalImportStore()

    async def run():
        first = await import_historical_sources(
            store,
            workspace_key="dev-01",
            roots=[root],
            idempotency_key="historical-import:taskflow",
        )
        second = await import_historical_sources(
            store,
            workspace_key="dev-01",
            roots=[root],
            idempotency_key="historical-import:taskflow",
        )
        return first, second

    first, second = asyncio.run(run())
    assert first.chunks.created == 1
    assert second.chunks.created == 0
    assert second.chunks.skipped == 1
    assert store.runs["historical-import:taskflow"].status == "completed"


def test_historical_import_parse_api_route(tmp_path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "AGENTS.md").write_text("# Boundaries\nNever store raw secrets.\n", encoding="utf-8")
    store = MemoryHistoricalImportStore()
    app = create_app(historical_import_store=store)
    routes = {(route.path, next(iter(route.methods))): route for route in app.routes}

    result = asyncio.run(
        routes[("/v1/historical-import/parse", "POST")].endpoint(
            request=HistoricalImportParseRequest(
                workspace_id="dev-01",
                roots=[root],
                idempotency_key="historical-import:api",
            )
        )
    )

    assert result.parsed_sources == 1
    assert result.chunks["created"] == 1
    assert result.run["status"] == "completed"
    assert list(store.sources.values())[0].status == "imported"


def test_historical_import_parse_worker_job(tmp_path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "TASKFLOW.md").write_text("# Next\nRun canary replay.\n", encoding="utf-8")
    jobs = MemoryJobStore()
    historical = MemoryHistoricalImportStore()

    async def run():
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="historical_import.parse",
            idempotency_key="historical-import-parse:dev-01",
            payload={
                "workspace_id": "dev-01",
                "max_files": 10,
                "idempotency_key": "historical-import:worker",
            },
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
    assert result.output["parsed_sources"] == 1
    assert result.output["chunks"]["created"] == 1
