from autoskill.services.contrastive import derive_contrastive_replay


def evidence(
    evidence_id: str,
    *,
    mode: str,
    success: bool,
    retries: int,
    slug: str,
    latency_ms: int | None = None,
):
    replay = {
        "candidate_slug": slug,
        "mode": mode,
        "success": success,
        "retries": retries,
    }
    if latency_ms is not None:
        replay["latency_ms"] = latency_ms
    return {
        "evidence_id": evidence_id,
        "payload": {
            "redacted_payload": {
                "autoskill_replay": replay,
            }
        },
    }


def test_contrastive_replay_uses_redacted_outcome_pairs() -> None:
    replay = derive_contrastive_replay(
        [
            evidence(
                "evidence-no-skill",
                mode="no_skill",
                success=False,
                retries=3,
                slug="demo",
                latency_ms=1000,
            ),
            evidence(
                "evidence-skill-visible",
                mode="skill_visible",
                success=True,
                retries=1,
                slug="demo",
                latency_ms=700,
            ),
        ],
        candidate_slug="demo",
    )

    assert replay is not None
    payload = replay.to_json()
    assert payload["no_skill"]["success"] is False
    assert payload["skill_visible"]["success"] is True
    assert payload["skill_visible"]["retries"] == 1.0
    assert payload["evidence_ids"] == ["evidence-no-skill", "evidence-skill-visible"]
    assert payload["basis"]["schema"] == "autoskill.contrastive_replay.v1"


def test_contrastive_replay_rejects_unimproved_or_mismatched_pairs() -> None:
    unimproved = derive_contrastive_replay(
        [
            evidence("baseline", mode="no_skill", success=True, retries=1, slug="demo"),
            evidence("candidate", mode="skill_visible", success=True, retries=2, slug="demo"),
        ],
        candidate_slug="demo",
    )
    mismatched = derive_contrastive_replay(
        [
            evidence("baseline", mode="no_skill", success=False, retries=3, slug="other"),
            evidence("candidate", mode="skill_visible", success=True, retries=1, slug="other"),
        ],
        candidate_slug="demo",
    )

    assert unimproved is None
    assert mismatched is None
