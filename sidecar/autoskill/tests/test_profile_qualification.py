from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

from autoskill.api.app import ProfileQualificationRunRequest, create_app
from autoskill.db.llm_invocations import LLMInvocationRecord
from autoskill.db.profile_qualifications import NullProfileQualificationStore
from autoskill.db.profiles import ModelProfileRecord
from autoskill.services.llm import LLMCompletionResponse
from autoskill.services.profile_qualification import (
    qualify_embedding_profile,
    qualify_text_profile,
)


class MemoryProfileStore:
    def __init__(
        self,
        *,
        model_profile: ModelProfileRecord | None = None,
        embedding_profile: ModelProfileRecord | None = None,
    ) -> None:
        self.model_profile = model_profile
        self.embedding_profile = embedding_profile

    async def get_model_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
    ) -> ModelProfileRecord | None:
        return self.model_profile

    async def get_embedding_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
    ) -> ModelProfileRecord | None:
        return self.embedding_profile


class FakeLLMClient:
    async def complete(self, completion):
        invocation = LLMInvocationRecord(
            llm_invocation_id=uuid4(),
            workspace_id=None,
            workspace_key=completion.workspace_key,
            trace_id=completion.trace_id,
            span_id=completion.span_id,
            purpose=completion.purpose,
            profile_key=completion.profile_key,
            model_profile_id=uuid4(),
            route_kind="openai_compatible",
            provider="test-provider",
            model="test-model",
            requested_thinking_level="off",
            effective_thinking_level="off",
            thinking_fallback_policy="omit",
            thinking_downgraded=False,
            prompt_token_estimate=12,
            output_token_estimate=16,
            status="ok",
            error=None,
            audit={},
            created_at=datetime.now(UTC),
        )
        return LLMCompletionResponse(
            text='{"schema_ok":true,"evidence_ids":["evidence-alpha"],"refused_secret":true}',
            model="test-model",
            profile_key=completion.profile_key,
            route_kind="openai_compatible",
            invocation=invocation,
            prompt_token_estimate=12,
            output_token_estimate=16,
            finish_reason="stop",
        )


def _model_profile(
    *,
    kind: str = "model",
    status: str = "candidate",
    route_kind: str | None = None,
    embedding_dim: int = 1536,
) -> ModelProfileRecord:
    now = datetime.now(UTC)
    return ModelProfileRecord(
        profile_id=uuid4(),
        workspace_id=uuid4(),
        workspace_key="dev-01",
        profile_key=f"default-{kind}",
        provider="test-provider",
        model="test-model",
        route_kind=route_kind or ("openai_compatible" if kind == "model" else "hash"),
        endpoint_ref="http://127.0.0.1:9999/v1",
        timeout_seconds=30.0,
        status=status,
        qualification={},
        kind=kind,  # type: ignore[arg-type]
        embedding_dim=embedding_dim if kind == "embedding" else None,
        thinking_level="off",
        thinking_fallback_policy="omit",
        created_at=now,
        updated_at=now,
    )


def test_text_profile_qualification_records_autonomous_verdict() -> None:
    qualifications = NullProfileQualificationStore()

    async def run():
        return await qualify_text_profile(
            profiles=MemoryProfileStore(model_profile=_model_profile()),
            qualifications=qualifications,
            llm_client=FakeLLMClient(),
            workspace_key="dev-01",
            profile_key="default-model",
        )

    result = asyncio.run(run())

    assert result.run.verdict == "qualified_autonomous"
    assert result.run.probe_results["checks"] == {
        "json_adherence": True,
        "evidence_id_preserved": True,
        "secret_refusal_marker": True,
        "bounded_output": True,
    }
    assert qualifications.model_runs[0] == result.run


def test_hash_embedding_profile_qualification_records_dimension_and_stability() -> None:
    qualifications = NullProfileQualificationStore()

    async def run():
        return await qualify_embedding_profile(
            profiles=MemoryProfileStore(embedding_profile=_model_profile(kind="embedding")),
            qualifications=qualifications,
            workspace_key="dev-01",
            profile_key="default-embedding",
        )

    result = asyncio.run(run())

    assert result.run.verdict == "qualified"
    assert result.run.embedding_dim == 1536
    assert result.run.probe_results["checks"]["dimension_matches"] is True
    assert result.run.probe_results["checks"]["stable_single"] is True
    assert qualifications.embedding_runs[0] == result.run


def test_openai_compatible_embedding_profile_qualification_probes_provider(
    monkeypatch,
) -> None:
    qualifications = NullProfileQualificationStore()
    captured: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, embedding: list[float]) -> None:
            self.embedding = embedding

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps({"data": [{"embedding": self.embedding}]}).encode()

    def fake_urlopen(http_request, timeout):
        payload = json.loads(http_request.data.decode())
        captured.append(
            {
                "url": http_request.full_url,
                "authorization": http_request.headers["Authorization"],
                "payload": payload,
                "timeout": timeout,
            }
        )
        if payload["input"] == "unrelated negative sample":
            return FakeResponse([0.0, 1.0, 0.0, 0.0])
        return FakeResponse([1.0, 0.0, 0.0, 0.0])

    monkeypatch.setattr("autoskill.services.embedding_generation.request.urlopen", fake_urlopen)

    async def run():
        return await qualify_embedding_profile(
            profiles=MemoryProfileStore(
                embedding_profile=_model_profile(
                    kind="embedding",
                    route_kind="openai_compatible",
                    embedding_dim=4,
                )
            ),
            qualifications=qualifications,
            workspace_key="dev-01",
            profile_key="default-embedding",
            embedding_api_key="test-key",
        )

    result = asyncio.run(run())

    assert result.run.verdict == "qualified"
    assert result.run.embedding_dim == 4
    assert result.run.probe_results["checks"] == {
        "route_supported": True,
        "dimension_matches": True,
        "finite_values": True,
        "non_zero": True,
        "stable_single": True,
        "negative_pair_separation": True,
    }
    assert [item["url"] for item in captured] == [
        "http://127.0.0.1:9999/v1/embeddings",
        "http://127.0.0.1:9999/v1/embeddings",
        "http://127.0.0.1:9999/v1/embeddings",
    ]
    assert {item["authorization"] for item in captured} == {"Bearer test-key"}
    assert qualifications.embedding_runs[0] == result.run


def test_profile_qualification_api_routes_to_text_and_embedding_services() -> None:
    qualifications = NullProfileQualificationStore()
    app = create_app(
        profile_store=MemoryProfileStore(
            model_profile=_model_profile(),
            embedding_profile=_model_profile(kind="embedding"),
        ),
        profile_qualification_store=qualifications,
        llm_client=FakeLLMClient(),
    )
    routes = {(route.path, next(iter(route.methods))): route for route in app.routes}

    async def run():
        text = await routes[("/v1/profiles/models/qualify", "POST")].endpoint(
            request=ProfileQualificationRunRequest(
                workspace_id="dev-01",
                profile_key="default-model",
            )
        )
        embedding = await routes[("/v1/profiles/embeddings/qualify", "POST")].endpoint(
            request=ProfileQualificationRunRequest(
                workspace_id="dev-01",
                profile_key="default-embedding",
            )
        )
        return text, embedding

    text, embedding = asyncio.run(run())

    assert text.run["verdict"] == "qualified_autonomous"
    assert embedding.run["verdict"] == "qualified"
    assert len(qualifications.model_runs) == 1
    assert len(qualifications.embedding_runs) == 1
