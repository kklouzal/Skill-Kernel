import asyncio
from uuid import uuid4

from autoskill.api.app import SkillProfileCompatibilityUpsertRequest, create_app
from autoskill.core.config import effective_skillkernel_config, get_settings
from autoskill.db.compatibility import NullCompatibilityStore


def test_compatibility_api_records_executor_profile_status() -> None:
    store = NullCompatibilityStore()
    app = create_app(compatibility_store=store)
    route = next(route for route in app.routes if route.path == "/v1/profiles/compatibility")
    skill_version_id = uuid4()
    executor_profile_id = uuid4()

    async def run():
        return await route.endpoint(
            request=SkillProfileCompatibilityUpsertRequest(
                workspace_id="dev-01",
                skill_version_id=skill_version_id,
                executor_profile_id=executor_profile_id,
                status="blocked",
                evidence={"reason": "missing binary"},
            )
        )

    response = asyncio.run(run())

    assert response.compatibility["status"] == "blocked"
    assert response.compatibility["evidence"] == {"reason": "missing binary"}
    assert asyncio.run(
        store.list_statuses(
            workspace_key="dev-01",
            executor_profile_id=executor_profile_id,
            skill_version_ids=[skill_version_id],
        )
    ) == {skill_version_id: "blocked"}


def test_core_compatibility_handshake_endpoints_report_contract(monkeypatch) -> None:
    monkeypatch.setenv("AUTOSKILL_IGNORE_ENV_FILE", "1")
    monkeypatch.delenv("AUTOSKILL_DATABASE_URL", raising=False)
    monkeypatch.delenv("SKILLKERNEL_DATABASE_URL", raising=False)
    monkeypatch.delenv("AUTOSKILL_LLM_API_BASE_URL", raising=False)
    monkeypatch.delenv("AUTOSKILL_EMBEDDING_API_BASE_URL", raising=False)
    get_settings.cache_clear()
    app = create_app()
    routes = {
        (route.path, method): route
        for route in app.routes
        for method in route.methods
    }

    version = asyncio.run(routes[("/v1/version", "GET")].endpoint())
    capabilities = asyncio.run(routes[("/v1/capabilities", "GET")].endpoint())
    contract = asyncio.run(routes[("/v1/read-model-contract", "GET")].endpoint())
    ready = asyncio.run(routes[("/v1/health/ready", "GET")].endpoint())

    assert version.service == "skillkernel-core"
    assert version.api_contract_version == "skillkernel.api.v1"
    assert version.schema_migration_version == "0001_autoskill_schema"
    assert version.read_model_contract_version == "skillkernel.readmodels.v1"
    assert "guarded_action_requests" in version.features
    assert "semantic_adjudication" in version.degraded_features
    assert "embedding_generation" in version.degraded_features
    assert capabilities.capabilities["ingest_contract"] == {
        "path": "/v1/ingest/events",
        "method": "POST",
        "auth_mode": "bearer",
        "ingest_auth_configured": False,
        "event_schema": "autoskill.event-envelope.v1",
    }
    assert capabilities.capabilities["raw_vault_policy"]["browser_exposure"] == "forbidden"
    assert capabilities.capabilities["raw_vault_policy"][
        "raw_capture_requires_plugin_handshake"
    ] is True
    assert capabilities.capabilities["redaction_policy"][
        "plugin_redacts_before_forward"
    ] is True
    assert capabilities.capabilities["redaction_policy"]["secret_redaction_required"] is True
    assert capabilities.capabilities["embedding_generation"] is False
    assert capabilities.capabilities["embedding_profile_policy"] == {
        "provider": "hash",
        "production_ready": False,
        "degraded": True,
        "reason_code": "hash_embedding_provider_test_mode",
        "jobs_paused": True,
        "supported_production_providers": ["openclaw", "openai_compatible"],
    }
    assert capabilities.capabilities["topology_operations"] == [
        "create",
        "improve",
        "compose",
        "decompose",
    ]
    assert contract.contract["admin_base_path"] == "/admin/api/v1"
    assert contract.contract["content_policy"]["live_stream_raw_content"] == "forbidden"
    assert ready.ready is False
    assert ready.checks["database_configured"] is False
    assert ready.checks["embedding_profile_configured"] is False
    assert ready.checks["embedding_profile_degraded"] is True
    assert ready.checks["embedding_dependent_jobs_paused"] is True
    assert ready.checks["embedding_profile_ready_or_explicitly_degraded"] is True
    assert ready.checks["embedding_profile_degraded_reason"] == "hash_embedding_provider_test_mode"
    assert ready.checks["read_model_contract_version"] == "skillkernel.readmodels.v1"

    get_settings.cache_clear()


def test_effective_config_reflects_raw_conversation_capture_policy(monkeypatch) -> None:
    monkeypatch.setenv("AUTOSKILL_IGNORE_ENV_FILE", "1")
    monkeypatch.setenv("AUTOSKILL_PLUGIN_CAPTURE_RAW_CONVERSATION", "true")
    get_settings.cache_clear()

    config = effective_skillkernel_config()

    assert config["plugin"]["capture_raw_conversation"] is True

    get_settings.cache_clear()
