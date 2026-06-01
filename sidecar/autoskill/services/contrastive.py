from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContrastiveReplay:
    no_skill: dict[str, Any]
    skill_visible: dict[str, Any]
    evidence_ids: list[str]
    basis: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "no_skill": self.no_skill,
            "skill_visible": self.skill_visible,
            "evidence_ids": self.evidence_ids,
            "basis": self.basis,
        }


def derive_contrastive_replay(
    evidence: list[dict[str, Any]],
    *,
    candidate_slug: str | None = None,
) -> ContrastiveReplay | None:
    """Build a deterministic intervention replay from redacted paired outcome evidence."""
    outcomes = [_extract_outcome(record, candidate_slug=candidate_slug) for record in evidence]
    usable = [outcome for outcome in outcomes if outcome is not None]
    no_skill = [_normalize_outcome(outcome) for outcome in usable if outcome["mode"] == "no_skill"]
    skill_visible = [
        _normalize_outcome(outcome) for outcome in usable if outcome["mode"] == "skill_visible"
    ]
    if not no_skill or not skill_visible:
        return None

    baseline = _least_successful(no_skill)
    candidate = _most_successful(skill_visible)
    if not _candidate_improves(baseline, candidate):
        return None

    evidence_ids = sorted(
        {
            str(outcome["evidence_id"])
            for outcome in usable
            if outcome["mode"] in {"no_skill", "skill_visible"}
        }
    )
    return ContrastiveReplay(
        no_skill=baseline,
        skill_visible=candidate,
        evidence_ids=evidence_ids,
        basis={
            "schema": "autoskill.contrastive_replay.v1",
            "source": "clustered-redacted-evidence",
            "candidate_slug": candidate_slug,
            "outcome_count": len(usable),
        },
    )


def _extract_outcome(
    record: dict[str, Any],
    *,
    candidate_slug: str | None,
) -> dict[str, Any] | None:
    payload = _dict(record.get("payload"))
    redacted = _dict(payload.get("redacted_payload"))
    outcome = _dict(redacted.get("autoskill_replay"))
    if not outcome:
        outcome = _dict(redacted.get("contrastive_replay"))
    if not outcome:
        outcome = _dict(payload.get("contrastive_replay"))
    if not outcome:
        return None

    outcome_slug = outcome.get("candidate_slug")
    if candidate_slug and str(outcome_slug or "") != candidate_slug:
        return None
    mode = str(outcome.get("mode") or "")
    if mode not in {"no_skill", "skill_visible"}:
        return None
    if "success" not in outcome:
        return None

    return {
        "evidence_id": str(record.get("evidence_id") or ""),
        "mode": mode,
        "success": bool(outcome.get("success")),
        "retries": _optional_float(outcome.get("retries")),
        "latency_ms": _optional_float(outcome.get("latency_ms")),
        "candidate_slug": str(outcome_slug) if outcome_slug else None,
    }


def _normalize_outcome(outcome: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "success": bool(outcome["success"]),
        "evidence_id": outcome["evidence_id"],
    }
    if outcome.get("retries") is not None:
        normalized["retries"] = outcome["retries"]
    if outcome.get("latency_ms") is not None:
        normalized["latency_ms"] = outcome["latency_ms"]
    return normalized


def _least_successful(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(outcomes, key=_outcome_score)[0]


def _most_successful(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(outcomes, key=_outcome_score, reverse=True)[0]


def _outcome_score(outcome: dict[str, Any]) -> tuple[int, float, float]:
    success_score = 1 if outcome.get("success") else 0
    retries = _optional_float(outcome.get("retries"))
    latency = _optional_float(outcome.get("latency_ms"))
    return (
        success_score,
        -(retries if retries is not None else 1_000_000.0),
        -(latency if latency is not None else 1_000_000_000.0),
    )


def _candidate_improves(baseline: dict[str, Any], candidate: dict[str, Any]) -> bool:
    if candidate.get("success") and not baseline.get("success"):
        return True
    if not candidate.get("success"):
        return False
    baseline_retries = _optional_float(baseline.get("retries"))
    candidate_retries = _optional_float(candidate.get("retries"))
    if (
        baseline_retries is not None
        and candidate_retries is not None
        and candidate_retries < baseline_retries
    ):
        return True
    baseline_latency = _optional_float(baseline.get("latency_ms"))
    candidate_latency = _optional_float(candidate.get("latency_ms"))
    return (
        baseline_latency is not None
        and candidate_latency is not None
        and candidate_latency < baseline_latency
    )


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
