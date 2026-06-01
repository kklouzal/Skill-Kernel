from __future__ import annotations

from pydantic import BaseModel, Field


class ContextHintRequest(BaseModel):
    workspace_id: str
    agent_id: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    user_intent: str | None = None
    max_tokens: int = 600


class ContextHintResponse(BaseModel):
    decision: str = "no_skill"
    hint: str = ""
    skill_ids: list[str] = Field(default_factory=list)
    broker_policy_version: str = "bootstrap.v1"
    cache_status: str = "bootstrap-empty"


def bootstrap_context_hint(_: ContextHintRequest) -> ContextHintResponse:
    return ContextHintResponse()

