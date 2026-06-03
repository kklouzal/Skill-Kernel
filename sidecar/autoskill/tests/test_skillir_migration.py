import asyncio
from uuid import UUID, uuid4

from autoskill.api.app import SkillIRMigrationProposalRequest, create_app
from autoskill.core.skillir import SkillIR
from autoskill.db.candidates import CandidatePersistResult
from autoskill.services.skillir_migration import (
    MIGRATION_COMPILER_VERSION,
    propose_skill_ir_migration,
)


class MemoryCandidateStore:
    def __init__(self) -> None:
        self.evolution_transaction_id: UUID | None = None
        self.proposals: list[object] = []

    async def persist_candidate_proposals(
        self,
        *,
        workspace_key: str,
        proposals: list[object],
        evolution_transaction_id: UUID | None = None,
    ) -> CandidatePersistResult:
        self.evolution_transaction_id = evolution_transaction_id
        self.proposals = proposals
        return CandidatePersistResult(
            persisted=len(proposals),
            skipped=0,
            candidates=[],
            evolution_transaction_id=evolution_transaction_id,
        )


def test_skillir_migration_proposes_new_gated_revision() -> None:
    source_revision_id = uuid4()
    source = skill_ir()

    result = propose_skill_ir_migration(
        source_skill_ir=source,
        source_revision_id=source_revision_id,
        migration_reason="record compiler migration gate metadata",
    )

    proposal = result.proposals[0]
    payload = proposal.to_json()

    assert result.proposed == 1
    assert result.skipped == 0
    assert payload["recommendation"] == "propose_migration"
    assert payload["skillir"]["version"] == source.version + 1
    assert payload["skillir"]["compiler_version"] == MIGRATION_COMPILER_VERSION
    assert payload["skillir"]["steps"] == source.steps
    assert payload["metadata"]["proposal_kind"] == "skill_ir_migration"
    assert payload["metadata"]["source_revision_id"] == str(source_revision_id)
    assert payload["metadata"]["migration_reason"] == "record compiler migration gate metadata"
    assert payload["metadata"]["semantic_preservation"]["status"] == "passed"
    assert payload["metadata"]["rollback_action"]["reactivate_source_revision_id"] == str(
        source_revision_id
    )
    assert proposal.compiled_sha256
    assert [probe.kind for probe in proposal.probe_plan] == [
        "target",
        "no_skill_control",
        "regression",
        "adversarial",
    ]


def test_skillir_migration_fails_closed_for_broad_description() -> None:
    source = skill_ir().model_copy(update={"description": "Does a broad thing"})

    result = propose_skill_ir_migration(
        source_skill_ir=source,
        source_revision_id=uuid4(),
        migration_reason="attempt invalid legacy migration",
    )

    proposal = result.proposals[0].to_json()

    assert result.proposed == 0
    assert result.skipped == 1
    assert proposal["skillir"] is None
    assert proposal["metadata"]["fail_closed"] is True
    assert proposal["skipped_reason"].startswith("description_style_invalid")


def test_skillir_migration_api_can_persist_inactive_candidate_revision() -> None:
    candidate_store = MemoryCandidateStore()
    app = create_app(candidate_store=candidate_store)
    route = next(route for route in app.routes if route.path == "/v1/skillir/migrations/propose")
    source_revision_id = uuid4()

    async def run():
        return await route.endpoint(
            request=SkillIRMigrationProposalRequest(
                workspace_id="dev-01",
                source_revision_id=source_revision_id,
                source_skill_ir=skill_ir().model_dump(by_alias=True, mode="json"),
                migration_reason="stage deterministic migration candidate",
            )
        )

    response = asyncio.run(run())

    assert response.proposed == 1
    assert response.persistence is not None
    assert response.persistence["persisted"] == 1
    assert response.persistence["transaction"]["status"] == "staged"
    assert candidate_store.evolution_transaction_id is not None
    proposal = candidate_store.proposals[0]
    assert proposal.metadata["source_revision_id"] == str(source_revision_id)
    assert proposal.metadata["rollback_action"]["archive_candidate_revision"] is True


def skill_ir() -> SkillIR:
    return SkillIR(
        skill_id=uuid4(),
        slug="pdf-table-cleanup",
        name="pdf-table-cleanup",
        description=(
            "Clean PDF table extraction; use when repeated PDF rows need normalization; "
            "not for generic document editing."
        ),
        version=3,
        applicability=[
            "Use for repeated PDF table extraction cleanup backed by cited evidence.",
        ],
        inputs=["PDF table extraction output and cited evidence IDs."],
        preconditions=["The source revision is an existing SkillIR revision."],
        steps=[
            "Inspect extracted rows for repeated alignment drift.",
            "Normalize rows using the established table cleanup procedure.",
        ],
        outputs=["Normalized table rows."],
        effects=["Records a deterministic cleanup procedure for PDF table extraction."],
        state_delta=["May create an inactive migrated SkillIR revision."],
        side_effects=["Does not mutate active runtime skill files."],
        termination=["Stop after staging the migrated candidate revision."],
        idempotency="retry_safe",
        verification=["Confirm normalized rows preserve table semantics."],
        failure_handling=["Leave the source revision active when migration gates fail."],
        failure_modes=["Source content is too broad to preserve safely."],
        do_not_use_when=["The source SkillIR does not describe PDF table cleanup."],
        never=["Do not mutate historical SkillIR revisions in place."],
        evidence_ids=[str(uuid4())],
        risk_notes=["Existing source revision is activation-gated."],
    )
