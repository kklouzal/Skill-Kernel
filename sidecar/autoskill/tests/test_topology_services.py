from uuid import uuid4

from autoskill.core.skillir import EffectSignature
from autoskill.db.governance import NullGovernanceStore
from autoskill.db.topology import NullTopologyStore
from autoskill.services.topology import (
    ComposeTopologyRequest,
    DecomposeTopologyRequest,
    ImproveTopologyRequest,
    TopologySkill,
    persist_topology_proposal,
    propose_composition,
    propose_decomposition,
    propose_improvement,
)


def test_improvement_proposal_preserves_effects_and_plans_rollback() -> None:
    subject = TopologySkill(
        skill_id=uuid4(),
        slug="repair-python-tests",
        effects=EffectSignature(outputs=["patch"], effects=["tests repaired"]),
    )
    proposed = TopologySkill(
        slug="repair-python-tests-v2",
        effects=EffectSignature(
            outputs=["patch", "diagnostic summary"],
            effects=["tests repaired", "flaky import isolated"],
        ),
    )

    result = propose_improvement(
        ImproveTopologyRequest(
            subject=subject,
            proposed=proposed,
            evidence_ids=["evidence-a"],
            improvement_reasons=["repeated flaky import failures"],
        )
    )

    assert result.ok
    assert result.skill_graph_ir is not None
    assert result.skill_graph_ir.operation_kind == "improve"
    assert result.skill_graph_ir.edges[0].edge_kind == "supersedes"
    assert result.transaction.transaction_kind == "topology_improve"
    assert result.transaction.rollback_actions[0]["operation"] == "restore_subject_skill"
    assert result.transaction.writes == [
        "skill_graph_operations",
        "evolution_transactions",
        "transaction_items",
        "planned_topology_trials",
    ]


def test_improvement_blocks_when_proposed_effects_regress_subject() -> None:
    result = propose_improvement(
        ImproveTopologyRequest(
            subject=TopologySkill(
                slug="repair-python-tests",
                effects=EffectSignature(outputs=["patch"], effects=["tests repaired"]),
            ),
            proposed=TopologySkill(
                slug="repair-python-tests-v2",
                effects=EffectSignature(outputs=["diagnostic summary"]),
            ),
            evidence_ids=["evidence-a"],
            improvement_reasons=["faster diagnosis"],
        )
    )

    assert not result.ok
    assert result.skill_graph_ir is None
    assert result.blockers == [
        "proposed skill does not preserve subject effect: patch",
        "proposed skill does not preserve subject effect: tests repaired",
    ]


def test_composition_proposal_builds_skillgraph_and_is_deterministic() -> None:
    inspect = TopologySkill(
        skill_id=uuid4(),
        slug="inspect-failure",
        effects=EffectSignature(outputs=["diagnostic"], effects=["failure classified"]),
    )
    repair = TopologySkill(
        skill_id=uuid4(),
        slug="repair-failure",
        effects=EffectSignature(outputs=["patch"], effects=["failure repaired"]),
    )
    composed = TopologySkill(
        slug="inspect-and-repair",
        effects=EffectSignature(outputs=["diagnostic", "patch"], effects=["failure repaired"]),
    )
    request = ComposeTopologyRequest(
        components=[inspect, repair],
        composed_output=composed,
        evidence_ids=["evidence-a", "evidence-b"],
        required_effects_by_component={"repair-failure": ["diagnostic"]},
    )

    first = propose_composition(request)
    second = propose_composition(request)

    assert first.ok
    assert first.plan_hash == second.plan_hash
    assert first.skill_graph_ir is not None
    assert first.skill_graph_ir.operation_kind == "compose"
    assert [node.operation_role for node in first.skill_graph_ir.nodes] == [
        "component",
        "component",
        "composed_output",
    ]
    assert first.transaction.idempotency_key == f"topology:compose:{first.plan_hash}"
    assert first.transaction.rollback_actions[1]["operation"] == "restore_component_routing"


def test_composition_blocks_unresolved_required_effects() -> None:
    result = propose_composition(
        ComposeTopologyRequest(
            components=[
                TopologySkill(
                    slug="inspect-failure",
                    effects=EffectSignature(outputs=["diagnostic"]),
                ),
                TopologySkill(
                    slug="repair-failure",
                    effects=EffectSignature(outputs=["patch"]),
                ),
            ],
            composed_output=TopologySkill(
                slug="inspect-and-repair",
                effects=EffectSignature(outputs=["patch"]),
            ),
            evidence_ids=["evidence-a"],
            required_effects_by_component={"repair-failure": ["root cause isolated"]},
        )
    )

    assert not result.ok
    assert result.skill_graph_ir is None
    assert result.blockers == [
        "component repair-failure requires unresolved effect: root cause isolated"
    ]


def test_decomposition_requires_successor_effect_coverage() -> None:
    result = propose_decomposition(
        DecomposeTopologyRequest(
            subject=TopologySkill(
                slug="broad-maintenance",
                effects=EffectSignature(outputs=["diagnostic", "patch"]),
            ),
            successors=[
                TopologySkill(
                    slug="diagnose-maintenance",
                    effects=EffectSignature(outputs=["diagnostic"]),
                ),
                TopologySkill(
                    slug="document-maintenance",
                    effects=EffectSignature(outputs=["runbook"]),
                ),
            ],
            evidence_ids=["evidence-a"],
        )
    )

    assert not result.ok
    assert result.skill_graph_ir is None
    assert result.blockers == [
        "successor set does not cover subject effect: patch"
    ]


def test_decomposition_proposal_records_coverage_and_rollback_metadata() -> None:
    subject_id = uuid4()
    result = propose_decomposition(
        DecomposeTopologyRequest(
            subject=TopologySkill(
                skill_id=subject_id,
                slug="broad-maintenance",
                effects=EffectSignature(outputs=["diagnostic", "patch"]),
            ),
            successors=[
                TopologySkill(
                    slug="diagnose-maintenance",
                    effects=EffectSignature(outputs=["diagnostic"]),
                ),
                TopologySkill(
                    slug="repair-maintenance",
                    effects=EffectSignature(outputs=["patch"]),
                ),
            ],
            evidence_ids=["evidence-a", "evidence-b"],
        )
    )

    assert result.ok
    assert result.skill_graph_ir is not None
    assert result.skill_graph_ir.effect_coverage == {
        "diagnostic": ["diagnose-maintenance"],
        "patch": ["repair-maintenance"],
    }
    assert result.transaction.rollback_actions == [
        {
            "operation": "restore_subject_skill",
            "subject_slug": "broad-maintenance",
            "subject_skill_id": str(subject_id),
            "remove_successor_slugs": ["diagnose-maintenance", "repair-maintenance"],
        }
    ]


def test_topology_proposal_persistence_records_operation_trials_and_transaction() -> None:
    evidence_id = uuid4()
    topology = NullTopologyStore()
    governance = NullGovernanceStore()
    result = propose_composition(
        ComposeTopologyRequest(
            components=[
                TopologySkill(
                    skill_id=uuid4(),
                    slug="inspect-failure",
                    effects=EffectSignature(outputs=["diagnostic"]),
                ),
                TopologySkill(
                    skill_id=uuid4(),
                    slug="repair-failure",
                    effects=EffectSignature(outputs=["patch"]),
                ),
            ],
            composed_output=TopologySkill(
                slug="inspect-and-repair",
                effects=EffectSignature(outputs=["diagnostic", "patch"]),
            ),
            evidence_ids=[str(evidence_id)],
        )
    )

    import asyncio

    persisted = asyncio.run(
        persist_topology_proposal(
            topology,
            governance,
            workspace_key="dev-01",
            proposal=result,
        )
    )

    assert persisted.operation.operation_kind == "compose"
    assert persisted.operation.status == "candidate"
    assert persisted.operation.evidence_ids == [evidence_id]
    assert persisted.operation.evolution_transaction_id is not None
    assert [trial.trial_kind for trial in persisted.trials] == [
        "component_baseline",
        "composed_workflow",
        "shadowing",
    ]
