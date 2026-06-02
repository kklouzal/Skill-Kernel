import asyncio
from datetime import datetime
from uuid import uuid4

from autoskill.db.utility import (
    SkillUtilityRollupRecord,
    _merge_probe_plan,
    _plan_improvements_and_splits,
)
from autoskill.services.utility import SkillUtilityFeatures, compute_utility_score


def test_compute_utility_score_rewards_help_and_penalizes_harm() -> None:
    features = SkillUtilityFeatures(
        helped_count=3,
        hurt_count=1,
        shadow_count=2,
        retrieval_count=10,
        canary_failure_count=1,
    )

    assert compute_utility_score(features) == -4.5


def test_curation_plans_split_and_improvement_actions() -> None:
    class FakeConn:
        def __init__(self) -> None:
            self.rows = []

        async def fetchrow(self, _query, *_args):
            self.rows.append(_args)
            return {
                "curation_action_id": uuid4(),
                "skill_id": _args[1],
                "action": _args[2],
                "status": _args[3],
                "reason": _args[4],
                "features": _args[5],
                "created_at": datetime.now().astimezone(),
            }

    conn = FakeConn()
    split_skill = uuid4()
    improve_skill = uuid4()

    async def run():
        return await _plan_improvements_and_splits(
            conn,
            workspace_id=uuid4(),
            rollups=[
                SkillUtilityRollupRecord(
                    skill_id=split_skill,
                    workspace_id=None,
                    workspace_key="dev-01",
                    slug="broad-skill",
                    lifecycle_state="active",
                    utility_score=-1.0,
                    features=SkillUtilityFeatures(hurt_count=1, shadow_count=2),
                    computed_at=datetime.now().astimezone(),
                ),
                SkillUtilityRollupRecord(
                    skill_id=improve_skill,
                    workspace_id=None,
                    workspace_key="dev-01",
                    slug="harmful-skill",
                    lifecycle_state="active",
                    utility_score=-2.0,
                    features=SkillUtilityFeatures(hurt_count=2),
                    computed_at=datetime.now().astimezone(),
                ),
            ],
            max_actions=5,
        )

    actions = asyncio.run(run())

    assert [action.action for action in actions] == ["plan_split", "plan_improvement"]
    assert {action.status for action in actions} == {"planned"}
    assert actions[0].features["repair_proposal"]["proposal_kind"] == "decompose"
    assert "sibling" in actions[0].features["repair_proposal"]["planned_trials"]
    assert actions[1].features["repair_proposal"]["proposal_kind"] == "improve"
    assert actions[1].features["repair_proposal"]["acceptance_gate"] == {
        "scanner_pass": True,
        "regression_failures": 0,
        "utility_delta_positive": True,
        "requires_no_skill_control": True,
    }


def test_duplicate_merge_probe_plan_requires_equivalence_and_rollback() -> None:
    left = uuid4()
    right = uuid4()

    plan = _merge_probe_plan(
        from_skill_id=left,
        to_skill_id=right,
        from_slug="left-skill",
        to_slug="right-skill",
    )

    assert plan["candidate_skill_ids"] == [str(left), str(right)]
    assert plan["required_probe_kinds"] == [
        "equivalence",
        "regression",
        "sibling_shadowing",
        "no_skill_control",
    ]
    assert plan["acceptance_gate"]["regression_failures"] == 0
    assert plan["rollback"] == {
        "required": True,
        "restore_archived_duplicate": True,
        "revoke_duplicate_edge_changes": True,
    }
