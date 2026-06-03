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
    outcome = _explicit_replay_outcome(payload, redacted)
    if not outcome:
        outcome = _attribution_outcome(payload, redacted)
    if not outcome:
        outcome = _canary_outcome(payload, redacted)
    if not outcome:
        outcome = _broker_outcome(payload, redacted)
    if not outcome:
        outcome = _context_token_ledger_outcome(payload, redacted)
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


def _explicit_replay_outcome(payload: dict[str, Any], redacted: dict[str, Any]) -> dict[str, Any]:
    for key in ("autoskill_replay", "contrastive_replay"):
        outcome = _dict(redacted.get(key))
        if outcome:
            return outcome
    return _dict(payload.get("contrastive_replay"))


def _attribution_outcome(payload: dict[str, Any], redacted: dict[str, Any]) -> dict[str, Any]:
    outcome = _dict(redacted.get("attribution_outcome")) or _dict(
        payload.get("attribution_outcome")
    )
    if not outcome:
        return {}
    status = str(outcome.get("outcome") or outcome.get("status") or "")
    mode = str(outcome.get("mode") or "")
    success = _outcome_success(status)
    if success is None:
        return {}
    if not mode:
        mode = "no_skill" if status in _NO_SKILL_OUTCOMES else "skill_visible"
    return _outcome_payload(outcome, mode=mode, success=success)


def _canary_outcome(payload: dict[str, Any], redacted: dict[str, Any]) -> dict[str, Any]:
    outcome = _dict(redacted.get("canary_result")) or _dict(payload.get("canary_result"))
    if not outcome:
        return {}
    status = str(outcome.get("status") or "")
    if status not in {"passed", "failed", "critical"}:
        return {}
    return _outcome_payload(
        outcome,
        mode=str(outcome.get("mode") or "skill_visible"),
        success=status == "passed",
    )


def _broker_outcome(payload: dict[str, Any], redacted: dict[str, Any]) -> dict[str, Any]:
    outcome = _dict(redacted.get("broker_outcome")) or _dict(payload.get("broker_outcome"))
    if not outcome:
        return {}
    status = str(outcome.get("outcome") or outcome.get("status") or "")
    success = _outcome_success(status)
    if success is None and "success" in outcome:
        success = bool(outcome.get("success"))
    if success is None:
        return {}
    mode = str(outcome.get("mode") or "")
    if not mode:
        mode = "no_skill" if bool(outcome.get("no_skill_control")) else "skill_visible"
    return _outcome_payload(outcome, mode=mode, success=success)


def _context_token_ledger_outcome(
    payload: dict[str, Any],
    redacted: dict[str, Any],
) -> dict[str, Any]:
    outcome = (
        _dict(redacted.get("context_token_ledger_outcome"))
        or _dict(redacted.get("context_token_ledger"))
        or _context_token_ledger_source(redacted)
        or _dict(payload.get("context_token_ledger_outcome"))
        or _dict(payload.get("context_token_ledger"))
        or _context_token_ledger_source(payload)
    )
    if not outcome:
        return {}
    status = str(outcome.get("outcome") or outcome.get("status") or "")
    success = _outcome_success(status)
    if success is None and "task_success" in outcome:
        success = bool(outcome.get("task_success"))
    if success is None:
        success = _marginal_value_success(outcome)
    if success is None:
        return {}
    mode = str(outcome.get("mode") or "")
    if not mode:
        visibility = str(outcome.get("visibility_state") or "")
        if visibility in {"no_skill", "skill_hidden"}:
            mode = "no_skill"
        elif visibility == "skill_visible":
            mode = "skill_visible"
    return _outcome_payload(outcome, mode=mode, success=success)


def _context_token_ledger_source(container: dict[str, Any]) -> dict[str, Any]:
    if str(container.get("source_kind") or "") != "context_token_ledger":
        return {}
    source_metadata = _dict(container.get("source_metadata"))
    return {
        **source_metadata,
        "candidate_slug": _first_present(
            container.get("candidate_slug"),
            source_metadata.get("candidate_slug"),
            container.get("skill_slug"),
            source_metadata.get("skill_slug"),
            container.get("slug"),
            source_metadata.get("slug"),
        ),
        "mode": _first_present(container.get("mode"), source_metadata.get("mode")),
        "visibility_state": _first_present(
            container.get("visibility_state"),
            source_metadata.get("visibility_state"),
        ),
        "outcome": _first_present(container.get("outcome"), source_metadata.get("outcome")),
        "status": _first_present(container.get("status"), source_metadata.get("status")),
        "retries": _first_present(container.get("retries"), source_metadata.get("retries")),
        "latency_ms": _first_present(
            container.get("latency_ms"),
            source_metadata.get("latency_ms"),
        ),
    }


_SUCCESS_OUTCOMES = {
    "skill_helped",
    "helped",
    "success",
    "succeeded",
    "passed",
    "agent_solved_independently",
    "no_skill_helped",
    "no_skill_success",
}
_FAILURE_OUTCOMES = {
    "skill_hurt",
    "hurt",
    "ignored",
    "ignored_load",
    "failed",
    "failure",
    "false_positive",
    "false_positive_load",
    "critical",
    "skill_shadowed",
    "shadowed",
    "skill_ignored",
    "wrong_skill",
    "missing_skill",
    "skill_missing",
    "no_skill_failed",
}
_NO_SKILL_OUTCOMES = {
    "agent_solved_independently",
    "no_skill_helped",
    "no_skill_success",
    "missing_skill",
    "skill_missing",
    "no_skill_failed",
}


def _outcome_success(status: str) -> bool | None:
    normalized = status.strip().lower()
    if normalized in _SUCCESS_OUTCOMES:
        return True
    if normalized in _FAILURE_OUTCOMES:
        return False
    return None


def _outcome_payload(outcome: dict[str, Any], *, mode: str, success: bool) -> dict[str, Any]:
    return {
        "candidate_slug": (
            outcome.get("candidate_slug") or outcome.get("skill_slug") or outcome.get("slug")
        ),
        "mode": mode,
        "success": success,
        "retries": outcome.get("retries"),
        "latency_ms": outcome.get("latency_ms"),
    }


def _marginal_value_success(outcome: dict[str, Any]) -> bool | None:
    value = _optional_float(outcome.get("marginal_value"))
    if value is None:
        marginal = _dict(outcome.get("marginal_value"))
        value = _optional_float(marginal.get("marginal_value"))
    if value is None:
        metadata = _dict(outcome.get("metadata"))
        marginal = _dict(metadata.get("marginal_value"))
        value = _optional_float(marginal.get("marginal_value"))
    if value is None:
        return None
    return value > 0


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


def _first_present(*values: object) -> object | None:
    for value in values:
        if value is not None:
            return value
    return None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
