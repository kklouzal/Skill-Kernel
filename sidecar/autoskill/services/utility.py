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

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> SkillUtilityFeatures:
        return cls(
            helped_count=max(0, int(values.get("helped_count", 0))),
            hurt_count=max(0, int(values.get("hurt_count", 0))),
            shadow_count=max(0, int(values.get("shadow_count", 0))),
            retrieval_count=max(0, int(values.get("retrieval_count", 0))),
            canary_failure_count=max(0, int(values.get("canary_failure_count", 0))),
        )

    def to_json(self) -> dict[str, int]:
        return {
            "helped_count": self.helped_count,
            "hurt_count": self.hurt_count,
            "shadow_count": self.shadow_count,
            "retrieval_count": self.retrieval_count,
            "canary_failure_count": self.canary_failure_count,
        }


def compute_utility_score(features: SkillUtilityFeatures) -> float:
    """Deterministic v1 utility score; marginal-value probes can replace weights later."""

    score = 0.0
    score += 2.0 * features.helped_count
    score += 0.15 * features.retrieval_count
    score -= 3.0 * features.hurt_count
    score -= 2.0 * features.shadow_count
    score -= 5.0 * features.canary_failure_count
    return round(score, 4)
