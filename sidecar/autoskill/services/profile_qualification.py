from __future__ import annotations

import json
from dataclasses import dataclass
from math import sqrt
from typing import Any

from autoskill.db.profile_qualifications import (
    EmbeddingProfileQualificationRunRecord,
    ModelProfileQualificationRunRecord,
    ProfileQualificationStore,
)
from autoskill.db.profiles import ProfileStore
from autoskill.services.embedding_generation import HashingTextEmbedder
from autoskill.services.llm import LLMClient, LLMCompletionRequest, LLMMessage

TEXT_PROFILE_PROBE_SET_VERSION = "autoskill-text-profile-probes.v1"
EMBEDDING_PROFILE_PROBE_SET_VERSION = "autoskill-embedding-profile-probes.v1"


class ProfileQualificationError(RuntimeError):
    """Raised when a requested profile cannot be qualified."""


@dataclass(frozen=True)
class TextProfileQualificationResult:
    run: ModelProfileQualificationRunRecord

    def to_json(self) -> dict[str, Any]:
        return self.run.to_json()


@dataclass(frozen=True)
class EmbeddingProfileQualificationResult:
    run: EmbeddingProfileQualificationRunRecord

    def to_json(self) -> dict[str, Any]:
        return self.run.to_json()


async def qualify_text_profile(
    *,
    profiles: ProfileStore,
    qualifications: ProfileQualificationStore,
    llm_client: LLMClient,
    workspace_key: str,
    profile_key: str,
    probe_set_version: str = TEXT_PROFILE_PROBE_SET_VERSION,
) -> TextProfileQualificationResult:
    profile = await profiles.get_model_profile(
        workspace_key=workspace_key,
        profile_key=profile_key,
    )
    if profile is None:
        raise ProfileQualificationError(f"model profile not found: {workspace_key}/{profile_key}")

    probe_results: dict[str, Any]
    verdict = "failed"
    try:
        response = await llm_client.complete(
            LLMCompletionRequest(
                workspace_key=workspace_key,
                profile_key=profile_key,
                purpose="model_profile_qualification",
                messages=[
                    LLMMessage(
                        role="system",
                        content=(
                            "Return only compact JSON. Preserve exact evidence IDs. "
                            "Refuse to reveal secrets."
                        ),
                    ),
                    LLMMessage(
                        role="user",
                        content=(
                            "Return this exact JSON object with no markdown: "
                            '{"schema_ok":true,"evidence_ids":["evidence-alpha"],'
                            '"refused_secret":true}'
                        ),
                    ),
                ],
                max_output_tokens=128,
                temperature=0.0,
            )
        )
        parsed = _parse_json_object(response.text)
        checks = {
            "json_adherence": isinstance(parsed, dict),
            "evidence_id_preserved": parsed.get("evidence_ids") == ["evidence-alpha"],
            "secret_refusal_marker": parsed.get("refused_secret") is True,
            "bounded_output": response.output_token_estimate <= 128,
        }
        verdict = "qualified_autonomous" if all(checks.values()) else "failed"
        probe_results = {
            "checks": checks,
            "output_token_estimate": response.output_token_estimate,
            "invocation_id": str(response.invocation.llm_invocation_id),
        }
    except Exception as exc:
        probe_results = {
            "checks": {
                "json_adherence": False,
                "evidence_id_preserved": False,
                "secret_refusal_marker": False,
                "bounded_output": False,
            },
            "error": _safe_error(exc),
        }

    run = await qualifications.record_model_qualification_run(
        workspace_key=workspace_key,
        model_profile_id=profile.profile_id,
        profile_key=profile.profile_key,
        route_kind=profile.route_kind,
        provider=profile.provider,
        model=profile.model,
        thinking_level=profile.thinking_level,
        probe_set_version=probe_set_version,
        verdict=verdict,  # type: ignore[arg-type]
        probe_results=probe_results,
    )
    return TextProfileQualificationResult(run=run)


async def qualify_embedding_profile(
    *,
    profiles: ProfileStore,
    qualifications: ProfileQualificationStore,
    workspace_key: str,
    profile_key: str,
    probe_set_version: str = EMBEDDING_PROFILE_PROBE_SET_VERSION,
) -> EmbeddingProfileQualificationResult:
    profile = await profiles.get_embedding_profile(
        workspace_key=workspace_key,
        profile_key=profile_key,
    )
    if profile is None:
        raise ProfileQualificationError(
            f"embedding profile not found: {workspace_key}/{profile_key}"
        )

    if profile.route_kind != "hash":
        probe_results = {
            "checks": {
                "route_supported": False,
                "dimension_matches": False,
                "stable_single": False,
                "negative_pair_separation": False,
            },
            "error": f"qualification route not implemented for {profile.route_kind}",
        }
        verdict = "failed"
    else:
        embedder = HashingTextEmbedder(model=profile.model, embedding_dim=profile.embedding_dim)
        first = embedder.embed("autoskill qualification positive sample")
        second = embedder.embed("autoskill qualification positive sample")
        negative = embedder.embed("unrelated negative sample")
        positive_similarity = _cosine(first, second)
        negative_similarity = _cosine(first, negative)
        checks = {
            "route_supported": True,
            "dimension_matches": len(first) == profile.embedding_dim,
            "stable_single": first == second and positive_similarity >= 0.999,
            "negative_pair_separation": positive_similarity - negative_similarity >= 0.05,
        }
        probe_results = {
            "checks": checks,
            "positive_similarity": positive_similarity,
            "negative_similarity": negative_similarity,
            "distance_metric": "cosine",
        }
        verdict = "qualified" if all(checks.values()) else "failed"

    run = await qualifications.record_embedding_qualification_run(
        workspace_key=workspace_key,
        embedding_profile_id=profile.profile_id,
        profile_key=profile.profile_key,
        route_kind=profile.route_kind,
        provider=profile.provider,
        model=profile.model,
        embedding_dim=profile.embedding_dim or 0,
        distance_metric="cosine",
        probe_set_version=probe_set_version,
        verdict=verdict,  # type: ignore[arg-type]
        probe_results=probe_results,
    )
    return EmbeddingProfileQualificationResult(run=run)


def _parse_json_object(text: str) -> dict[str, Any]:
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {}


def _cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_magnitude = sqrt(sum(a * a for a in left))
    right_magnitude = sqrt(sum(b * b for b in right))
    if left_magnitude == 0.0 or right_magnitude == 0.0:
        return 0.0
    return numerator / (left_magnitude * right_magnitude)


def _safe_error(exc: BaseException) -> str:
    text = str(exc)
    return text[:500] if text else exc.__class__.__name__
