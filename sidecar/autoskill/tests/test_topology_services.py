import asyncio
from dataclasses import replace
from uuid import uuid4

from autoskill.api.app import (
    TopologyApplyRequest,
    TopologyUsageProposalRequest,
    create_app,
)
from autoskill.core.skillir import EffectSignature
from autoskill.db.activation import ActivationReadiness
from autoskill.db.autonomy import NullAutonomyControlStore
from autoskill.db.governance import NullGovernanceStore
from autoskill.db.topology import NullTopologyStore
from autoskill.db.usage import UsageTopologyRecommendation
from autoskill.services.topology import (
    ComposeTopologyRequest,
    CreateTopologyRequest,
    DecomposeTopologyRequest,
    ImproveTopologyRequest,
    TopologySkill,
    persist_topology_proposal,
    propose_composition,
    propose_creation,
    propose_decomposition,
    propose_improvement,
)


class MemoryTopologyUsageStore:
    def __init__(self, recommendations: list[UsageTopologyRecommendation]) -> None:
        self.recommendations = recommendations
        self.calls: list[dict[str, object]] = []

    async def recommend_topology_operations(
        self,
        *,
        workspace_key: str,
        limit: int = 25,
        min_support: int = 3,
        min_success_count: int = 1,
        max_failure_ratio: float = 0.25,
        min_sequence_count: int = 1,
    ) -> list[UsageTopologyRecommendation]:
        self.calls.append(
            {
                "workspace_key": workspace_key,
                "limit": limit,
                "min_support": min_support,
                "min_success_count": min_success_count,
                "max_failure_ratio": max_failure_ratio,
                "min_sequence_count": min_sequence_count,
            }
        )
        return self.recommendations[:limit]


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
        require_context_compile_proof=False,
        context_compile_run_id=None,
        context_artifact_id=None,
        compiled_text_hash=None,
        context_output_manifest_hash=None,
        allowed_autonomy_actions=None,
    ) -> ActivationReadiness:
        self.calls.append(
            {
                "workspace_key": workspace_key,
                "skill_version_id": skill_version_id,
                "executor_profile_id": executor_profile_id,
                "require_context_compile_proof": require_context_compile_proof,
                "allowed_autonomy_actions": allowed_autonomy_actions,
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
            context_compile_run_id=context_compile_run_id,
            context_artifact_id=context_artifact_id,
            context_compile_status="passed" if self.allowed else "failed",
            context_safety_status="passed" if self.allowed else "blocked",
            context_equivalence_status="passed" if self.allowed else "failed",
            context_budget_status="passed" if self.allowed else "over_budget",
            blockers=[] if self.allowed else ["not ready"],
            autonomy_action="auto_accept" if allowed_autonomy_actions else None,
            autonomy_action_required=bool(allowed_autonomy_actions),
        )


class RecordingGovernanceStore(NullGovernanceStore):
    def __init__(self) -> None:
        self.status_updates: list[dict[str, object]] = []

    async def update_transaction_status(self, **kwargs):
        self.status_updates.append(kwargs)
        return await super().update_transaction_status(**kwargs)


def test_create_topology_proposal_is_first_class_operation() -> None:
    proposal = propose_creation(
        CreateTopologyRequest(
            proposed=TopologySkill(
                slug="pytest-import-repair",
                skill_id=uuid4(),
                effects=EffectSignature(
                    outputs=["repair-python-import-error"],
                    effects=["inspect-traceback"],
                ),
            ),
            evidence_ids=[str(uuid4())],
            creation_reasons=["recurring missing workflow evidence"],
        )
    )

    assert proposal.status == "candidate"
    assert proposal.operation_kind == "create"
    assert proposal.skill_graph_ir is not None
    assert proposal.skill_graph_ir.operation_kind == "create"
    assert proposal.skill_graph_ir.nodes[0].operation_role == "successor"
    assert {trial.kind for trial in proposal.trial_plan} == {
        "target_creation",
        "no_skill_control",
        "nearest_active_collision",
        "broker_replay",
        "broker_canary",
        "rollback_readiness",
    }
    broker_replay = next(trial for trial in proposal.trial_plan if trial.kind == "broker_replay")
    assert broker_replay.expected["operation_kind"] == "create"
    assert broker_replay.expected["block_on_shadowing"] is True
    assert proposal.transaction.transaction_kind == "topology_create"
    assert proposal.transaction.rollback_actions[0]["operation"] == "remove_created_skill"


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
    assert {trial.kind for trial in result.trial_plan} == {
        "target_improvement",
        "regression",
        "broker_replay",
        "broker_canary",
        "rollback_readiness",
    }
    broker_replay = next(trial for trial in result.trial_plan if trial.kind == "broker_replay")
    assert broker_replay.expected["operation_kind"] == "improve"
    assert broker_replay.expected["block_on_shadowing"] is True
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


def test_composition_required_edges_point_to_actual_effect_producers() -> None:
    collect = TopologySkill(
        skill_id=uuid4(),
        slug="collect-logs",
        effects=EffectSignature(outputs=["logs"]),
    )
    diagnose = TopologySkill(
        skill_id=uuid4(),
        slug="diagnose-failure",
        effects=EffectSignature(outputs=["diagnostic"], effects=["logs interpreted"]),
    )
    repair = TopologySkill(
        skill_id=uuid4(),
        slug="repair-failure",
        effects=EffectSignature(outputs=["patch"]),
    )
    result = propose_composition(
        ComposeTopologyRequest(
            components=[collect, diagnose, repair],
            composed_output=TopologySkill(
                slug="diagnose-and-repair",
                effects=EffectSignature(outputs=["diagnostic", "patch"]),
            ),
            evidence_ids=["evidence-a"],
            required_effects_by_component={
                "diagnose-failure": ["logs"],
                "repair-failure": ["diagnostic"],
            },
        )
    )

    assert result.ok
    assert result.skill_graph_ir is not None
    required_edges = [
        edge
        for edge in result.skill_graph_ir.edges
        if edge.edge_kind == "requires"
    ]
    assert [
        (edge.from_slug, edge.to_slug, edge.required_effects)
        for edge in required_edges
    ] == [
        ("collect-logs", "diagnose-failure", ["logs"]),
        ("diagnose-failure", "repair-failure", ["diagnostic"]),
    ]


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
    governance = RecordingGovernanceStore()
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
        "broker_replay",
        "broker_canary",
    ]
    assert len(governance.status_updates) == 1
    metrics = governance.status_updates[0]["metrics"]
    assert metrics["topology_operation_kind"] == "compose"
    assert metrics["topology_status"] == "candidate"
    assert metrics["plan_hash"] == result.plan_hash
    assert metrics["evidence_count"] == 1
    assert metrics["planned_trials"] == 5
    assert metrics["trial_kinds"] == [
        "component_baseline",
        "composed_workflow",
        "shadowing",
        "broker_replay",
        "broker_canary",
    ]
    assert metrics["graph_node_count"] == 3
    assert metrics["graph_edge_count"] == 2
    assert metrics["graph_node_roles"] == {
        "component": 2,
        "composed_output": 1,
    }
    assert metrics["graph_edge_kinds"] == {"component_of": 2}
    assert metrics["effect_coverage_count"] == 2
    assert metrics["rollback_actions"] == 2
    assert metrics["rollback_actions_planned"] is True
    assert metrics["requires_trial_before_apply"] is True
    assert metrics["writes"] == [
        "skill_graph_operations",
        "evolution_transactions",
        "transaction_items",
        "planned_topology_trials",
    ]
    trace = metrics["data_to_skill_trace"]
    assert trace["schema_version"] == "skillkernel.data-to-skill-trace.topology.v1"
    assert trace["operation_kind"] == "compose"
    assert trace["status"] == "candidate"
    assert trace["failure_exit"] is None
    assert trace["terminal_stage"] == "planned_trials"
    assert trace["content_policy"]["raw_available"] is False
    stages = {stage["name"]: stage for stage in trace["stages"]}
    assert stages["evidence_packet"]["input_refs"] == [
        {"object_type": "evidence_item", "object_id": str(evidence_id)}
    ]
    assert stages["operation_plan"]["output_refs"] == [
        {
            "object_type": "skill_graph_operation",
            "object_id": str(persisted.operation.skill_graph_operation_id),
        }
    ]
    assert stages["evaluation_result"]["output_refs"] == [
        {
            "object_type": "planned_topology_trial",
            "object_id": str(trial.planned_topology_trial_id),
        }
        for trial in persisted.trials
    ]
    assert "inspect-and-repair" not in str(trace)


def test_topology_proposal_persistence_records_calibration_observation() -> None:
    topology = NullTopologyStore()
    governance = RecordingGovernanceStore()
    autonomy = NullAutonomyControlStore()
    result = propose_creation(
        CreateTopologyRequest(
            proposed=TopologySkill(
                slug="pytest-import-repair",
                effects=EffectSignature(outputs=["repair-python-import-error"]),
            ),
            evidence_ids=[str(uuid4())],
            creation_reasons=["recurring missing workflow evidence"],
        )
    )

    persisted = asyncio.run(
        persist_topology_proposal(
            topology,
            governance,
            workspace_key="dev-01",
            proposal=result,
            autonomy=autonomy,
        )
    )

    assert len(autonomy.calibration_observations) == 1
    observation = autonomy.calibration_observations[0]
    assert observation.calibration_family == "topology_operation_choice"
    assert observation.selected_action == "propose_create"
    assert observation.action_risk_tier == "T1_internal_record"
    assert observation.outcome_status == "pending"
    assert observation.predicted_confidence > 0.7
    assert autonomy.reliability_metrics[-1].calibration_family == (
        "topology_operation_choice"
    )
    assert autonomy.reliability_metrics[-1].sample_count == 1
    assert persisted.operation.status == "candidate"


def test_topology_blocked_proposal_records_reject_calibration_observation() -> None:
    topology = NullTopologyStore()
    governance = RecordingGovernanceStore()
    autonomy = NullAutonomyControlStore()
    result = propose_creation(
        CreateTopologyRequest(
            proposed=TopologySkill(
                slug="empty-effect-skill",
                effects=EffectSignature(),
            ),
            evidence_ids=[],
            creation_reasons=[],
        )
    )

    persisted = asyncio.run(
        persist_topology_proposal(
            topology,
            governance,
            workspace_key="dev-01",
            proposal=result,
            autonomy=autonomy,
        )
    )

    assert persisted.operation.status == "blocked"
    assert len(autonomy.calibration_observations) == 1
    observation = autonomy.calibration_observations[0]
    assert observation.calibration_family == "topology_operation_choice"
    assert observation.selected_action == "auto_reject"
    assert observation.predicted_confidence > 0.8
    assert autonomy.reliability_metrics[-1].abstention_rate == 1.0


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
                skill_id=uuid4(),
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
    orchestration = applied.operation.trial_summary["downstream_orchestration"]
    assert orchestration["status"] == "planned"
    assert orchestration["action_count"] == len(applied.downstream_actions)
    assert {action["operation"] for action in applied.downstream_actions or []} == {
        "activate_composed_skill",
        "materialize_skill_graph_edges",
        "record_topology_operation_applied",
        "route_components_to_composed_skill",
    }
    assert all(
        action["status"] in {"planned", "ready"}
        for action in applied.downstream_actions or []
    )


def test_topology_downstream_apply_records_lifecycle_and_edge_execution() -> None:
    topology = NullTopologyStore()
    governance = NullGovernanceStore()
    component_a = uuid4()
    component_b = uuid4()
    composed_id = uuid4()
    result = propose_composition(
        ComposeTopologyRequest(
            components=[
                TopologySkill(
                    skill_id=component_a,
                    slug="inspect-failure",
                    effects=EffectSignature(outputs=["diagnostic"]),
                ),
                TopologySkill(
                    skill_id=component_b,
                    slug="repair-failure",
                    effects=EffectSignature(outputs=["patch"]),
                ),
            ],
            composed_output=TopologySkill(
                skill_id=composed_id,
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
    topology.trials = [replace(trial, status="passed") for trial in topology.trials]
    applied = asyncio.run(
        topology.apply_operation(
            workspace_key="dev-01",
            skill_graph_operation_id=persisted.operation.skill_graph_operation_id,
        )
    )

    downstream = asyncio.run(
        topology.apply_downstream_actions(
            workspace_key="dev-01",
            skill_graph_operation_id=persisted.operation.skill_graph_operation_id,
            applied_by="test-worker",
        )
    )

    assert applied.allowed
    assert downstream.allowed
    assert downstream.lifecycle_updates == 1
    assert downstream.edges_materialized == 2
    assert downstream.operation is not None
    orchestration = downstream.operation.trial_summary["downstream_orchestration"]
    assert orchestration["status"] == "applied"
    assert orchestration["applied_by"] == "test-worker"
    assert orchestration["lifecycle_updates"] == 1
    assert orchestration["edges_materialized"] == 2
    assert {action["operation"] for action in orchestration["actions"]} == {
        "activate_composed_skill",
        "materialize_skill_graph_edges",
        "record_topology_operation_applied",
        "route_components_to_composed_skill",
    }


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


def test_topology_usage_recommendations_can_persist_compose_proposals() -> None:
    first_skill = uuid4()
    second_skill = uuid4()
    evidence_id = uuid4()
    usage = MemoryTopologyUsageStore(
        [
            UsageTopologyRecommendation(
                skill_usage_cluster_id=uuid4(),
                cluster_key=f"compose:{first_skill}:{second_skill}",
                skill_ids=[first_skill, second_skill],
                evidence_ids=[evidence_id],
                recommended_operation="compose",
                support_count=5,
                success_count=4,
                failure_count=0,
                sequence_count=5,
                operation_score=18.0,
                blockers=[],
                metadata={
                    "source": "usage.aggregate",
                    "topology_signal": "recurring_co_usage",
                },
            )
        ]
    )
    topology = NullTopologyStore()
    app = create_app(
        usage_store=usage,
        topology_store=topology,
        governance_store=NullGovernanceStore(),
    )
    route = next(
        route for route in app.routes if route.path == "/v1/topology/propose-from-usage"
    )

    async def run():
        return await route.endpoint(
            request=TopologyUsageProposalRequest(
                workspace_id="dev-01",
                limit=3,
                min_support=4,
                persist=True,
            )
        )

    response = asyncio.run(run())

    assert response.recommendations_scanned == 1
    assert response.skipped == []
    assert len(response.proposals) == 1
    proposal = response.proposals[0]["proposal"]
    assert proposal["operation_kind"] == "compose"
    assert proposal["status"] == "candidate"
    assert proposal["evidence_ids"] == [str(evidence_id)]
    assert response.proposals[0]["persistence"]["operation"]["operation_kind"] == "compose"
    assert topology.operations[0].evidence_ids == [evidence_id]
    assert usage.calls == [
        {
            "workspace_key": "dev-01",
            "limit": 3,
            "min_support": 4,
            "min_success_count": 1,
            "max_failure_ratio": 0.25,
            "min_sequence_count": 1,
        }
    ]


def test_topology_usage_recommendations_can_persist_improve_and_decompose_proposals() -> None:
    skill_id = uuid4()
    improve_evidence = uuid4()
    decompose_evidence = uuid4()
    hydrated_metadata = {
        "skill_snapshots": [
            {
                "skill_id": str(skill_id),
                "slug": "real-runtime-skill",
                "description": "Real runtime skill description",
                "effects": {
                    "outputs": ["real-output"],
                    "effects": ["real-effect"],
                    "state_delta": ["real-state-delta"],
                    "termination": ["real-termination"],
                    "failure_modes": ["real-failure-mode"],
                    "idempotency": "retry_safe",
                },
                "contracts": {
                    "environment_contract_count": 1,
                    "runtime_guard_count": 1,
                    "support_artifact_count": 1,
                },
                "body_index": {
                    "document_kinds": ["runtime", "skillir"],
                    "document_count": 2,
                },
            }
        ]
    }
    usage = MemoryTopologyUsageStore(
        [
            UsageTopologyRecommendation(
                skill_usage_cluster_id=uuid4(),
                cluster_key=f"improve:{skill_id}",
                skill_ids=[skill_id],
                evidence_ids=[improve_evidence],
                recommended_operation="improve",
                support_count=5,
                success_count=0,
                failure_count=3,
                sequence_count=0,
                operation_score=11.0,
                blockers=[],
                metadata={
                    "source": "usage.aggregate",
                    "topology_signal": "repeated_negative_outcome",
                    "context_signal_count": 0,
                    **hydrated_metadata,
                },
            ),
            UsageTopologyRecommendation(
                skill_usage_cluster_id=uuid4(),
                cluster_key=f"decompose:{skill_id}",
                skill_ids=[skill_id],
                evidence_ids=[decompose_evidence],
                recommended_operation="decompose",
                support_count=6,
                success_count=0,
                failure_count=0,
                sequence_count=0,
                operation_score=12.0,
                blockers=[],
                metadata={
                    "source": "usage.aggregate",
                    "topology_signal": "context_waste_or_false_positive",
                    "context_signal_count": 4,
                    "token_waste": 900,
                    "avg_context_value_per_token": -0.025,
                    "suggested_context_actions": [
                        "broker_abstain",
                        "tighten_description",
                    ],
                    **hydrated_metadata,
                },
            ),
        ]
    )
    topology = NullTopologyStore()
    app = create_app(
        usage_store=usage,
        topology_store=topology,
        governance_store=NullGovernanceStore(),
    )
    route = next(
        route for route in app.routes if route.path == "/v1/topology/propose-from-usage"
    )

    async def run():
        return await route.endpoint(
            request=TopologyUsageProposalRequest(workspace_id="dev-01", persist=True)
        )

    response = asyncio.run(run())

    assert response.recommendations_scanned == 2
    assert response.skipped == []
    assert [item["proposal"]["operation_kind"] for item in response.proposals] == [
        "improve",
        "decompose",
    ]
    improve = response.proposals[0]["proposal"]
    decompose = response.proposals[1]["proposal"]
    assert improve["status"] == "candidate"
    assert improve["evidence_ids"] == [str(improve_evidence)]
    assert improve["skill_graph_ir"]["nodes"][0]["slug"] == "real-runtime-skill"
    assert improve["skill_graph_ir"]["nodes"][0]["effects"]["outputs"] == [
        "real-output"
    ]
    assert improve["skill_graph_ir"]["nodes"][1]["slug"].startswith(
        "real-runtime-skill-improved-"
    )
    assert "failure_count:3" in improve["trial_plan"][0]["expected"]["reasons"]
    assert (
        "current_skillir_description_present"
        in improve["trial_plan"][0]["expected"]["reasons"]
    )
    assert "environment_contract_count:1" in improve["trial_plan"][0]["expected"][
        "reasons"
    ]
    assert "body_index_kind:skillir" in improve["trial_plan"][0]["expected"][
        "reasons"
    ]
    assert "real-failure-mode" in improve["skill_graph_ir"]["nodes"][1]["effects"][
        "failure_modes"
    ]
    assert improve["skill_graph_ir"]["nodes"][1]["effects"][
        "idempotency"
    ] == "retry_safe"
    assert decompose["status"] == "candidate"
    assert decompose["evidence_ids"] == [str(decompose_evidence)]
    assert decompose["skill_graph_ir"]["operation_kind"] == "decompose"
    assert len(decompose["skill_graph_ir"]["nodes"]) == 3
    assert decompose["skill_graph_ir"]["effect_coverage"]["real-state-delta"]
    assert "real-state-delta" in decompose["trial_plan"][2]["expected"][
        "covered_effects"
    ]
    assert "token_waste:900" in decompose["trial_plan"][3]["expected"]["reasons"]
    assert "avg_context_value_per_token:-0.025" in decompose["trial_plan"][3][
        "expected"
    ]["reasons"]
    assert response.proposals[1]["recommendation"]["metadata"]["token_waste"] == 900
    assert (
        response.proposals[1]["recommendation"]["metadata"][
            "avg_context_value_per_token"
        ]
        == -0.025
    )
    assert "broker_abstain" in response.proposals[1]["recommendation"]["metadata"][
        "suggested_context_actions"
    ]
    assert [operation.operation_kind for operation in topology.operations] == [
        "improve",
        "decompose",
    ]


def test_topology_usage_recommendations_skip_blocked_or_unsupported_signals() -> None:
    skill_id = uuid4()
    usage = MemoryTopologyUsageStore(
        [
            UsageTopologyRecommendation(
                skill_usage_cluster_id=uuid4(),
                cluster_key=f"compose:{skill_id}",
                skill_ids=[skill_id],
                evidence_ids=[],
                recommended_operation="compose",
                support_count=1,
                success_count=0,
                failure_count=1,
                sequence_count=0,
                operation_score=-1.0,
                blockers=["usage cluster support below threshold"],
                metadata={"source": "usage.aggregate"},
            ),
            UsageTopologyRecommendation(
                skill_usage_cluster_id=uuid4(),
                cluster_key=f"create:{skill_id}",
                skill_ids=[skill_id],
                evidence_ids=[],
                recommended_operation="create",
                support_count=5,
                success_count=5,
                failure_count=0,
                sequence_count=5,
                operation_score=20.0,
                blockers=[],
                metadata={"source": "usage.aggregate"},
            ),
        ]
    )
    app = create_app(usage_store=usage, topology_store=NullTopologyStore())
    route = next(
        route for route in app.routes if route.path == "/v1/topology/propose-from-usage"
    )

    async def run():
        return await route.endpoint(
            request=TopologyUsageProposalRequest(workspace_id="dev-01", persist=False)
        )

    response = asyncio.run(run())

    assert response.recommendations_scanned == 2
    assert response.proposals == []
    assert [item["skipped_reason"] for item in response.skipped] == [
        "recommendation blocked by usage thresholds",
        (
            "usage recommendation lacks enough structured data "
            "for a propose-only topology operation"
        ),
    ]


def test_topology_compose_apply_requires_broker_trials() -> None:
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

    result = asyncio.run(
        topology.apply_operation(
            workspace_key="dev-01",
            skill_graph_operation_id=operation.skill_graph_operation_id,
        )
    )

    assert result.allowed is False
    assert any("requires broker_replay trial" in blocker for blocker in result.blockers)
    assert any("requires broker_canary trial" in blocker for blocker in result.blockers)


def test_topology_decompose_apply_blocks_bad_broker_scores() -> None:
    topology = NullTopologyStore()
    operation = asyncio.run(
        topology.record_operation(
            workspace_key="dev-01",
            operation_kind="decompose",
            status="candidate",
        )
    )

    async def add_trials():
        for trial_kind in ("original_baseline", "successor_routing", "coverage_regression"):
            await topology.record_planned_trial(
                workspace_key="dev-01",
                skill_graph_operation_id=operation.skill_graph_operation_id,
                trial_kind=trial_kind,
                objective=trial_kind,
                status="passed",
            )
        await topology.record_planned_trial(
            workspace_key="dev-01",
            skill_graph_operation_id=operation.skill_graph_operation_id,
            trial_kind="broker_replay",
            objective="broker replay",
            status="passed",
            result={"mismatched": 1, "degradation_count": 1},
        )
        await topology.record_planned_trial(
            workspace_key="dev-01",
            skill_graph_operation_id=operation.skill_graph_operation_id,
            trial_kind="broker_canary",
            objective="broker canary",
            status="passed",
            result={"metrics": {"harmful_rate": 0.0, "shadowed_rate": 0.25}},
        )

    asyncio.run(add_trials())

    result = asyncio.run(
        topology.apply_operation(
            workspace_key="dev-01",
            skill_graph_operation_id=operation.skill_graph_operation_id,
        )
    )

    assert result.allowed is False
    assert any("has 1 mismatches" in blocker for blocker in result.blockers)
    assert any("has 1 degradations" in blocker for blocker in result.blockers)
    assert any("shadowed_rate=0.25" in blocker for blocker in result.blockers)


def test_topology_broker_trial_scoring_persists_passed_results() -> None:
    topology = NullTopologyStore()
    operation = asyncio.run(
        topology.record_operation(
            workspace_key="dev-01",
            operation_kind="compose",
            status="candidate",
        )
    )

    async def add_trials():
        await topology.record_planned_trial(
            workspace_key="dev-01",
            skill_graph_operation_id=operation.skill_graph_operation_id,
            trial_kind="broker_replay",
            objective="broker replay",
        )
        await topology.record_planned_trial(
            workspace_key="dev-01",
            skill_graph_operation_id=operation.skill_graph_operation_id,
            trial_kind="broker_canary",
            objective="broker canary",
        )

    asyncio.run(add_trials())
    result = asyncio.run(
        topology.record_broker_trial_scores(
            workspace_key="dev-01",
            skill_graph_operation_id=operation.skill_graph_operation_id,
            replay_result={"total": 3, "matched": 3, "mismatched": 0},
            canary_metrics={"harmful_rate": 0.0, "shadowed_rate": 0.0},
            scored_by="test-worker",
        )
    )

    assert result.allowed is True
    assert result.blockers == []
    assert {trial.status for trial in result.updated_trials} == {"passed"}
    assert {
        trial.result["broker_trial_score"]["scored_by"]
        for trial in result.updated_trials
    } == {"test-worker"}
