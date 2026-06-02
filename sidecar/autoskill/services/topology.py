from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from autoskill.core.hashing import sha256_json
from autoskill.core.skillgraph import SkillGraphEdge, SkillGraphIR, SkillGraphNode
from autoskill.core.skillir import EffectSignature
from autoskill.db.governance import GovernanceStore
from autoskill.db.topology import TopologyPersistenceRecord, TopologyStore

TopologyOperationKind = Literal["create", "improve", "compose", "decompose"]

MAX_COMPONENTS = 8
MAX_SUCCESSORS = 8


@dataclass(frozen=True)
class TopologySkill:
    slug: str
    effects: EffectSignature
    skill_id: UUID | None = None

    def node(
        self,
        operation_role: Literal["subject", "component", "successor", "composed_output"],
    ) -> SkillGraphNode:
        return SkillGraphNode(
            skill_id=self.skill_id,
            slug=self.slug,
            operation_role=operation_role,
            effects=self.effects,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "skill_id": str(self.skill_id) if self.skill_id else None,
            "slug": self.slug,
            "effects": self.effects.model_dump(mode="json"),
        }


@dataclass(frozen=True)
class ImproveTopologyRequest:
    subject: TopologySkill
    proposed: TopologySkill
    evidence_ids: list[str]
    improvement_reasons: list[str]


@dataclass(frozen=True)
class CreateTopologyRequest:
    proposed: TopologySkill
    evidence_ids: list[str]
    creation_reasons: list[str]


@dataclass(frozen=True)
class ComposeTopologyRequest:
    components: list[TopologySkill]
    composed_output: TopologySkill
    evidence_ids: list[str]
    required_effects_by_component: dict[str, list[str]] | None = None
    max_components: int = MAX_COMPONENTS


@dataclass(frozen=True)
class DecomposeTopologyRequest:
    subject: TopologySkill
    successors: list[TopologySkill]
    evidence_ids: list[str]
    coverage_requirements: list[str] | None = None
    max_successors: int = MAX_SUCCESSORS


@dataclass(frozen=True)
class TopologyTrialPlan:
    kind: str
    objective: str
    expected: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "objective": self.objective,
            "expected": self.expected,
        }


@dataclass(frozen=True)
class TopologyTransactionPlan:
    transaction_kind: str
    idempotency_key: str
    plan_hash: str
    status: Literal["candidate", "blocked"]
    rollback_actions: list[dict[str, Any]]
    writes: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "transaction_kind": self.transaction_kind,
            "idempotency_key": self.idempotency_key,
            "plan_hash": self.plan_hash,
            "status": self.status,
            "rollback_actions": self.rollback_actions,
            "writes": self.writes,
        }


@dataclass(frozen=True)
class TopologyProposalResult:
    operation_kind: TopologyOperationKind
    status: Literal["candidate", "blocked"]
    plan_hash: str
    blockers: list[str]
    evidence_ids: list[str]
    skill_graph_ir: SkillGraphIR | None
    trial_plan: list[TopologyTrialPlan]
    transaction: TopologyTransactionPlan

    @property
    def ok(self) -> bool:
        return self.status == "candidate"

    def to_json(self) -> dict[str, Any]:
        graph = (
            self.skill_graph_ir.model_dump(by_alias=True, mode="json")
            if self.skill_graph_ir
            else None
        )
        return {
            "operation_kind": self.operation_kind,
            "status": self.status,
            "plan_hash": self.plan_hash,
            "blockers": self.blockers,
            "evidence_ids": self.evidence_ids,
            "skill_graph_ir": graph,
            "trial_plan": [trial.to_json() for trial in self.trial_plan],
            "transaction": self.transaction.to_json(),
        }


async def persist_topology_proposal(
    topology: TopologyStore,
    governance: GovernanceStore,
    *,
    workspace_key: str,
    proposal: TopologyProposalResult,
) -> TopologyPersistenceRecord:
    evidence_ids = _uuid_values(proposal.evidence_ids)
    transaction = await governance.start_transaction(
        workspace_key=workspace_key,
        transaction_kind=proposal.transaction.transaction_kind,
        idempotency_key=proposal.transaction.idempotency_key,
        plan_hash=proposal.transaction.plan_hash,
        cause={
            "source": "topology_proposal",
            "operation_kind": proposal.operation_kind,
            "status": proposal.status,
            "blockers": proposal.blockers,
        },
        source_evidence_ids=evidence_ids,
        policy_snapshot={
            "mode": "propose_only",
            "writes": proposal.transaction.writes,
            "requires_trial_before_apply": True,
        },
    )
    graph = (
        proposal.skill_graph_ir.model_dump(by_alias=True, mode="json")
        if proposal.skill_graph_ir
        else {}
    )
    operation = await topology.record_operation(
        workspace_key=workspace_key,
        operation_kind=proposal.operation_kind,
        status=proposal.status,
        subject_skill_ids=_operation_skill_ids(proposal, roles={"subject", "component"}),
        output_skill_ids=_operation_skill_ids(
            proposal,
            roles={"successor", "composed_output"},
        ),
        skill_graph_ir=graph,
        evidence_ids=evidence_ids,
        effect_coverage=graph.get("effect_coverage", {}) if graph else {},
        trial_summary={
            "plan_hash": proposal.plan_hash,
            "blockers": proposal.blockers,
            "trials": [trial.to_json() for trial in proposal.trial_plan],
        },
        evolution_transaction_id=transaction.transaction.evolution_transaction_id,
    )
    await governance.record_transaction_item(
        evolution_transaction_id=transaction.transaction.evolution_transaction_id,
        item_kind="skill_graph_operation",
        item_id=operation.skill_graph_operation_id,
        activation_state=proposal.status,
        after_hash=proposal.plan_hash,
        rollback_action={
            "operation": "mark_topology_operation_rolled_back",
            "skill_graph_operation_id": str(operation.skill_graph_operation_id),
        },
    )
    await governance.record_provenance_edge(
        workspace_key=workspace_key,
        source_kind="evolution_transaction",
        source_id=transaction.transaction.evolution_transaction_id,
        derived_kind="skill_graph_operation",
        derived_id=operation.skill_graph_operation_id,
        relation="planned_topology_operation",
    )
    for evidence_id in evidence_ids:
        await governance.record_provenance_edge(
            workspace_key=workspace_key,
            source_kind="evidence_item",
            source_id=evidence_id,
            derived_kind="skill_graph_operation",
            derived_id=operation.skill_graph_operation_id,
            relation="supports_topology_proposal",
        )

    trials = []
    for trial in proposal.trial_plan:
        trial_record = await topology.record_planned_trial(
            workspace_key=workspace_key,
            skill_graph_operation_id=operation.skill_graph_operation_id,
            trial_kind=trial.kind,
            objective=trial.objective,
            expected=trial.expected,
            status="blocked" if proposal.status == "blocked" else "planned",
            result={"blockers": proposal.blockers} if proposal.status == "blocked" else {},
            evolution_transaction_id=transaction.transaction.evolution_transaction_id,
        )
        trials.append(trial_record)
        await governance.record_transaction_item(
            evolution_transaction_id=transaction.transaction.evolution_transaction_id,
            item_kind="planned_topology_trial",
            item_id=trial_record.planned_topology_trial_id,
            activation_state=trial_record.status,
            after_hash=sha256_json(trial_record.to_json()),
            rollback_action={
                "operation": "retire_planned_topology_trial",
                "planned_topology_trial_id": str(trial_record.planned_topology_trial_id),
            },
        )
        await governance.record_provenance_edge(
            workspace_key=workspace_key,
            source_kind="skill_graph_operation",
            source_id=operation.skill_graph_operation_id,
            derived_kind="planned_topology_trial",
            derived_id=trial_record.planned_topology_trial_id,
            relation="requires_trial",
        )

    await governance.update_transaction_status(
        evolution_transaction_id=transaction.transaction.evolution_transaction_id,
        status="staged" if proposal.status == "candidate" else "blocked",
        metrics={
            "topology_operation_kind": proposal.operation_kind,
            "planned_trials": len(trials),
            "blockers": len(proposal.blockers),
        },
    )
    return TopologyPersistenceRecord(operation=operation, trials=trials)


def propose_creation(request: CreateTopologyRequest) -> TopologyProposalResult:
    proposed_terms = _effect_terms(request.proposed.effects)
    blockers: list[str] = []
    if not proposed_terms:
        blockers.append("create proposal requires at least one declared effect")
    if not request.evidence_ids:
        blockers.append("create proposal requires cited evidence")
    if not request.creation_reasons:
        blockers.append("create proposal requires at least one deterministic reason")

    graph: SkillGraphIR | None = None
    if not blockers:
        graph = SkillGraphIR(
            operation_kind="create",
            nodes=[request.proposed.node("successor")],
            edges=[],
            effect_coverage={term: [request.proposed.slug] for term in sorted(proposed_terms)},
            rollback_blockers=[],
        )

    payload = {
        "operation_kind": "create",
        "proposed": request.proposed.to_json(),
        "evidence_ids": sorted(request.evidence_ids),
        "creation_reasons": sorted(request.creation_reasons),
        "blockers": blockers,
        "graph": _graph_json(graph),
    }
    return _result(
        operation_kind="create",
        payload=payload,
        blockers=blockers,
        evidence_ids=request.evidence_ids,
        graph=graph,
        trial_plan=[
            TopologyTrialPlan(
                kind="target_creation",
                objective="Confirm the proposed skill addresses the cited missing workflow.",
                expected={
                    "positive_marginal_value": True,
                    "reasons": list(request.creation_reasons),
                },
            ),
            TopologyTrialPlan(
                kind="no_skill_control",
                objective="Accept only if the new skill beats the no-skill baseline.",
                expected={"beats_no_skill": True},
            ),
            TopologyTrialPlan(
                kind="nearest_active_collision",
                objective="Reject if an existing active skill already covers the target effects.",
                expected={"no_active_duplicate": True},
            ),
            TopologyTrialPlan(
                kind="rollback_readiness",
                objective="Keep first activation reversible until canaries pass.",
                expected={"rollback_actions_planned": True},
            ),
        ],
        rollback_actions=_create_rollback_actions(request),
    )


def propose_improvement(request: ImproveTopologyRequest) -> TopologyProposalResult:
    subject_terms = _effect_terms(request.subject.effects)
    proposed_terms = _effect_terms(request.proposed.effects)
    missing = sorted(subject_terms - proposed_terms)
    blockers = [
        f"proposed skill does not preserve subject effect: {term}"
        for term in missing
    ]
    if not request.improvement_reasons:
        blockers.append("improvement proposal requires at least one deterministic reason")

    graph: SkillGraphIR | None = None
    if not blockers:
        rollback_blockers = _rollback_blockers([request.subject])
        graph = SkillGraphIR(
            operation_kind="improve",
            nodes=[
                request.subject.node("subject"),
                request.proposed.node("successor"),
            ],
            edges=[
                SkillGraphEdge(
                    from_slug=request.subject.slug,
                    to_slug=request.proposed.slug,
                    edge_kind="supersedes",
                    required_effects=sorted(subject_terms),
                    produced_effects=sorted(proposed_terms),
                )
            ],
            effect_coverage={
                term: [request.proposed.slug]
                for term in sorted(subject_terms)
                if term in proposed_terms
            },
            rollback_blockers=rollback_blockers,
        )

    payload = {
        "operation_kind": "improve",
        "subject": request.subject.to_json(),
        "proposed": request.proposed.to_json(),
        "evidence_ids": sorted(request.evidence_ids),
        "improvement_reasons": sorted(request.improvement_reasons),
        "blockers": blockers,
        "graph": _graph_json(graph),
    }
    return _result(
        operation_kind="improve",
        payload=payload,
        blockers=blockers,
        evidence_ids=request.evidence_ids,
        graph=graph,
        trial_plan=[
            TopologyTrialPlan(
                kind="target_improvement",
                objective="Confirm the successor improves the cited failure or utility signal.",
                expected={
                    "positive_marginal_value": True,
                    "reasons": list(request.improvement_reasons),
                },
            ),
            TopologyTrialPlan(
                kind="regression",
                objective="Reject the improvement if preserved subject effects regress.",
                expected={"preserved_effects": sorted(subject_terms)},
            ),
            TopologyTrialPlan(
                kind="rollback_readiness",
                objective="Keep the original skill restorable until canaries pass.",
                expected={"rollback_actions_planned": True},
            ),
        ],
        rollback_actions=_improve_rollback_actions(request),
    )


def propose_composition(request: ComposeTopologyRequest) -> TopologyProposalResult:
    blockers = _bounded_component_blockers(request.components, request.max_components)
    required_by_slug = request.required_effects_by_component or {}
    produced_so_far: set[str] = set()
    edges: list[SkillGraphEdge] = []

    for component in request.components:
        required = set(required_by_slug.get(component.slug, []))
        gaps = sorted(required - produced_so_far)
        if gaps:
            blockers.extend(
                f"component {component.slug} requires unresolved effect: {gap}"
                for gap in gaps
            )
        produced = _effect_terms(component.effects)
        if required:
            edges.append(
                SkillGraphEdge(
                    from_slug=request.components[0].slug,
                    to_slug=component.slug,
                    edge_kind="requires",
                    required_effects=sorted(required),
                    produced_effects=sorted(produced_so_far),
                )
            )
        produced_so_far.update(produced)

    output_terms = _effect_terms(request.composed_output.effects)
    component_terms = _union_effect_terms(request.components)
    if not (output_terms & component_terms):
        blockers.append("composed output has no effect overlap with its components")

    graph: SkillGraphIR | None = None
    if not blockers:
        graph_edges = [
            *[
                SkillGraphEdge(
                    from_slug=component.slug,
                    to_slug=request.composed_output.slug,
                    edge_kind="component_of",
                    produced_effects=sorted(_effect_terms(component.effects)),
                    required_effects=sorted(output_terms & _effect_terms(component.effects)),
                )
                for component in request.components
            ],
            *edges,
        ]
        graph = SkillGraphIR(
            operation_kind="compose",
            nodes=[
                *[component.node("component") for component in request.components],
                request.composed_output.node("composed_output"),
            ],
            edges=graph_edges,
            effect_coverage={
                term: [
                    component.slug
                    for component in request.components
                    if term in _effect_terms(component.effects)
                ]
                for term in sorted(output_terms & component_terms)
            },
            rollback_blockers=_rollback_blockers(request.components),
        )

    payload = {
        "operation_kind": "compose",
        "components": [component.to_json() for component in request.components],
        "composed_output": request.composed_output.to_json(),
        "evidence_ids": sorted(request.evidence_ids),
        "required_effects_by_component": {
            key: sorted(value) for key, value in sorted(required_by_slug.items())
        },
        "blockers": blockers,
        "graph": _graph_json(graph),
    }
    return _result(
        operation_kind="compose",
        payload=payload,
        blockers=blockers,
        evidence_ids=request.evidence_ids,
        graph=graph,
        trial_plan=[
            TopologyTrialPlan(
                kind="component_baseline",
                objective="Measure existing component-only workflow performance.",
                expected={"component_slugs": [component.slug for component in request.components]},
            ),
            TopologyTrialPlan(
                kind="composed_workflow",
                objective="Accept only if composed workflow beats component-only baseline.",
                expected={"positive_marginal_value": True},
            ),
            TopologyTrialPlan(
                kind="shadowing",
                objective="Reject if the composed skill steals narrow component tasks.",
                expected={"no_component_shadowing": True},
            ),
            TopologyTrialPlan(
                kind="broker_replay",
                objective=(
                    "Replay component, composed-workflow, and no-skill control "
                    "episodes before compose activation."
                ),
                expected={
                    "operation_kind": "compose",
                    "component_skill_ids": [
                        str(component.skill_id)
                        for component in request.components
                        if component.skill_id
                    ],
                    "composed_skill_id": (
                        str(request.composed_output.skill_id)
                        if request.composed_output.skill_id
                        else None
                    ),
                    "required_decisions": [
                        "component_baseline",
                        "composed_workflow",
                        "no_skill_control",
                    ],
                    "block_on_mismatch": True,
                },
            ),
            TopologyTrialPlan(
                kind="broker_canary",
                objective=(
                    "Canary composed routing and roll back if component shadowing "
                    "or harmful routing appears."
                ),
                expected={
                    "operation_kind": "compose",
                    "max_harmful_rate": 0.0,
                    "max_shadowed_rate": 0.2,
                    "max_ignored_rate": 0.5,
                },
            ),
        ],
        rollback_actions=_compose_rollback_actions(request),
    )


def propose_decomposition(request: DecomposeTopologyRequest) -> TopologyProposalResult:
    blockers = _bounded_component_blockers(request.successors, request.max_successors)
    required = set(request.coverage_requirements or sorted(_effect_terms(request.subject.effects)))
    coverage = {
        term: [
            successor.slug
            for successor in request.successors
            if term in _effect_terms(successor.effects)
        ]
        for term in sorted(required)
    }
    missing = [term for term, slugs in coverage.items() if not slugs]
    blockers.extend(
        f"successor set does not cover subject effect: {term}"
        for term in missing
    )

    graph: SkillGraphIR | None = None
    if not blockers:
        graph = SkillGraphIR(
            operation_kind="decompose",
            nodes=[
                request.subject.node("subject"),
                *[successor.node("successor") for successor in request.successors],
            ],
            edges=[
                SkillGraphEdge(
                    from_slug=request.subject.slug,
                    to_slug=successor.slug,
                    edge_kind="decomposes_to",
                    required_effects=sorted(required & _effect_terms(successor.effects)),
                    produced_effects=sorted(_effect_terms(successor.effects)),
                )
                for successor in request.successors
            ],
            effect_coverage=coverage,
            rollback_blockers=_rollback_blockers([request.subject]),
        )

    payload = {
        "operation_kind": "decompose",
        "subject": request.subject.to_json(),
        "successors": [successor.to_json() for successor in request.successors],
        "evidence_ids": sorted(request.evidence_ids),
        "coverage_requirements": sorted(required),
        "blockers": blockers,
        "graph": _graph_json(graph),
    }
    return _result(
        operation_kind="decompose",
        payload=payload,
        blockers=blockers,
        evidence_ids=request.evidence_ids,
        graph=graph,
        trial_plan=[
            TopologyTrialPlan(
                kind="original_baseline",
                objective="Measure original broad-skill routing and token cost.",
                expected={"subject_slug": request.subject.slug},
            ),
            TopologyTrialPlan(
                kind="successor_routing",
                objective="Accept only if successors improve routing precision or cost.",
                expected={"successor_slugs": [successor.slug for successor in request.successors]},
            ),
            TopologyTrialPlan(
                kind="coverage_regression",
                objective="Reject if successors lose high-value original probes.",
                expected={
                    "covered_effects": sorted(
                        term for term, slugs in coverage.items() if slugs
                    )
                },
            ),
            TopologyTrialPlan(
                kind="broker_replay",
                objective=(
                    "Replay subject, successor, and no-skill control episodes "
                    "before decompose activation."
                ),
                expected={
                    "operation_kind": "decompose",
                    "subject_skill_ids": [
                        str(request.subject.skill_id)
                    ]
                    if request.subject.skill_id
                    else [],
                    "successor_skill_ids": [
                        str(successor.skill_id)
                        for successor in request.successors
                        if successor.skill_id
                    ],
                    "required_decisions": [
                        "original_baseline",
                        "successor_routing",
                        "no_skill_control",
                    ],
                    "block_on_mismatch": True,
                },
            ),
            TopologyTrialPlan(
                kind="broker_canary",
                objective=(
                    "Canary successor routing and roll back if decomposition "
                    "loses coverage or creates harmful routing."
                ),
                expected={
                    "operation_kind": "decompose",
                    "max_harmful_rate": 0.0,
                    "max_shadowed_rate": 0.2,
                    "max_ignored_rate": 0.5,
                },
            ),
        ],
        rollback_actions=_decompose_rollback_actions(request),
    )


def _result(
    *,
    operation_kind: TopologyOperationKind,
    payload: dict[str, Any],
    blockers: list[str],
    evidence_ids: list[str],
    graph: SkillGraphIR | None,
    trial_plan: list[TopologyTrialPlan],
    rollback_actions: list[dict[str, Any]],
) -> TopologyProposalResult:
    plan_hash = sha256_json(payload)
    status: Literal["candidate", "blocked"] = "blocked" if blockers else "candidate"
    transaction = TopologyTransactionPlan(
        transaction_kind=f"topology_{operation_kind}",
        idempotency_key=f"topology:{operation_kind}:{plan_hash}",
        plan_hash=plan_hash,
        status=status,
        rollback_actions=rollback_actions,
        writes=[
            "skill_graph_operations",
            "evolution_transactions",
            "transaction_items",
            "planned_topology_trials",
        ],
    )
    return TopologyProposalResult(
        operation_kind=operation_kind,
        status=status,
        plan_hash=plan_hash,
        blockers=blockers,
        evidence_ids=evidence_ids,
        skill_graph_ir=graph,
        trial_plan=trial_plan,
        transaction=transaction,
    )


def _bounded_component_blockers(skills: list[TopologySkill], max_count: int) -> list[str]:
    blockers: list[str] = []
    if len(skills) < 2:
        blockers.append("topology operation requires at least two related skills")
    if len(skills) > max_count:
        blockers.append(f"topology operation is bounded to {max_count} skills")
    slugs = [skill.slug for skill in skills]
    duplicates = sorted({slug for slug in slugs if slugs.count(slug) > 1})
    blockers.extend(f"duplicate skill slug: {slug}" for slug in duplicates)
    return blockers


def _effect_terms(effects: EffectSignature) -> set[str]:
    return {
        value.strip()
        for values in (
            effects.outputs,
            effects.effects,
            effects.state_delta,
            effects.termination,
        )
        for value in values
        if value.strip()
    }


def _union_effect_terms(skills: list[TopologySkill]) -> set[str]:
    terms: set[str] = set()
    for skill in skills:
        terms.update(_effect_terms(skill.effects))
    return terms


def _rollback_blockers(skills: list[TopologySkill]) -> list[str]:
    return [
        f"{skill.slug} has no stable skill_id for rollback anchoring"
        for skill in skills
        if skill.skill_id is None
    ]


def _improve_rollback_actions(request: ImproveTopologyRequest) -> list[dict[str, Any]]:
    return [
        {
            "operation": "restore_subject_skill",
            "subject_slug": request.subject.slug,
            "subject_skill_id": str(request.subject.skill_id) if request.subject.skill_id else None,
            "remove_successor_slug": request.proposed.slug,
        }
    ]


def _create_rollback_actions(request: CreateTopologyRequest) -> list[dict[str, Any]]:
    return [
        {
            "operation": "remove_created_skill",
            "created_slug": request.proposed.slug,
            "created_skill_id": (
                str(request.proposed.skill_id) if request.proposed.skill_id else None
            ),
        }
    ]


def _compose_rollback_actions(request: ComposeTopologyRequest) -> list[dict[str, Any]]:
    return [
        {
            "operation": "remove_composed_output",
            "composed_slug": request.composed_output.slug,
            "composed_skill_id": (
                str(request.composed_output.skill_id)
                if request.composed_output.skill_id
                else None
            ),
        },
        {
            "operation": "restore_component_routing",
            "component_slugs": [component.slug for component in request.components],
            "component_skill_ids": [
                str(component.skill_id) if component.skill_id else None
                for component in request.components
            ],
        },
    ]


def _decompose_rollback_actions(request: DecomposeTopologyRequest) -> list[dict[str, Any]]:
    return [
        {
            "operation": "restore_subject_skill",
            "subject_slug": request.subject.slug,
            "subject_skill_id": str(request.subject.skill_id) if request.subject.skill_id else None,
            "remove_successor_slugs": [successor.slug for successor in request.successors],
        }
    ]


def _graph_json(graph: SkillGraphIR | None) -> dict[str, Any] | None:
    if graph is None:
        return None
    return graph.model_dump(by_alias=True, mode="json")


def _uuid_values(values: list[str]) -> list[UUID]:
    parsed: list[UUID] = []
    for value in values:
        try:
            parsed.append(UUID(str(value)))
        except ValueError:
            continue
    return parsed


def _operation_skill_ids(
    proposal: TopologyProposalResult,
    *,
    roles: set[str],
) -> list[UUID]:
    if proposal.skill_graph_ir is None:
        return []
    return [
        node.skill_id
        for node in proposal.skill_graph_ir.nodes
        if node.skill_id is not None and node.operation_role in roles
    ]
