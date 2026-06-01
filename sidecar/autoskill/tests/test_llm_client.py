import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from autoskill.db.llm_invocations import LLMInvocationRecord
from autoskill.db.profiles import ModelProfileRecord
from autoskill.services.llm import (
    LLMClient,
    LLMCompletionRequest,
    LLMMessage,
    LLMRouteUnsupportedError,
    LLMThinkingPolicyError,
)


class MemoryProfileStore:
    def __init__(self, profile: ModelProfileRecord | None) -> None:
        self.profile = profile
        self.calls: list[dict[str, str]] = []

    async def get_model_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
    ) -> ModelProfileRecord | None:
        self.calls.append({"workspace_key": workspace_key, "profile_key": profile_key})
        return self.profile


class MemoryInvocationStore:
    def __init__(self) -> None:
        self.records: list[LLMInvocationRecord] = []

    async def record_invocation(self, **kwargs) -> LLMInvocationRecord:
        record = LLMInvocationRecord(
            llm_invocation_id=uuid4(),
            workspace_id=None,
            workspace_key=kwargs["workspace_key"],
            trace_id=kwargs.get("trace_id"),
            span_id=kwargs.get("span_id"),
            purpose=kwargs["purpose"],
            profile_key=kwargs["profile_key"],
            model_profile_id=kwargs.get("model_profile_id"),
            route_kind=kwargs["route_kind"],
            provider=kwargs["provider"],
            model=kwargs["model"],
            requested_thinking_level=kwargs.get("requested_thinking_level"),
            effective_thinking_level=kwargs.get("effective_thinking_level"),
            thinking_fallback_policy=kwargs.get("thinking_fallback_policy", "omit"),
            thinking_downgraded=kwargs.get("thinking_downgraded", False),
            prompt_token_estimate=kwargs.get("prompt_token_estimate", 0),
            output_token_estimate=kwargs.get("output_token_estimate", 0),
            status=kwargs["status"],
            error=kwargs.get("error"),
            audit=kwargs.get("audit") or {},
            created_at=datetime.now(UTC),
        )
        self.records.append(record)
        return record


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(
            {
                "id": "chatcmpl-test",
                "choices": [
                    {
                        "message": {"content": "{\"candidate\": true}"},
                        "finish_reason": "stop",
                    }
                ],
            }
        ).encode()


def _profile(
    *,
    route_kind: str = "openai_compatible",
    thinking_level: str = "off",
    thinking_fallback_policy: str = "omit",
    qualification: dict[str, object] | None = None,
) -> ModelProfileRecord:
    now = datetime.now(UTC)
    return ModelProfileRecord(
        profile_id=uuid4(),
        workspace_id=uuid4(),
        workspace_key="dev-01",
        profile_key="default-text",
        provider="test-provider",
        model="test-model",
        route_kind=route_kind,
        endpoint_ref="http://127.0.0.1:9999/v1",
        timeout_seconds=12.5,
        thinking_level=thinking_level,
        thinking_fallback_policy=thinking_fallback_policy,
        status="qualified",
        qualification=qualification or {},
        kind="model",
        embedding_dim=None,
        created_at=now,
        updated_at=now,
    )


def _request() -> LLMCompletionRequest:
    return LLMCompletionRequest(
        workspace_key="dev-01",
        profile_key="default-text",
        purpose="skill_creation_plan",
        messages=[LLMMessage(role="user", content="Return a JSON proposal.")],
        trace_id=uuid4(),
        span_id=uuid4(),
    )


def test_llm_client_posts_openai_compatible_request_and_records_safe_audit() -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(http_request, timeout):
        captured["url"] = http_request.full_url
        captured["timeout"] = timeout
        captured["authorization"] = http_request.headers["Authorization"]
        captured["payload"] = json.loads(http_request.data.decode())
        return FakeResponse()

    invocations = MemoryInvocationStore()
    client = LLMClient(
        profiles=MemoryProfileStore(
            _profile(
                thinking_level="medium",
                qualification={
                    "supports_thinking": True,
                    "thinking_request_field": "reasoning_effort",
                },
            )
        ),
        invocations=invocations,
        settings=SimpleNamespace(llm_api_key="secret-test-key"),
        urlopen=fake_urlopen,
    )

    response = asyncio.run(client.complete(_request()))

    assert response.text == "{\"candidate\": true}"
    assert captured["url"] == "http://127.0.0.1:9999/v1/chat/completions"
    assert captured["timeout"] == 12.5
    assert captured["authorization"] == "Bearer secret-test-key"
    assert captured["payload"]["reasoning_effort"] == "medium"
    assert invocations.records[0].status == "ok"
    assert invocations.records[0].requested_thinking_level == "medium"
    assert invocations.records[0].effective_thinking_level == "medium"
    assert invocations.records[0].audit == {
        "endpoint_route": "chat_completions",
        "finish_reason": "stop",
        "provider_request_id": "chatcmpl-test",
    }


def test_llm_client_records_strict_thinking_policy_failure() -> None:
    invocations = MemoryInvocationStore()
    client = LLMClient(
        profiles=MemoryProfileStore(
            _profile(thinking_level="high", thinking_fallback_policy="strict")
        ),
        invocations=invocations,
        settings=SimpleNamespace(llm_api_key="secret-test-key"),
        urlopen=lambda *_args, **_kwargs: FakeResponse(),
    )

    with pytest.raises(LLMThinkingPolicyError):
        asyncio.run(client.complete(_request()))

    assert invocations.records[0].status == "error"
    assert "thinking_level=high" in str(invocations.records[0].error)


def test_llm_client_records_openclaw_route_as_unsupported() -> None:
    invocations = MemoryInvocationStore()
    client = LLMClient(
        profiles=MemoryProfileStore(_profile(route_kind="openclaw")),
        invocations=invocations,
        settings=SimpleNamespace(llm_api_key="secret-test-key"),
    )

    with pytest.raises(LLMRouteUnsupportedError):
        asyncio.run(client.complete(_request()))

    assert invocations.records[0].status == "unsupported"
    assert invocations.records[0].audit == {"endpoint_route": "openclaw"}
