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
