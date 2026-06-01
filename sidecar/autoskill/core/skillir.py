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
    tool_templates: list[ToolTemplate] = Field(default_factory=list)
    verification: list[str]
    failure_handling: list[str]
    do_not_use_when: list[str] = Field(default_factory=list)
    never: list[str]
    dependencies: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    environment_contracts: list[EnvironmentContract] = Field(default_factory=list)
    support_artifacts: list[SupportArtifact] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    compiler_version: str = "autoskill-compiler.v1"

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
    def required_runtime_sections(self) -> "SkillIR":
        required_lists = {
            "applicability": self.applicability,
            "steps": self.steps,
            "verification": self.verification,
            "failure_handling": self.failure_handling,
            "never": self.never,
        }
        missing = [name for name, values in required_lists.items() if not values]
        if missing:
            raise ValueError(f"missing required SkillIR sections: {', '.join(missing)}")
        return self

