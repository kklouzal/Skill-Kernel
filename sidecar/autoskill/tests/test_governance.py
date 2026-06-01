import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from autoskill.api.app import (
    EvolutionTransactionItemRequest,
    EvolutionTransactionStartRequest,
    EvolutionTransactionStatusRequest,
    ProvenanceEdgeCreateRequest,
    RevocationRequestCreateRequest,
    RevocationTraversalPreviewRequest,
    create_app,
)
from autoskill.db.governance import (
    EvolutionTransactionItemRecord,
    EvolutionTransactionRecord,
    ProvenanceEdgeCreateResult,
    ProvenanceEdgeRecord,
    RevocationRequestRecord,
    RevocationTraversalRecord,
    TransactionStartResult,
)


class MemoryGovernanceStore:
    def __init__(self) -> None:
        self.transactions: dict[str, EvolutionTransactionRecord] = {}
        self.items: list[EvolutionTransactionItemRecord] = []
        self.edges: list[ProvenanceEdgeRecord] = []
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

    async def list_transaction_items(
        self,
        *,
        evolution_transaction_id: UUID,
    ) -> list[EvolutionTransactionItemRecord]:
        return [
            item
            for item in reversed(self.items)
            if item.evolution_transaction_id == evolution_transaction_id
        ]

    async def record_provenance_edge(
        self,
        *,
        workspace_key: str,
        source_kind: str,
        source_id: UUID,
        derived_kind: str,
        derived_id: UUID,
        relation: str,
    ) -> ProvenanceEdgeCreateResult:
        for edge in self.edges:
            if (
                edge.source_kind == source_kind
                and edge.source_id == source_id
                and edge.derived_kind == derived_kind
                and edge.derived_id == derived_id
                and edge.relation == relation
            ):
                return ProvenanceEdgeCreateResult(edge=edge, created=False)
        edge = ProvenanceEdgeRecord(
            provenance_edge_id=uuid4(),
            workspace_id=uuid4(),
            workspace_key=workspace_key,
            source_kind=source_kind,
            source_id=source_id,
            derived_kind=derived_kind,
            derived_id=derived_id,
            relation=relation,
            created_at=datetime.now(UTC),
        )
        self.edges.append(edge)
        return ProvenanceEdgeCreateResult(edge=edge, created=True)

    async def preview_revocation_traversal(
        self,
        *,
        workspace_key: str,
        root_object_type: str,
        root_object_id: UUID,
        max_depth: int = 8,
        max_nodes: int = 500,
    ) -> RevocationTraversalRecord:
        impacted: list[dict[str, object]] = [
            {
                "object_type": root_object_type,
                "object_id": str(root_object_id),
                "depth": 0,
            }
        ]
        traversed_edges: list[dict[str, object]] = []
        frontier = [(root_object_type, root_object_id, 0)]
        seen = {(root_object_type, root_object_id)}
        while frontier and len(impacted) < max_nodes:
            object_type, object_id, depth = frontier.pop(0)
            if depth >= max_depth:
                continue
            for edge in self.edges:
                if edge.source_kind != object_type or edge.source_id != object_id:
                    continue
                traversed_edges.append(
                    {
                        "provenance_edge_id": str(edge.provenance_edge_id),
                        "source_kind": edge.source_kind,
                        "source_id": str(edge.source_id),
                        "derived_kind": edge.derived_kind,
                        "derived_id": str(edge.derived_id),
                        "relation": edge.relation,
                    }
                )
                key = (edge.derived_kind, edge.derived_id)
                if key in seen:
                    continue
                seen.add(key)
                impacted.append(
                    {
                        "object_type": edge.derived_kind,
                        "object_id": str(edge.derived_id),
                        "depth": depth + 1,
                    }
                )
                frontier.append((edge.derived_kind, edge.derived_id, depth + 1))
        return RevocationTraversalRecord(
            workspace_id=None,
            workspace_key=workspace_key,
            root_object_type=root_object_type,
            root_object_id=root_object_id,
            impacted_objects=impacted,
            edges=traversed_edges,
            truncated=bool(frontier and len(impacted) >= max_nodes),
            max_depth=max_depth,
            max_nodes=max_nodes,
        )

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

    async def claim_next_revocation_request(
        self,
        *,
        workspace_key: str | None = None,
        request_kind: str = "rollback",
        root_object_type: str | None = None,
        worker_id: str | None = None,
    ) -> RevocationRequestRecord | None:
        for index, request in enumerate(self.revocations):
            if request.status != "queued" or request.request_kind != request_kind:
                continue
            if workspace_key is not None and request.workspace_key != workspace_key:
                continue
            if root_object_type is not None and request.root_object_type != root_object_type:
                continue
            updated = RevocationRequestRecord(
                **(
                    request.__dict__
                    | {
                        "status": "processing",
                        "traversal_summary": request.traversal_summary
                        | ({"claimed_by": worker_id} if worker_id else {}),
                    }
                )
            )
            self.revocations[index] = updated
            return updated
        return None

    async def complete_revocation_request(
        self,
        *,
        revocation_request_id: UUID,
        status: str,
        traversal_summary: dict[str, object],
    ) -> RevocationRequestRecord | None:
        for index, request in enumerate(self.revocations):
            if request.revocation_request_id != revocation_request_id:
                continue
            updated = RevocationRequestRecord(
                **(
                    request.__dict__
                    | {
                        "status": status,
                        "traversal_summary": traversal_summary,
                        "completed_at": datetime.now(UTC),
                    }
                )
            )
            self.revocations[index] = updated
            return updated
        return None


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
    edge_route = next(route for route in app.routes if route.path == "/v1/provenance/edges")
    preview_route = next(route for route in app.routes if route.path == "/v1/revocations/preview")
    revocation_route = next(
        route for route in app.routes if route.path == "/v1/revocations/request"
    )

    root_object_id = uuid4()
    evidence_id = uuid4()

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
        edge = await edge_route.endpoint(
            request=ProvenanceEdgeCreateRequest(
                workspace_id="dev-01",
                source_kind="evidence_item",
                source_id=evidence_id,
                derived_kind="skill_version",
                derived_id=root_object_id,
                relation="proposed_from",
            ),
        )
        duplicate_edge = await edge_route.endpoint(
            request=ProvenanceEdgeCreateRequest(
                workspace_id="dev-01",
                source_kind="evidence_item",
                source_id=evidence_id,
                derived_kind="skill_version",
                derived_id=root_object_id,
                relation="proposed_from",
            ),
        )
        preview = await preview_route.endpoint(
            request=RevocationTraversalPreviewRequest(
                workspace_id="dev-01",
                root_object_type="evidence_item",
                root_object_id=evidence_id,
            )
        )
        revocation = await revocation_route.endpoint(
            request=RevocationRequestCreateRequest(
                workspace_id="dev-01",
                request_kind="rollback",
                root_object_type="evidence_item",
                root_object_id=evidence_id,
            )
        )
        return started, duplicate, updated, item, edge, duplicate_edge, preview, revocation

    started, duplicate, updated, item, edge, duplicate_edge, preview, revocation = asyncio.run(
        run()
    )

    assert started.created is True
    assert duplicate.created is False
    assert updated.transaction["status"] == "staged"
    assert updated.transaction["metrics"] == {"items": 1}
    assert item.item["relative_path"] == "skills/autoskill/example/SKILL.md"
    assert edge.created is True
    assert duplicate_edge.created is False
    assert preview.traversal["impacted_count"] == 2
    assert preview.traversal["impacted_objects"][1]["object_type"] == "skill_version"
    assert revocation.revocation["root_object_id"] == str(evidence_id)
    assert revocation.revocation["status"] == "queued"
    assert revocation.revocation["traversal_summary"]["impacted_count"] == 2
