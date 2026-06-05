from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from typing import Protocol
from urllib import error, request
from uuid import UUID

from autoskill.db.llm_invocations import LLMInvocationRecord, LLMInvocationStore
from autoskill.db.observability import (
    NullObservabilityStore,
    ObservabilityStore,
    TraceStatus,
)
from autoskill.db.profiles import ModelProfileRecord, ProfileStore


class LLMClientError(RuntimeError):
    """Base error for typed LLM client failures."""


class LLMProfileNotFoundError(LLMClientError):
    """Raised when a configured text profile cannot be fetched."""


class LLMRouteUnsupportedError(LLMClientError):
    """Raised when a configured route is not available in this sidecar build."""


class LLMThinkingPolicyError(LLMClientError):
    """Raised when the configured thinking policy cannot be honored."""


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str

    def to_json(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class LLMCompletionRequest:
    workspace_key: str
    profile_key: str
    purpose: str
    messages: list[LLMMessage]
    max_output_tokens: int = 1024
    temperature: float = 0.0
    trace_id: UUID | None = None
    span_id: UUID | None = None


@dataclass(frozen=True)
class LLMCompletionResponse:
    text: str
    model: str
    profile_key: str
    route_kind: str
    invocation: LLMInvocationRecord
    prompt_token_estimate: int
    output_token_estimate: int
    finish_reason: str | None = None


@dataclass(frozen=True)
class ThinkingDecision:
    requested: str
    effective: str
    fallback_policy: str
    downgraded: bool
    payload: dict[str, object]


class URLOpener(Protocol):
    def __call__(self, http_request: request.Request, timeout: float):
        """Open a prepared HTTP request."""


class LLMClient:
    def __init__(
        self,
        *,
        profiles: ProfileStore,
        invocations: LLMInvocationStore,
        settings: object,
        observability: ObservabilityStore | None = None,
        urlopen: URLOpener | None = None,
    ) -> None:
        self.profiles = profiles
        self.invocations = invocations
        self.settings = settings
        self.observability = observability or NullObservabilityStore()
        self.urlopen = urlopen or request.urlopen

    async def complete(self, completion: LLMCompletionRequest) -> LLMCompletionResponse:
        profile = await self.profiles.get_model_profile(
            workspace_key=completion.workspace_key,
            profile_key=completion.profile_key,
        )
        if profile is None:
            raise LLMProfileNotFoundError(
                f"model profile not found: {completion.workspace_key}/{completion.profile_key}"
            )

        prompt_estimate = estimate_text_tokens(
            "\n".join(message.content for message in completion.messages)
        )
        span = await self.observability.start_span(
            workspace_key=completion.workspace_key,
            trace_id=completion.trace_id,
            parent_span_id=completion.span_id,
            operation_name="llm.complete",
            operation_kind="llm_call",
            safe_attributes={
                "purpose": completion.purpose,
                "profile_key": profile.profile_key,
                "route_kind": profile.route_kind,
                "provider": profile.provider,
                "model": profile.model,
                "requested_thinking_level": profile.thinking_level or "off",
                "thinking_fallback_policy": profile.thinking_fallback_policy or "omit",
                "prompt_token_estimate": prompt_estimate,
                "max_output_tokens": completion.max_output_tokens,
                "temperature": completion.temperature,
            },
            object_refs=[
                {
                    "object_type": "model_profile",
                    "object_id": str(profile.profile_id),
                }
            ],
        )
        traced_completion = replace(
            completion,
            trace_id=span.trace_id,
            span_id=span.span_id,
        )
        try:
            thinking = _resolve_thinking(profile)
            if profile.route_kind == "openai_compatible":
                response = await self._complete_openai_compatible(
                    completion=traced_completion,
                    profile=profile,
                    thinking=thinking,
                    prompt_token_estimate=prompt_estimate,
                )
                await self._finish_span(
                    span_id=span.span_id,
                    status="ok",
                    safe_attributes={
                        "purpose": completion.purpose,
                        "profile_key": profile.profile_key,
                        "status": "ok",
                        "effective_thinking_level": thinking.effective,
                        "thinking_downgraded": thinking.downgraded,
                        "output_token_estimate": response.output_token_estimate,
                        "finish_reason": response.finish_reason,
                    },
                    object_refs=[
                        {
                            "object_type": "llm_invocation",
                            "object_id": str(response.invocation.llm_invocation_id),
                        }
                    ],
                )
                return response
            if profile.route_kind == "openclaw":
                raise LLMRouteUnsupportedError(
                    "openclaw LLM route is not yet stable in the sidecar"
                )
            raise LLMRouteUnsupportedError(f"unsupported LLM route_kind: {profile.route_kind}")
        except LLMThinkingPolicyError as exc:
            thinking = ThinkingDecision(
                requested=profile.thinking_level or "off",
                effective="off",
                fallback_policy=profile.thinking_fallback_policy or "omit",
                downgraded=False,
                payload={},
            )
            await self._record_failure(
                completion=traced_completion,
                profile=profile,
                thinking=thinking,
                prompt_token_estimate=prompt_estimate,
                status="error",
                error_text=str(exc),
            )
            await self._finish_span(
                span_id=span.span_id,
                status="error",
                safe_attributes={
                    "purpose": completion.purpose,
                    "profile_key": profile.profile_key,
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                },
            )
            raise
        except LLMRouteUnsupportedError as exc:
            await self._record_failure(
                completion=traced_completion,
                profile=profile,
                thinking=thinking,
                prompt_token_estimate=prompt_estimate,
                status="unsupported",
                error_text=str(exc),
            )
            await self._finish_span(
                span_id=span.span_id,
                status="denied",
                safe_attributes={
                    "purpose": completion.purpose,
                    "profile_key": profile.profile_key,
                    "status": "unsupported",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                },
            )
            raise
        except Exception as exc:
            await self._finish_span(
                span_id=span.span_id,
                status=_trace_status_for_exception(exc),
                safe_attributes={
                    "purpose": completion.purpose,
                    "profile_key": profile.profile_key,
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error": _safe_error(exc)[:500],
                },
            )
            raise

    async def _complete_openai_compatible(
        self,
        *,
        completion: LLMCompletionRequest,
        profile: ModelProfileRecord,
        thinking: ThinkingDecision,
        prompt_token_estimate: int,
    ) -> LLMCompletionResponse:
        base_url = _resolve_endpoint(profile.endpoint_ref, self.settings)
        api_key = _resolve_api_key(profile, self.settings)
        if not base_url or not api_key:
            error_text = "openai_compatible LLM profile requires endpoint and API key"
            invocation = await self._record_failure(
                completion=completion,
                profile=profile,
                thinking=thinking,
                prompt_token_estimate=prompt_token_estimate,
                status="error",
                error_text=error_text,
            )
            raise LLMClientError(error_text) from None

        endpoint_kind = _resolve_endpoint_kind(profile)
        payload = _build_openai_compatible_payload(
            completion=completion,
            profile=profile,
            endpoint_kind=endpoint_kind,
        )
        payload.update(thinking.payload)
        http_request = request.Request(
            f"{base_url.rstrip('/')}/{_endpoint_path(endpoint_kind)}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self.urlopen(http_request, timeout=profile.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            await self._record_failure(
                completion=completion,
                profile=profile,
                thinking=thinking,
                prompt_token_estimate=prompt_token_estimate,
                status="timeout",
                error_text=_safe_error(exc),
            )
            raise LLMClientError("LLM provider timed out") from exc
        except error.URLError as exc:
            await self._record_failure(
                completion=completion,
                profile=profile,
                thinking=thinking,
                prompt_token_estimate=prompt_token_estimate,
                status="error",
                error_text=_safe_error(exc),
            )
            raise LLMClientError("LLM provider request failed") from exc
        except Exception as exc:
            await self._record_failure(
                completion=completion,
                profile=profile,
                thinking=thinking,
                prompt_token_estimate=prompt_token_estimate,
                status="error",
                error_text=_safe_error(exc),
            )
            raise

        text, finish_reason = _extract_openai_compatible_text(body, endpoint_kind)
        output_estimate = estimate_text_tokens(text)
        invocation = await self.invocations.record_invocation(
            workspace_key=completion.workspace_key,
            purpose=completion.purpose,
            profile_key=profile.profile_key,
            model_profile_id=profile.profile_id,
            route_kind=profile.route_kind,
            provider=profile.provider,
            model=profile.model,
            trace_id=completion.trace_id,
            span_id=completion.span_id,
            requested_thinking_level=thinking.requested,
            effective_thinking_level=thinking.effective,
            thinking_fallback_policy=thinking.fallback_policy,
            thinking_downgraded=thinking.downgraded,
            prompt_token_estimate=prompt_token_estimate,
            output_token_estimate=output_estimate,
            status="ok",
            audit={
                "endpoint_route": endpoint_kind,
                "provider_request_id": body.get("id"),
                "finish_reason": finish_reason,
            },
        )
        return LLMCompletionResponse(
            text=text,
            model=profile.model,
            profile_key=profile.profile_key,
            route_kind=profile.route_kind,
            invocation=invocation,
            prompt_token_estimate=prompt_token_estimate,
            output_token_estimate=output_estimate,
            finish_reason=finish_reason,
        )

    async def _record_failure(
        self,
        *,
        completion: LLMCompletionRequest,
        profile: ModelProfileRecord,
        thinking: ThinkingDecision,
        prompt_token_estimate: int,
        status: str,
        error_text: str,
    ) -> LLMInvocationRecord:
        return await self.invocations.record_invocation(
            workspace_key=completion.workspace_key,
            purpose=completion.purpose,
            profile_key=profile.profile_key,
            model_profile_id=profile.profile_id,
            route_kind=profile.route_kind,
            provider=profile.provider,
            model=profile.model,
            trace_id=completion.trace_id,
            span_id=completion.span_id,
            requested_thinking_level=thinking.requested,
            effective_thinking_level=thinking.effective,
            thinking_fallback_policy=thinking.fallback_policy,
            thinking_downgraded=thinking.downgraded,
            prompt_token_estimate=prompt_token_estimate,
            output_token_estimate=0,
            status=status,  # type: ignore[arg-type]
            error=error_text[:500],
            audit={"endpoint_route": _failure_endpoint_route(profile)},
        )

    async def _finish_span(
        self,
        *,
        span_id: UUID,
        status: TraceStatus,
        safe_attributes: dict[str, object],
        object_refs: list[dict[str, str]] | None = None,
    ) -> None:
        await self.observability.finish_span(
            span_id=span_id,
            status=status,
            safe_attributes=safe_attributes,
            object_refs=object_refs,
        )


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _resolve_endpoint_kind(profile: ModelProfileRecord) -> str:
    endpoint_kind = getattr(profile, "endpoint_kind", None) or "chat_completions"
    if endpoint_kind not in {"chat_completions", "responses"}:
        raise LLMRouteUnsupportedError(f"unsupported LLM endpoint_kind: {endpoint_kind}")
    return endpoint_kind


def _failure_endpoint_route(profile: ModelProfileRecord) -> str:
    if profile.route_kind == "openai_compatible":
        return getattr(profile, "endpoint_kind", None) or "chat_completions"
    return profile.route_kind


def _endpoint_path(endpoint_kind: str) -> str:
    if endpoint_kind == "responses":
        return "responses"
    return "chat/completions"


def _build_openai_compatible_payload(
    *,
    completion: LLMCompletionRequest,
    profile: ModelProfileRecord,
    endpoint_kind: str,
) -> dict[str, object]:
    if endpoint_kind == "responses":
        return {
            "model": profile.model,
            "input": [message.to_json() for message in completion.messages],
            "max_output_tokens": completion.max_output_tokens,
            "temperature": completion.temperature,
        }
    return {
        "model": profile.model,
        "messages": [message.to_json() for message in completion.messages],
        "max_tokens": completion.max_output_tokens,
        "temperature": completion.temperature,
    }


def _extract_openai_compatible_text(
    body: dict[str, object],
    endpoint_kind: str,
) -> tuple[str, str | None]:
    if endpoint_kind == "responses":
        output_text = body.get("output_text")
        if isinstance(output_text, str):
            return output_text, _response_finish_reason(body)
        output = body.get("output")
        if isinstance(output, list):
            fragments: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        fragments.append(part["text"])
            return "".join(fragments), _response_finish_reason(body)
        return "", _response_finish_reason(body)

    choices = body.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices else {}
    if not isinstance(choice, dict):
        return "", None
    message = choice.get("message")
    if not isinstance(message, dict):
        return "", _string_or_none(choice.get("finish_reason"))
    return str(message.get("content", "")), _string_or_none(choice.get("finish_reason"))


def _response_finish_reason(body: dict[str, object]) -> str | None:
    status = _string_or_none(body.get("status"))
    if status:
        return status
    incomplete = body.get("incomplete_details")
    if isinstance(incomplete, dict):
        return _string_or_none(incomplete.get("reason"))
    return None


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _resolve_thinking(profile: ModelProfileRecord) -> ThinkingDecision:
    requested = profile.thinking_level or "off"
    policy = profile.thinking_fallback_policy or "omit"
    if requested in {"off", "omit"}:
        return ThinkingDecision(
            requested=requested,
            effective="off",
            fallback_policy=policy,
            downgraded=False,
            payload={},
        )

    qualification = profile.qualification
    supported_levels = qualification.get("thinking_levels")
    supports_any = qualification.get("supports_thinking") is True
    supports_requested = supports_any or (
        isinstance(supported_levels, list) and requested in supported_levels
    )
    if supports_requested:
        field_name = qualification.get("thinking_request_field")
        if isinstance(field_name, str) and field_name:
            return ThinkingDecision(
                requested=requested,
                effective=requested,
                fallback_policy=policy,
                downgraded=False,
                payload={field_name: requested},
            )
        return ThinkingDecision(
            requested=requested,
            effective=requested,
            fallback_policy=policy,
            downgraded=False,
            payload={},
        )

    if policy == "strict":
        raise LLMThinkingPolicyError(f"model profile does not support thinking_level={requested}")
    if policy == "downgrade":
        return ThinkingDecision(
            requested=requested,
            effective="off",
            fallback_policy=policy,
            downgraded=True,
            payload={},
        )
    return ThinkingDecision(
        requested=requested,
        effective="off",
        fallback_policy=policy,
        downgraded=True,
        payload={},
    )


def _resolve_endpoint(endpoint_ref: str | None, settings: object) -> str | None:
    if endpoint_ref:
        return os.environ.get(endpoint_ref, endpoint_ref)
    configured = getattr(settings, "llm_api_base_url", None)
    if configured:
        return str(configured)
    return os.environ.get("AUTOSKILL_LLM_API_BASE_URL")


def _resolve_api_key(profile: ModelProfileRecord, settings: object) -> str | None:
    key_env = profile.qualification.get("api_key_env")
    if isinstance(key_env, str) and key_env:
        value = os.environ.get(key_env)
        if value:
            return value
    configured = getattr(settings, "llm_api_key", None)
    if configured:
        return str(configured)
    return os.environ.get("AUTOSKILL_LLM_API_KEY")


def _safe_error(exc: BaseException) -> str:
    text = str(exc)
    return text if text else exc.__class__.__name__


def _trace_status_for_exception(exc: BaseException) -> TraceStatus:
    if isinstance(exc, LLMClientError) and "timed out" in str(exc).lower():
        return "timeout"
    return "error"
