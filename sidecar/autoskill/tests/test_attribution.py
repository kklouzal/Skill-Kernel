import asyncio
from uuid import uuid4

import pytest
from autoskill.db.attribution import (
    ATTRIBUTION_OUTCOMES,
    NullAttributionStore,
    normalize_attribution_outcome,
)


def test_section_27_attribution_outcomes_are_canonical() -> None:
    assert {
        "skill_helped",
        "skill_hurt",
        "skill_ignored",
        "skill_missing",
        "skill_shadowed",
        "agent_solved_independently",
        "tool_failed_independent",
        "environment_drifted",
        "user_correction_changed_requirements",
        "unknown",
    } == ATTRIBUTION_OUTCOMES


def test_attribution_outcome_aliases_normalize_to_section_27_slugs() -> None:
    assert normalize_attribution_outcome("skill helped") == "skill_helped"
    assert normalize_attribution_outcome("missing_skill") == "skill_missing"
    assert normalize_attribution_outcome("wrong-skill") == "skill_shadowed"
    assert normalize_attribution_outcome("tool failed independent of skill") == (
        "tool_failed_independent"
    )
    assert normalize_attribution_outcome("user correction changed requirements") == (
        "user_correction_changed_requirements"
    )


def test_null_attribution_store_normalizes_recorded_event_outcome() -> None:
    store = NullAttributionStore()

    async def run():
        return await store.record_event(
            workspace_key="dev-01",
            session_id="s",
            turn_id="t",
            action_kind="runtime_outcome",
            risk_level="medium",
            skill_ids=[uuid4()],
            outcome="failed",
            metadata={"source": "legacy"},
        )

    event = asyncio.run(run())

    assert event.outcome == "skill_hurt"
    assert event.metadata == {"source": "legacy", "raw_outcome": "failed"}


def test_attribution_outcome_rejects_unsupported_string() -> None:
    with pytest.raises(ValueError, match="unsupported attribution outcome"):
        normalize_attribution_outcome("mysterious positive-ish result")
