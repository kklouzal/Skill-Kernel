from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SkillUtilityFeatures:
    helped_count: int = 0
    hurt_count: int = 0
    shadow_count: int = 0
    retrieval_count: int = 0
    canary_failure_count: int = 0
    marginal_value: float = 0.0
    context_value_per_token: float = 0.0
    ignored_load_count: int = 0
    false_positive_load_count: int = 0
    token_waste: int = 0

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> SkillUtilityFeatures:
        return cls(
            helped_count=max(0, int(values.get("helped_count", 0))),
            hurt_count=max(0, int(values.get("hurt_count", 0))),
            shadow_count=max(0, int(values.get("shadow_count", 0))),
            retrieval_count=max(0, int(values.get("retrieval_count", 0))),
            canary_failure_count=max(0, int(values.get("canary_failure_count", 0))),
            marginal_value=float(values.get("marginal_value", 0.0) or 0.0),
            context_value_per_token=float(
                values.get("context_value_per_token", 0.0) or 0.0
            ),
            ignored_load_count=max(0, int(values.get("ignored_load_count", 0))),
            false_positive_load_count=max(
                0,
                int(values.get("false_positive_load_count", 0)),
            ),
            token_waste=max(0, int(values.get("token_waste", 0))),
        )

    def to_json(self) -> dict[str, int | float]:
        return {
            "helped_count": self.helped_count,
            "hurt_count": self.hurt_count,
            "shadow_count": self.shadow_count,
            "retrieval_count": self.retrieval_count,
            "canary_failure_count": self.canary_failure_count,
            "marginal_value": round(self.marginal_value, 6),
            "context_value_per_token": round(self.context_value_per_token, 8),
            "ignored_load_count": self.ignored_load_count,
            "false_positive_load_count": self.false_positive_load_count,
            "token_waste": self.token_waste,
        }


def compute_utility_score(features: SkillUtilityFeatures) -> float:
    """Deterministic v1 utility score from outcomes and marginal context value."""

    score = 0.0
    score += 2.0 * features.helped_count
    score += 0.15 * features.retrieval_count
    score -= 3.0 * features.hurt_count
    score -= 2.0 * features.shadow_count
    score -= 5.0 * features.canary_failure_count
    score += 4.0 * features.marginal_value
    score += 25.0 * features.context_value_per_token
    score -= 0.5 * features.ignored_load_count
    score -= 1.0 * features.false_positive_load_count
    score -= min(5.0, features.token_waste / 400.0)
    return round(score, 4)
