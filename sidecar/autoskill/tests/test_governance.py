import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from autoskill.api.app import (
    EvolutionTransactionItemRequest,
    EvolutionTransactionStartRequest,
    EvolutionTransactionStatusRequest,
    RevocationRequestCreateRequest,
    create_app,
)
from autoskill.db.governance import (
    EvolutionTransactionItemRecord,
    EvolutionTransactionRecord,
    RevocationRequestRecord,
    TransactionStartResult,
)


class MemoryGovernanceStore:
    def __init__(self) -> None:
        self.transactions: dict[str, EvolutionTransactionRecord] = {}
        self.items: list[EvolutionTransactionItemRecord] = []
        self.revocations: list[RevocationRequestRecord] = []

    async def start_transaction(
        self,
        *,
        workspace_key: str,
        transaction_kind: str,
        idempotency_key: str,
        plan_hash: str,
        actor: str = "autoskill-sidecar",
        cause: dict[str, object] | None = None,
        source_evidence_ids: list[UUID] | None = None,
        source_memory_ids: list[UUID] | None = None,
        policy_snapshot: dict[str, object] | None = None,
        rollback_of_transaction_id: UUID | None = None,
    ) -> TransactionStartResult:
        existing = self.transactions.get(idempotency_key)
        if existing:
            return TransactionStartResult(transaction=existing, created=False)
        record = EvolutionTransactionRecord(
            evolution_transaction_id=uuid4(),
            workspace_id=uuid4(),
            workspace_key=workspace_key,
            transaction_kind=transaction_kind,
            status="planned",
            idempotency_key=idempotency_key,
            plan_hash=plan_hash,
            actor=actor,
            cause=cause or {},
            source_evidence_ids=source_evidence_ids or [],
            source_memory_ids=source_memory_ids or [],
            policy_snapshot=policy_snapshot or {},
            metrics={},
            rollback_of_transaction_id=rollback_of_transaction_id,
            started_at=datetime.now(UTC),
            committed_at=None,
            rolled_back_at=None,
        )
        self.transactions[idempotency_key] = record
        return TransactionStartResult(transaction=record, created=True)

    async def update_transaction_status(
        self,
        *,
        evolution_transaction_id: UUID,
        status: str,
        metrics: dict[str, object] | None = None,
    ) -> EvolutionTransactionRecord | None:
        for key, transaction in list(self.transactions.items()):
            if transaction.evolution_transaction_id == evolution_transaction_id:
                updated = EvolutionTransactionRecord(
                    **(transaction.__dict__ | {"status": status, "metrics": metrics or {}})
                )
                self.transactions[key] = updated
                return updated
        return None

    async def record_transaction_item(
        self,
        *,
        evolution_transaction_id: UUID,
        item_kind: str,
        activation_state: str,
        item_id: UUID | None = None,
        relative_path: str | None = None,
        before_hash: str | None = None,
        after_hash: str | None = None,
        rollback_action: dict[str, object] | None = None,
    ) -> EvolutionTransactionItemRecord:
        item = EvolutionTransactionItemRecord(
            transaction_item_id=uuid4(),
            evolution_transaction_id=evolution_transaction_id,
            item_kind=item_kind,
            item_id=item_id,
            relative_path=relative_path,
            before_hash=before_hash,
            after_hash=after_hash,
            activation_state=activation_state,
            rollback_action=rollback_action or {},
            created_at=datetime.now(UTC),
        )
        self.items.append(item)
        return item

    async def request_revocation(
        self,
        *,
        workspace_key: str,
        request_kind: str,
        root_object_type: str,
        root_object_id: UUID,
        traversal_summary: dict[str, object] | None = None,
        created_by_job_id: UUID | None = None,
    ) -> RevocationRequestRecord:
        request = RevocationRequestRecord(
            revocation_request_id=uuid4(),
            workspace_id=uuid4(),
            workspace_key=workspace_key,
            request_kind=request_kind,
            root_object_type=root_object_type,
            root_object_id=root_object_id,
            status="queued",
            traversal_summary=traversal_summary or {},
            created_by_job_id=created_by_job_id,
            created_at=datetime.now(UTC),
            completed_at=None,
        )
        self.revocations.append(request)
        return request


def test_governance_api_records_transaction_item_and_revocation() -> None:
    store = MemoryGovernanceStore()
    app = create_app(governance_store=store)
    start_route = next(
        route for route in app.routes if route.path == "/v1/evolution/transactions/start"
    )
    status_route = next(
        route
        for route in app.routes
        if route.path == "/v1/evolution/transactions/{transaction_id}/status"
    )
    item_route = next(
        route
        for route in app.routes
        if route.path == "/v1/evolution/transactions/{transaction_id}/items"
    )
    revocation_route = next(
        route for route in app.routes if route.path == "/v1/revocations/request"
    )

    root_object_id = uuid4()

    async def run():
        started = await start_route.endpoint(
            request=EvolutionTransactionStartRequest(
                workspace_id="dev-01",
                transaction_kind="create_skill",
                idempotency_key="candidate:one",
                plan_hash="abc123",
                cause={"source": "test"},
            )
        )
        duplicate = await start_route.endpoint(
            request=EvolutionTransactionStartRequest(
                workspace_id="dev-01",
                transaction_kind="create_skill",
                idempotency_key="candidate:one",
                plan_hash="abc123",
            )
        )
        transaction_id = UUID(started.transaction["evolution_transaction_id"])
        updated = await status_route.endpoint(
            transaction_id=transaction_id,
            request=EvolutionTransactionStatusRequest(status="staged", metrics={"items": 1}),
        )
        item = await item_route.endpoint(
            transaction_id=transaction_id,
            request=EvolutionTransactionItemRequest(
                item_kind="skill_file",
                activation_state="staged",
                relative_path="skills/autoskill/example/SKILL.md",
                after_hash="def456",
                rollback_action={"delete": True},
            ),
        )
        revocation = await revocation_route.endpoint(
            request=RevocationRequestCreateRequest(
                workspace_id="dev-01",
                request_kind="rollback",
                root_object_type="skill_version",
                root_object_id=root_object_id,
                traversal_summary={"queued": True},
            )
        )
        return started, duplicate, updated, item, revocation

    started, duplicate, updated, item, revocation = asyncio.run(run())

    assert started.created is True
    assert duplicate.created is False
    assert updated.transaction["status"] == "staged"
    assert updated.transaction["metrics"] == {"items": 1}
    assert item.item["relative_path"] == "skills/autoskill/example/SKILL.md"
    assert revocation.revocation["root_object_id"] == str(root_object_id)
    assert revocation.revocation["status"] == "queued"
