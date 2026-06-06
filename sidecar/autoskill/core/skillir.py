from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class ToolTemplate(BaseModel):
    name: str
    purpose: str
    template: str
    required_capabilities: list[str] = Field(default_factory=list)


class EnvironmentContract(BaseModel):
    kind: str
    name: str
    expectation: str
    probe: str | None = None


class SupportArtifact(BaseModel):
    path: str
    kind: Literal["script", "template", "fixture", "manifest", "asset"]
    sha256: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    load_policy: Literal[
        "never_loaded",
        "agent_may_read",
        "broker_excerpt_only",
        "script_only",
        "probe_only",
        "operator_only",
    ] = "never_loaded"


class RuntimeGuardTemplate(BaseModel):
    template_id: Literal[
        "preflight_check",
        "verify_only_check",
        "capability_warning",
        "sibling_disambiguation_hint",
        "drift_block",
    ]
    mode: Literal[
        "preflight",
        "verify_only",
        "warn",
        "context_hint",
        "block",
        "drift_check",
        "capability_check",
        "shadowing_hint",
    ]
    condition_summary: str
    operator_message: str
    required_capabilities: list[str] = Field(default_factory=list)

    @field_validator("condition_summary", "operator_message")
    @classmethod
    def validate_compact_text(cls, value: str) -> str:
        text = value.strip()
        if not text or "\n" in text or len(text) > 180:
            raise ValueError("runtime guard text must be one compact line")
        return text


class EffectSignature(BaseModel):
    outputs: list[str] = Field(default_factory=list)
    effects: list[str] = Field(default_factory=list)
    state_delta: list[str] = Field(default_factory=list)
    side_effects: list[str] = Field(default_factory=list)
    termination: list[str] = Field(default_factory=list)
    idempotency: Literal["idempotent", "retry_safe", "not_retry_safe", "unknown"] = "unknown"
    unsafe_when: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)


class SkillIR(BaseModel):
    schema_: Literal["skillir.v1"] = Field(default="skillir.v1", alias="schema")
    skill_id: UUID = Field(default_factory=uuid4)
    slug: str
    name: str
    description: str
    version: int = 1
    applicability: list[str]
    inputs: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str]
    outputs: list[str] = Field(default_factory=list)
    effects: list[str] = Field(default_factory=list)
    state_delta: list[str] = Field(default_factory=list)
    side_effects: list[str] = Field(default_factory=list)
    termination: list[str] = Field(default_factory=list)
    idempotency: Literal["idempotent", "retry_safe", "not_retry_safe", "unknown"] = "unknown"
    unsafe_when: list[str] = Field(default_factory=list)
    tool_templates: list[ToolTemplate] = Field(default_factory=list)
    verification: list[str]
    failure_handling: list[str]
    failure_modes: list[str] = Field(default_factory=list)
    do_not_use_when: list[str] = Field(default_factory=list)
    never: list[str]
    dependencies: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    environment_contracts: list[EnvironmentContract] = Field(default_factory=list)
    runtime_guards: list[RuntimeGuardTemplate] = Field(default_factory=list)
    support_artifacts: list[SupportArtifact] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    compiler_version: str = "autoskill-compiler.v1"
    granularity: Literal["atomic", "functional", "workflow", "planning", "meta", "external"] = (
        "functional"
    )
    scope: Literal[
        "workspace_local",
        "project_local",
        "domain",
        "global_general",
        "external_readonly",
        "archived",
    ] = "workspace_local"
    topology_role: Literal[
        "standalone",
        "component",
        "composition",
        "decomposition_successor",
        "superseded_parent",
        "sibling",
        "prerequisite",
        "alternative",
    ] = "standalone"
    component_policy: Literal[
        "retain_components",
        "prefer_composed",
        "prefer_components",
        "broker_decides",
    ] = "broker_decides"
    runtime_visibility_policy: Literal[
        "metadata_only",
        "broker_hint_only",
        "full_skill_allowed",
        "hidden_by_default",
        "no_runtime_visibility",
    ] = "full_skill_allowed"

    @property
    def effect_signature(self) -> EffectSignature:
        return EffectSignature(
            outputs=self.outputs,
            effects=self.effects,
            state_delta=self.state_delta,
            side_effects=self.side_effects,
            termination=self.termination,
            idempotency=self.idempotency,
            unsafe_when=self.unsafe_when,
            failure_modes=self.failure_modes,
        )

    @field_validator("slug", "name")
    @classmethod
    def validate_skill_name(cls, value: str) -> str:
        if not value:
            raise ValueError("skill name cannot be empty")
        if not all(ch.islower() or ch.isdigit() or ch == "-" for ch in value):
            raise ValueError("skill name must contain only lowercase letters, digits, and hyphens")
        if value.startswith("-") or value.endswith("-") or "--" in value:
            raise ValueError("skill name must be a stable slug")
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        if "\n" in value or len(value.strip()) > 180:
            raise ValueError("description must be one compact line")
        return value.strip()

    @model_validator(mode="after")
    def required_runtime_sections(self) -> SkillIR:
        required_lists = {
            "applicability": self.applicability,
            "steps": self.steps,
            "outputs": self.outputs,
            "effects": self.effects,
            "verification": self.verification,
            "failure_handling": self.failure_handling,
            "never": self.never,
        }
        missing = [name for name, values in required_lists.items() if not values]
        if missing:
            raise ValueError(f"missing required SkillIR sections: {', '.join(missing)}")
        return self
