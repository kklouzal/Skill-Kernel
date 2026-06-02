import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from autoskill.api.app import (
    ContextArtifactRecordRequest,
    ContextBudgetEventRequest,
    ContextCompileRunRequest,
    ContextSkillIRCompileRequest,
    ContextTokenLedgerOutcomeRequest,
    ContextTokenLedgerRequest,
    ControlFlowEventRequest,
    DiagnosticSignalRequest,
    EmbeddingProfileUpsertRequest,
    ExecutorProfileUpsertRequest,
    MemoryQuarantineDecisionRequest,
    MemoryQuarantineRequest,
    ModelProfileUpsertRequest,
    SemanticCompressionTrialRequest,
    TopologyProposalRequest,
    TopologySkillPayload,
    TraceSpanStartRequest,
    create_app,
)
from autoskill.core.audit import AuditRecord, verify_hash_chain
from autoskill.core.config import get_settings
from autoskill.core.skillir import SkillIR
from autoskill.db.broker_policy import NullBrokerPolicyStore
from autoskill.db.jobs import JobQueueSummary, NullJobStore
from autoskill.db.profiles import ExecutorProfileRecord, ModelProfileRecord
from autoskill.db.skills import SkillRecord
from autoskill.db.topology import NullTopologyStore


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


class MemoryReadinessProfileStore:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.executor_profiles = [
            ExecutorProfileRecord(
                executor_profile_id=uuid4(),
                workspace_id=uuid4(),
                workspace_key="dev-01",
                profile_key="codex-prod",
                model_family="gpt",
                agent_backend="codex",
                sandbox="danger-full-access",
                os_name="ubuntu",
                available_tools=["exec"],
                available_binaries=["git"],
                permissions={"filesystem": "workspace"},
                api_contracts={},
                status="active",
                created_at=now,
                updated_at=now,
            )
        ]
        self.model_profiles = [
            ModelProfileRecord(
                profile_id=uuid4(),
                workspace_id=uuid4(),
                workspace_key="dev-01",
                profile_key="text-prod",
                provider="openai-compatible",
                model="configured-text-model",
                route_kind="openai_compatible",
                endpoint_ref="AUTOSKILL_LLM_API_BASE_URL",
                timeout_seconds=30.0,
                thinking_level="medium",
                thinking_fallback_policy="omit",
                status="qualified",
                qualification={"verdict": "qualified"},
                kind="model",
                embedding_dim=None,
                created_at=now,
                updated_at=now,
            )
        ]
        self.embedding_profiles = [
            ModelProfileRecord(
                profile_id=uuid4(),
                workspace_id=uuid4(),
                workspace_key="dev-01",
                profile_key="embedding-prod",
                provider="openai-compatible",
                model="configured-embedding-model",
                route_kind="openai_compatible",
                endpoint_ref="AUTOSKILL_EMBEDDING_API_BASE_URL",
                timeout_seconds=15.0,
                thinking_level="off",
                thinking_fallback_policy="omit",
                status="active",
                qualification={"verdict": "qualified"},
                kind="embedding",
                embedding_dim=768,
                created_at=now,
                updated_at=now,
            )
        ]

    async def list_executor_profiles(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ExecutorProfileRecord]:
        profiles = [
            profile
            for profile in self.executor_profiles
            if profile.workspace_key == workspace_key
            and (status is None or profile.status == status)
        ]
        return profiles[:limit]

    async def list_model_profiles(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ModelProfileRecord]:
        profiles = [
            profile
            for profile in self.model_profiles
            if profile.workspace_key == workspace_key
            and (status is None or profile.status == status)
        ]
        return profiles[:limit]

    async def list_embedding_profiles(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ModelProfileRecord]:
        profiles = [
            profile
            for profile in self.embedding_profiles
            if profile.workspace_key == workspace_key
            and (status is None or profile.status == status)
        ]
        return profiles[:limit]


class MemoryReadinessJobStore(NullJobStore):
    def __init__(self, summaries: dict[str | None, JobQueueSummary]) -> None:
        self.summaries = summaries
        self.summary_calls: list[str | None] = []

    async def summary(self, *, workspace_key: str | None = None) -> JobQueueSummary:
        self.summary_calls.append(workspace_key)
        return self.summaries.get(workspace_key, JobQueueSummary(counts={}, by_kind={}))


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


def test_profile_list_endpoints_return_operator_profile_surfaces() -> None:
    app = create_app(profile_store=MemoryReadinessProfileStore())
    routes = {
        (route.path, next(iter(route.methods - {"HEAD", "OPTIONS"}))): route
        for route in app.routes
        if hasattr(route, "methods")
    }

    async def run():
        models = await routes[("/v1/profiles/models", "GET")].endpoint(
            workspace_id="dev-01",
            status=None,
            limit=10,
        )
        embeddings = await routes[("/v1/profiles/embeddings", "GET")].endpoint(
            workspace_id="dev-01",
            status="active",
            limit=10,
        )
        return models, embeddings

    models, embeddings = asyncio.run(run())

    assert models.profiles[0]["profile_key"] == "text-prod"
    assert models.profiles[0]["status"] == "qualified"
    assert embeddings.profiles[0]["profile_key"] == "embedding-prod"
    assert embeddings.profiles[0]["embedding_dim"] == 768


def test_deployment_readiness_reports_blockers_without_mutating_runtime() -> None:
    app = create_app(job_store=NullJobStore())
    route = next(route for route in app.routes if route.path == "/v1/deployment/readiness")

    async def run():
        return await route.endpoint(
            workspace_id="dev-01",
            replay_tag="production",
        )

    response = asyncio.run(run())

    assert response.ready is False
    assert "database_configured" in response.blockers
    assert "control_auth_configured" in response.blockers
    assert "ingest_auth_configured" in response.blockers
    assert "runtime_context_broker_enabled" in response.blockers
    assert "writer_roots_contained" not in response.blockers


def test_deployment_readiness_passes_when_required_gates_are_present(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AUTOSKILL_DATABASE_URL", "postgresql://example/skillkernel")
    monkeypatch.setenv("AUTOSKILL_CONTROL_TOKEN", "control-token")
    monkeypatch.setenv("AUTOSKILL_INGEST_TOKEN", "ingest-token")
    monkeypatch.setenv("AUTOSKILL_RUNTIME_CONTEXT_BROKER_ENABLED", "true")
    get_settings.cache_clear()

    broker_policies = NullBrokerPolicyStore()

    async def seed_broker_policy() -> None:
        await broker_policies.upsert_policy_version(
            workspace_key="dev-01",
            version="prod.v1",
            policy={"max_tokens": 800},
            status="active",
        )
        await broker_policies.record_replay_episode(
            workspace_key="dev-01",
            episode_key="prod-episode-1",
            redacted_user_intent="Diagnose a bounded OpenClaw failure.",
            expected_decision="skill_hint",
            tags=["production"],
        )

    asyncio.run(seed_broker_policy())

    app = create_app(
        job_store=NullJobStore(),
        profile_store=MemoryReadinessProfileStore(),
        broker_policy_store=broker_policies,
    )
    route = next(route for route in app.routes if route.path == "/v1/deployment/readiness")

    async def run():
        return await route.endpoint(
            authorization="Bearer control-token",
            workspace_id="dev-01",
            replay_tag="production",
        )

    response = asyncio.run(run())

    assert response.ready is True
    assert response.blockers == []
    assert response.checks["active_broker_policy"]["version"] == "prod.v1"
    assert response.checks["active_embedding_profile"]["dimensions"] == [768]

    get_settings.cache_clear()


def test_deployment_readiness_ignores_failed_jobs_from_other_workspaces(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AUTOSKILL_DATABASE_URL", "postgresql://example/skillkernel")
    monkeypatch.setenv("AUTOSKILL_CONTROL_TOKEN", "control-token")
    monkeypatch.setenv("AUTOSKILL_INGEST_TOKEN", "ingest-token")
    monkeypatch.setenv("AUTOSKILL_RUNTIME_CONTEXT_BROKER_ENABLED", "true")
    get_settings.cache_clear()

    broker_policies = NullBrokerPolicyStore()

    async def seed_broker_policy() -> None:
        await broker_policies.upsert_policy_version(
            workspace_key="dev-01",
            version="prod.v1",
            policy={"max_tokens": 800},
            status="active",
        )
        await broker_policies.record_replay_episode(
            workspace_key="dev-01",
            episode_key="prod-episode-1",
            redacted_user_intent="Diagnose a bounded OpenClaw failure.",
            expected_decision="skill_hint",
            tags=["production"],
        )

    asyncio.run(seed_broker_policy())
    job_store = MemoryReadinessJobStore(
        {
            None: JobQueueSummary(
                counts={"failed": 3},
                by_kind={"smoke.only": {"failed": 3}},
            ),
            "dev-01": JobQueueSummary(counts={}, by_kind={}),
        }
    )
    app = create_app(
        job_store=job_store,
        profile_store=MemoryReadinessProfileStore(),
        broker_policy_store=broker_policies,
    )
    route = next(route for route in app.routes if route.path == "/v1/deployment/readiness")

    async def run():
        return await route.endpoint(
            authorization="Bearer control-token",
            workspace_id="dev-01",
            replay_tag="production",
        )

    response = asyncio.run(run())

    assert response.ready is True
    assert "job_queue_has_no_failed_jobs" not in response.warnings
    assert job_store.summary_calls == ["dev-01"]

    get_settings.cache_clear()


def test_memory_quarantine_and_control_flow_surfaces_are_governed() -> None:
    app = create_app()
    routes = {
        (route.path, next(iter(route.methods - {"HEAD", "OPTIONS"}))): route
        for route in app.routes
        if hasattr(route, "methods")
    }
    source_id = uuid4()

    async def run():
        quarantined = await routes[("/v1/memory/quarantine", "POST")].endpoint(
            request=MemoryQuarantineRequest(
                workspace_id="dev-01",
                source_object_type="evidence",
                source_object_id=source_id,
                proposed_memory={
                    "memory_kind": "procedural_lesson",
                    "summary": "Use the retry gate only after redacted evidence recurs.",
                },
                taint={"source": "derived", "external_instruction": False},
                scanner_findings={"imperative_language": False},
            )
        )
        listed_pending = await routes[("/v1/memory/quarantine", "GET")].endpoint(
            workspace_id="dev-01",
            status="pending",
            limit=10,
        )
        decided = await routes[
            ("/v1/memory/quarantine/{quarantine_id}/decision", "POST")
        ].endpoint(
            quarantine_id=UUID(quarantined.memory["quarantine_id"]),
            request=MemoryQuarantineDecisionRequest(
                workspace_id="dev-01",
                status="approved",
                operator_id="operator-1",
                rationale="Scanner and provenance gates passed.",
            ),
        )
        event = await routes[("/v1/control-flow/events", "POST")].endpoint(
            request=ControlFlowEventRequest(
                workspace_id="dev-01",
                source_kind="memory",
                source_id=quarantined.memory["quarantine_id"],
                influence_kind="retrieval",
                run_id="run-1",
                decision={
                    "decision": "eligible_after_quarantine_approval",
                    "memory_status": decided.memory["status"],
                },
            )
        )
        listed_events = await routes[("/v1/control-flow/events", "GET")].endpoint(
            workspace_id="dev-01",
            source_kind="memory",
            influence_kind="retrieval",
            limit=10,
        )
        return quarantined, listed_pending, decided, event, listed_events

    quarantined, listed_pending, decided, event, listed_events = asyncio.run(run())

    assert quarantined.memory["status"] == "pending"
    assert listed_pending.memories[0]["quarantine_id"] == quarantined.memory["quarantine_id"]
    assert decided.memory["status"] == "approved"
    assert decided.memory["decided_at"] is not None
    assert event.event["source_kind"] == "memory"
    assert event.event["influence_kind"] == "retrieval"
    assert listed_events.events[0]["decision"]["memory_status"] == "approved"


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
        outcome = await routes[
            ("/v1/context/token-ledger/{ledger_id}/outcome", "POST")
        ].endpoint(
            ledger_id=ledger.ledger["context_token_ledger_id"],
            request=ContextTokenLedgerOutcomeRequest(
                workspace_id="dev-01",
                outcome="helped",
                utility_delta=0.25,
                task_success=True,
                token_savings=10,
            ),
        )
        compile_run = await routes[("/v1/context/compile-runs", "POST")].endpoint(
            request=ContextCompileRunRequest(
                workspace_id="dev-01",
                compiler_version="context-compiler.v1",
                input_skillir_hash="skillir-hash",
                output_manifest_hash="manifest-hash",
                target_runtime_tokens=350,
                actual_runtime_tokens=120,
                compression_ratio=0.4,
                semantic_equivalence_score=0.96,
                status="passed",
                context_artifact_id=artifact.artifact["context_artifact_id"],
            )
        )
        budget_event = await routes[("/v1/context/budget-events", "POST")].endpoint(
            request=ContextBudgetEventRequest(
                workspace_id="dev-01",
                event_type="compile_budget_gate",
                decision="accept",
                context_artifact_id=artifact.artifact["context_artifact_id"],
                tokens_delta=-180,
                marginal_success_delta=0.2,
                evidence={"gate": "token_budget_governor"},
            )
        )
        compression_trial = await routes[
            ("/v1/context/semantic-compression-trials", "POST")
        ].endpoint(
            request=SemanticCompressionTrialRequest(
                workspace_id="dev-01",
                source_tokens=300,
                candidate_tokens=120,
                preserved_requirements=8,
                lost_requirements=0,
                added_unsupported_requirements=0,
                equivalence_score=0.96,
                target_probe_pass_rate=1.0,
                regression_probe_pass_rate=1.0,
                status="passed",
                candidate_context_artifact_id=artifact.artifact["context_artifact_id"],
            )
        )
        return (
            trace,
            profile,
            model,
            embedding,
            momentum,
            artifact,
            ledger,
            outcome,
            compile_run,
            budget_event,
            compression_trial,
        )

    (
        trace,
        profile,
        model,
        embedding,
        momentum,
        artifact,
        ledger,
        outcome,
        compile_run,
        budget_event,
        compression_trial,
    ) = asyncio.run(run())

    assert trace.span["operation_kind"] == "ingest"
    assert profile.profile["profile_key"] == "codex-dev"
    assert model.profile["kind"] == "model"
    assert embedding.profile["embedding_dim"] == 1536
    assert momentum.momentum["status"] == "ready_for_probe"
    assert artifact.artifact["budget_status"] == "passed"
    assert ledger.ledger["visibility_state"] == "skill_visible"
    assert outcome.ledger["outcome"] == "helped"
    assert "marginal_value" in outcome.ledger["metadata"]
    assert compile_run.run["status"] == "passed"
    assert compile_run.run["context_artifact_id"] == artifact.artifact["context_artifact_id"]
    assert budget_event.event["decision"] == "accept"
    assert budget_event.event["evidence"]["gate"] == "token_budget_governor"
    assert compression_trial.trial["equivalence_score"] == 0.96
    assert compression_trial.trial["status"] == "passed"


def test_context_compile_skillir_endpoint_records_deterministic_gate() -> None:
    app = create_app()
    route = next(route for route in app.routes if route.path == "/v1/context/compile-skillir")
    skill = SkillIR(
        slug="autoskill-example",
        name="autoskill-example",
        description="Handle repeated workflow checks.",
        applicability=["A repeated workflow has validated evidence."],
        inputs=["User goal and cited evidence IDs."],
        preconditions=["Evidence is mature enough for proposal."],
        steps=["Inspect evidence.", "Run deterministic checks.", "Return bounded result."],
        outputs=["Bounded action or no-op decision."],
        effects=["Selected workflow path is evaluated without activation."],
        verification=["Confirm all required gates pass."],
        failure_handling=["Stop and report the blocking gate."],
        do_not_use_when=["The task lacks grounded evidence."],
        never=["Never include raw secrets or private user facts."],
        evidence_ids=["evidence-1"],
    )

    async def run():
        return await route.endpoint(
            request=ContextSkillIRCompileRequest(
                workspace_id="dev-01",
                skillir=skill,
            )
        )

    response = asyncio.run(run())

    assert response.result["status"] == "passed"
    assert response.result["context_artifact"]["artifact_kind"] == "skill_md"
    assert response.result["compile_run"]["status"] == "passed"
    assert response.result["budget_event"]["decision"] == "accept"
    assert response.result["semantic_compression_trial"]["status"] == "passed"


def test_topology_proposal_endpoint_persists_propose_only_operation() -> None:
    topology = NullTopologyStore()
    app = create_app(topology_store=topology)
    route = next(route for route in app.routes if route.path == "/v1/topology/propose")

    async def run():
        return await route.endpoint(
            request=TopologyProposalRequest(
                workspace_id="dev-01",
                operation_kind="compose",
                components=[
                    TopologySkillPayload(
                        skill_id=uuid4(),
                        slug="inspect-failure",
                        effects={"outputs": ["diagnostic"]},
                    ),
                    TopologySkillPayload(
                        skill_id=uuid4(),
                        slug="repair-failure",
                        effects={"outputs": ["patch"]},
                    ),
                ],
                composed_output=TopologySkillPayload(
                    slug="inspect-and-repair",
                    effects={"outputs": ["diagnostic", "patch"]},
                ),
                evidence_ids=[str(uuid4())],
            )
        )

    response = asyncio.run(run())

    assert response.proposal["status"] == "candidate"
    assert response.persistence is not None
    assert response.persistence["operation"]["operation_kind"] == "compose"
    assert {trial["trial_kind"] for trial in response.persistence["trials"]} == {
        "component_baseline",
        "composed_workflow",
        "shadowing",
        "broker_replay",
        "broker_canary",
    }
    assert topology.operations[0].evolution_transaction_id is not None


def test_topology_proposal_endpoint_records_blocked_trials() -> None:
    topology = NullTopologyStore()
    app = create_app(topology_store=topology)
    route = next(route for route in app.routes if route.path == "/v1/topology/propose")

    async def run():
        return await route.endpoint(
            request=TopologyProposalRequest(
                workspace_id="dev-01",
                operation_kind="decompose",
                subject=TopologySkillPayload(
                    skill_id=uuid4(),
                    slug="broad-maintenance",
                    effects={"outputs": ["diagnostic", "patch"]},
                ),
                successors=[
                    TopologySkillPayload(
                        slug="diagnose-maintenance",
                        effects={"outputs": ["diagnostic"]},
                    )
                ],
                evidence_ids=[str(uuid4())],
            )
        )

    response = asyncio.run(run())

    assert response.proposal["status"] == "blocked"
    assert response.persistence is not None
    assert response.persistence["operation"]["status"] == "blocked"
    assert {trial["status"] for trial in response.persistence["trials"]} == {"blocked"}
