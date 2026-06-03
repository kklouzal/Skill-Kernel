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


def test_contrastive_replay_derives_from_attribution_outcomes() -> None:
    replay = derive_contrastive_replay(
        [
            {
                "evidence_id": "missing-skill",
                "payload": {
                    "redacted_payload": {
                        "attribution_outcome": {
                            "candidate_slug": "demo",
                            "outcome": "missing_skill",
                            "latency_ms": 1200,
                        }
                    }
                },
            },
            {
                "evidence_id": "skill-helped",
                "payload": {
                    "redacted_payload": {
                        "attribution_outcome": {
                            "candidate_slug": "demo",
                            "outcome": "skill_helped",
                            "latency_ms": 800,
                        }
                    }
                },
            },
        ],
        candidate_slug="demo",
    )

    assert replay is not None
    payload = replay.to_json()
    assert payload["no_skill"]["success"] is False
    assert payload["skill_visible"]["success"] is True
    assert payload["basis"]["outcome_count"] == 2


def test_contrastive_replay_derives_from_canary_and_broker_outcomes() -> None:
    replay = derive_contrastive_replay(
        [
            {
                "evidence_id": "broker-no-skill",
                "payload": {
                    "redacted_payload": {
                        "broker_outcome": {
                            "candidate_slug": "demo",
                            "no_skill_control": True,
                            "status": "failed",
                            "retries": 3,
                        }
                    }
                },
            },
            {
                "evidence_id": "canary-visible",
                "payload": {
                    "redacted_payload": {
                        "canary_result": {
                            "candidate_slug": "demo",
                            "status": "passed",
                            "retries": 1,
                        }
                    }
                },
            },
        ],
        candidate_slug="demo",
    )

    assert replay is not None
    payload = replay.to_json()
    assert payload["no_skill"]["retries"] == 3.0
    assert payload["skill_visible"]["retries"] == 1.0


def test_contrastive_replay_derives_from_context_token_ledger_outcomes() -> None:
    replay = derive_contrastive_replay(
        [
            {
                "evidence_id": "context-hidden",
                "payload": {
                    "redacted_payload": {
                        "context_token_ledger_outcome": {
                            "candidate_slug": "demo",
                            "visibility_state": "skill_hidden",
                            "outcome": "no_skill_failed",
                            "latency_ms": 1400,
                        }
                    }
                },
            },
            {
                "evidence_id": "context-visible",
                "payload": {
                    "redacted_payload": {
                        "context_token_ledger_outcome": {
                            "candidate_slug": "demo",
                            "visibility_state": "skill_visible",
                            "outcome": "helped",
                            "latency_ms": 800,
                        }
                    }
                },
            },
        ],
        candidate_slug="demo",
    )

    assert replay is not None
    payload = replay.to_json()
    assert payload["no_skill"]["success"] is False
    assert payload["skill_visible"]["success"] is True
    assert payload["skill_visible"]["latency_ms"] == 800.0


def test_contrastive_replay_derives_context_token_ledger_source_metadata() -> None:
    replay = derive_contrastive_replay(
        [
            {
                "evidence_id": "context-negative-value",
                "payload": {
                    "redacted_payload": {
                        "source_kind": "context_token_ledger",
                        "skill_slug": "demo",
                        "outcome": "measured",
                        "source_metadata": {
                            "visibility_state": "no_skill",
                            "marginal_value": {
                                "marginal_value": -0.5,
                                "context_value_per_token": -0.01,
                            },
                        },
                    }
                },
            },
            {
                "evidence_id": "context-positive-value",
                "payload": {
                    "redacted_payload": {
                        "source_kind": "context_token_ledger",
                        "skill_slug": "demo",
                        "outcome": "measured",
                        "source_metadata": {
                            "visibility_state": "skill_visible",
                            "marginal_value": {
                                "marginal_value": 1.25,
                                "context_value_per_token": 0.025,
                            },
                        },
                    }
                },
            },
        ],
        candidate_slug="demo",
    )

    assert replay is not None
    payload = replay.to_json()
    assert payload["no_skill"]["success"] is False
    assert payload["skill_visible"]["success"] is True
    assert payload["evidence_ids"] == ["context-negative-value", "context-positive-value"]
