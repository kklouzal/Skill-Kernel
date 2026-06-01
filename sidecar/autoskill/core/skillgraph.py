from __future__ import annotations

from typing import Literal
from uuid import UUID

from autoskill.core.skillir import EffectSignature
from pydantic import BaseModel, Field, model_validator


class SkillGraphNode(BaseModel):
    skill_id: UUID | None = None
    slug: str
    operation_role: Literal["subject", "component", "successor", "composed_output"]
    effects: EffectSignature = Field(default_factory=EffectSignature)


class SkillGraphEdge(BaseModel):
    from_slug: str
    to_slug: str
    edge_kind: Literal[
        "component_of",
        "composes_with",
        "composed_by",
        "decomposes_to",
        "specializes",
        "generalizes",
        "supersedes",
        "shadows",
        "requires",
        "conflicts_with",
    ]
    required_effects: list[str] = Field(default_factory=list)
    produced_effects: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)


class SkillGraphIR(BaseModel):
    schema_: Literal["skillgraph.v1"] = Field(default="skillgraph.v1", alias="schema")
    operation_kind: Literal[
        "create",
        "improve",
        "compose",
        "decompose",
        "merge",
        "archive",
        "promote",
    ]
    nodes: list[SkillGraphNode]
    edges: list[SkillGraphEdge] = Field(default_factory=list)
    effect_coverage: dict[str, list[str]] = Field(default_factory=dict)
    rollback_blockers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph_effects(self) -> SkillGraphIR:
        slugs = {node.slug for node in self.nodes}
        missing = [
            f"{edge.from_slug}->{edge.to_slug}"
            for edge in self.edges
            if edge.from_slug not in slugs or edge.to_slug not in slugs
        ]
        if missing:
            raise ValueError(f"skill graph edges reference missing nodes: {', '.join(missing)}")
        if self.operation_kind == "compose":
            unresolved = [gap for edge in self.edges for gap in edge.unresolved_gaps]
            if unresolved:
                raise ValueError(
                    "compose graph has unresolved effect gaps: " + ", ".join(unresolved)
                )
        if self.operation_kind == "decompose" and not self.effect_coverage:
            raise ValueError("decompose graph requires effect coverage mapping")
        return self
