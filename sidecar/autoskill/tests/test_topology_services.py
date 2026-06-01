import asyncio
from dataclasses import replace
from uuid import uuid4

from autoskill.api.app import TopologyApplyRequest, create_app
from autoskill.core.skillir import EffectSignature
from autoskill.db.activation import ActivationReadiness
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


class MemoryTopologyActivationGate:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed = allowed
        self.calls: list[dict[str, object]] = []

    async def check_activation_readiness(
        self,
        *,
        workspace_key,
        skill_version_id,
        executor_profile_id=None,
    ) -> ActivationReadiness:
        self.calls.append(
            {
                "workspace_key": workspace_key,
                "skill_version_id": skill_version_id,
                "executor_profile_id": executor_profile_id,
            }
        )
        return ActivationReadiness(
            allowed=self.allowed,
            skill_version_id=skill_version_id,
            executor_profile_id=executor_profile_id,
            scanner_status="passed" if self.allowed else "blocked",
            evaluator_status="passed" if self.allowed else "failed",
            latest_evaluation_status="passed" if self.allowed else "failed",
            compatibility_status="compatible" if self.allowed else "blocked",
            blockers=[] if self.allowed else ["not ready"],
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


def test_topology_apply_requires_passed_trials() -> None:
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
            evidence_ids=[str(uuid4())],
        )
    )
    persisted = asyncio.run(
        persist_topology_proposal(
            topology,
            governance,
            workspace_key="dev-01",
            proposal=result,
        )
    )

    blocked = asyncio.run(
        topology.apply_operation(
            workspace_key="dev-01",
            skill_graph_operation_id=persisted.operation.skill_graph_operation_id,
        )
    )
    topology.trials = [replace(trial, status="passed") for trial in topology.trials]
    applied = asyncio.run(
        topology.apply_operation(
            workspace_key="dev-01",
            skill_graph_operation_id=persisted.operation.skill_graph_operation_id,
            applied_by="test",
        )
    )

    assert blocked.allowed is False
    assert "is planned" in blocked.blockers[0]
    assert applied.allowed is True
    assert applied.operation is not None
    assert applied.operation.status == "applied"
    assert applied.operation.trial_summary["applied_by"] == "test"


def test_topology_apply_api_activation_gate_blocks_state_change() -> None:
    topology = NullTopologyStore()
    operation = asyncio.run(
        topology.record_operation(
            workspace_key="dev-01",
            operation_kind="compose",
            status="candidate",
        )
    )
    asyncio.run(
        topology.record_planned_trial(
            workspace_key="dev-01",
            skill_graph_operation_id=operation.skill_graph_operation_id,
            trial_kind="composed_workflow",
            objective="candidate improves the workflow",
            status="passed",
        )
    )
    activation_gate = MemoryTopologyActivationGate(allowed=False)
    app = create_app(topology_store=topology, activation_gate_store=activation_gate)
    route = next(route for route in app.routes if route.path == "/v1/topology/apply")
    skill_version_id = uuid4()

    async def run():
        return await route.endpoint(
            request=TopologyApplyRequest(
                workspace_id="dev-01",
                skill_graph_operation_id=operation.skill_graph_operation_id,
                activation_gate_required=True,
                skill_version_ids=[skill_version_id],
            )
        )

    try:
        asyncio.run(run())
    except Exception as error:
        raised = error
    else:  # pragma: no cover
        raise AssertionError("topology apply should have been blocked")

    assert getattr(raised, "status_code", None) == 409
    assert activation_gate.calls[0]["skill_version_id"] == skill_version_id
    assert topology.operations[0].status == "candidate"
