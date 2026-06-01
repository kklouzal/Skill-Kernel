import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from autoskill.api.app import (
    ContextArtifactRecordRequest,
    ContextTokenLedgerRequest,
    DiagnosticSignalRequest,
    EmbeddingProfileUpsertRequest,
    ExecutorProfileUpsertRequest,
    ModelProfileUpsertRequest,
    TraceSpanStartRequest,
    create_app,
)
from autoskill.core.audit import AuditRecord, verify_hash_chain
from autoskill.db.skills import SkillRecord


class MemorySkillStore:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.calls: list[dict[str, object]] = []
        self.skills = [
            SkillRecord(
                skill_id=uuid4(),
                workspace_id=uuid4(),
                workspace_key="dev-01",
                slug="autoskill-example",
                name="autoskill-example",
                source="autoskill",
                lifecycle_state="active",
                active_version_id=uuid4(),
                active_version=2,
                scanner_status="passed",
                evaluator_status="passed",
                compiled_sha256="abc123",
                manifest={"schema": "autoskill.writer-manifest.v1"},
                last_canary_status="passed",
                freeze_reason=None,
                created_at=now,
                updated_at=now,
                frozen_at=None,
            )
        ]

    async def list_skills(
        self,
        *,
        workspace_key: str | None = None,
        lifecycle_state: str | None = None,
        limit: int = 100,
    ) -> list[SkillRecord]:
        self.calls.append(
            {
                "workspace_key": workspace_key,
                "lifecycle_state": lifecycle_state,
                "limit": limit,
            }
        )
        skills = self.skills
        if workspace_key is not None:
            skills = [skill for skill in skills if skill.workspace_key == workspace_key]
        if lifecycle_state is not None:
            skills = [skill for skill in skills if skill.lifecycle_state == lifecycle_state]
        return skills[:limit]


class MemoryAuditStore:
    def __init__(self) -> None:
        first = AuditRecord(
            action="create",
            subject_type="skill",
            subject_id="autoskill-example",
        ).sealed()
        second = AuditRecord(
            action="activate",
            subject_type="skill",
            subject_id="autoskill-example",
            previous_hash=first.audit_hash,
        ).sealed()
        self.records = [first, second]

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


def test_skills_endpoint_lists_persisted_skill_metadata() -> None:
    skill_store = MemorySkillStore()
    app = create_app(skill_store=skill_store)
    route = next(route for route in app.routes if route.path == "/v1/skills")

    async def run():
        return await route.endpoint(
            workspace_id="dev-01",
            lifecycle_state="active",
            limit=50,
        )

    response = asyncio.run(run())

    assert response.skills[0]["slug"] == "autoskill-example"
    assert response.skills[0]["active_version"] == 2
    assert response.skills[0]["scanner_status"] == "passed"
    assert skill_store.calls == [
        {"workspace_key": "dev-01", "lifecycle_state": "active", "limit": 50}
    ]


def test_audit_recent_endpoint_returns_records_and_chain_status() -> None:
    app = create_app(audit_store=MemoryAuditStore())
    route = next(route for route in app.routes if route.path == "/v1/audit/recent")

    async def run():
        return await route.endpoint(workspace_id="dev-01", limit=10)

    response = asyncio.run(run())

    assert response.chain_valid is True
    assert [record["action"] for record in response.audit] == ["activate", "create"]


def test_v14_trace_diagnostics_profiles_and_context_surfaces() -> None:
    app = create_app()
    routes = {
        (route.path, next(iter(route.methods - {"HEAD", "OPTIONS"}))): route
        for route in app.routes
        if hasattr(route, "methods")
    }

    async def run():
        trace = await routes[("/v1/trace/spans", "POST")].endpoint(
            request=TraceSpanStartRequest(
                workspace_id="dev-01",
                operation_name="test.trace",
                operation_kind="ingest",
                safe_attributes={"payload": "redacted"},
            )
        )
        profile = await routes[("/v1/profiles/executors", "POST")].endpoint(
            request=ExecutorProfileUpsertRequest(
                workspace_id="dev-01",
                profile_key="codex-dev",
                agent_backend="codex",
                sandbox="danger-full-access",
                available_tools=["exec"],
            )
        )
        model = await routes[("/v1/profiles/models", "POST")].endpoint(
            request=ModelProfileUpsertRequest(
                workspace_id="dev-01",
                profile_key="text-default",
                provider="openclaw",
                model="configured-text-model",
                route_kind="openclaw",
                status="qualified",
            )
        )
        embedding = await routes[("/v1/profiles/embeddings", "POST")].endpoint(
            request=EmbeddingProfileUpsertRequest(
                workspace_id="dev-01",
                profile_key="embedding-default",
                provider="hash",
                model="autoskill-hash-embedding.v1",
                route_kind="hash",
                embedding_dim=1536,
                status="qualified",
            )
        )
        momentum = await routes[("/v1/diagnostics/momentum", "POST")].endpoint(
            request=DiagnosticSignalRequest(
                workspace_id="dev-01",
                diagnostic_kind="probe_failure",
                root_cause_hypothesis="Probe failed repeatedly.",
                suggested_change_direction="Add a narrower verification step.",
                evidence_delta=2,
            )
        )
        artifact = await routes[("/v1/context/artifacts", "POST")].endpoint(
            request=ContextArtifactRecordRequest(
                workspace_id="dev-01",
                artifact_kind="broker_hint",
                source_object_type="broker_policy",
                text="Use only when directly relevant.",
                max_tokens=20,
                safety_status="passed",
            )
        )
        ledger = await routes[("/v1/context/token-ledger", "POST")].endpoint(
            request=ContextTokenLedgerRequest(
                workspace_id="dev-01",
                visibility_state="skill_visible",
                token_count=artifact.artifact["token_count"],
            )
        )
        return trace, profile, model, embedding, momentum, artifact, ledger

    trace, profile, model, embedding, momentum, artifact, ledger = asyncio.run(run())

    assert trace.span["operation_kind"] == "ingest"
    assert profile.profile["profile_key"] == "codex-dev"
    assert model.profile["kind"] == "model"
    assert embedding.profile["embedding_dim"] == 1536
    assert momentum.momentum["status"] == "ready_for_probe"
    assert artifact.artifact["budget_status"] == "passed"
    assert ledger.ledger["visibility_state"] == "skill_visible"
