from uuid import uuid4

import pytest
from autoskill.core.skillgraph import SkillGraphEdge, SkillGraphIR, SkillGraphNode
from autoskill.core.skillir import EffectSignature
from pydantic import ValidationError


def test_skillgraph_compose_requires_resolved_effect_edges() -> None:
    first = SkillGraphNode(
        skill_id=uuid4(),
        slug="inspect",
        operation_role="component",
        effects=EffectSignature(outputs=["diagnostic"], effects=["project inspected"]),
    )
    second = SkillGraphNode(
        skill_id=uuid4(),
        slug="fix",
        operation_role="component",
        effects=EffectSignature(outputs=["patch"], effects=["issue remediated"]),
    )

    graph = SkillGraphIR(
        operation_kind="compose",
        nodes=[first, second],
        edges=[
            SkillGraphEdge(
                from_slug="inspect",
                to_slug="fix",
                edge_kind="requires",
                produced_effects=["diagnostic"],
                required_effects=["diagnostic"],
            )
        ],
    )

    assert graph.schema_ == "skillgraph.v1"


def test_skillgraph_decompose_requires_effect_coverage() -> None:
    with pytest.raises(ValidationError):
        SkillGraphIR(
            operation_kind="decompose",
            nodes=[
                SkillGraphNode(
                    slug="broad",
                    operation_role="subject",
                    effects=EffectSignature(effects=["broad workflow covered"]),
                )
            ],
        )
