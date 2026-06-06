from __future__ import annotations

from dataclasses import dataclass

from autoskill.db.retrieval import RetrievalCandidate, RetrievalResult, RetrievalStore

MATCH_STOP_WORDS = {
    "active",
    "add",
    "and",
    "are",
    "archived",
    "around",
    "candidate",
    "derive",
    "evidence",
    "fix",
    "guarded",
    "insufficient",
    "matches",
    "observed",
    "only",
    "procedural",
    "repeated",
    "skill",
    "times",
    "with",
    "workflow",
}


@dataclass(frozen=True)
class SkillMatchRequest:
    workspace_key: str
    candidate_slug: str
    candidate_description: str
    candidate_runtime_text: str = ""
    limit: int = 10
    record_retrieval: bool = True


@dataclass(frozen=True)
class SkillMatch:
    skill_id: str
    object_id: str
    lifecycle_state: str
    slug: str | None
    score: float
    summary: str

    @classmethod
    def from_candidate(cls, candidate: RetrievalCandidate, score: float) -> SkillMatch:
        return cls(
            skill_id=str(candidate.skill_id),
            object_id=str(candidate.object_id),
            lifecycle_state=str(candidate.metadata.get("lifecycle_state", "unknown")),
            slug=(
                str(candidate.metadata["slug"])
                if candidate.metadata.get("slug") is not None
                else None
            ),
            score=score,
            summary=candidate.summary,
        )

    def to_json(self) -> dict[str, object]:
        return {
            "skill_id": self.skill_id,
            "object_id": self.object_id,
            "lifecycle_state": self.lifecycle_state,
            "slug": self.slug,
            "score": self.score,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class ExternalSkillMatch:
    external_skill_id: str
    source: str | None
    status: str
    slug: str | None
    score: float
    summary: str
    collision_risk: str
    collision_score: float
    recommendation: str
    reason_codes: list[str]

    @classmethod
    def from_candidate(
        cls,
        candidate: RetrievalCandidate,
        score: float,
        candidate_slug: str,
    ) -> ExternalSkillMatch:
        slug = (
            str(candidate.metadata["slug"])
            if candidate.metadata.get("slug") is not None
            else None
        )
        status = str(candidate.metadata.get("status", "unknown"))
        reason_codes = _external_collision_reason_codes(
            slug=slug,
            candidate_slug=candidate_slug,
            status=status,
            score=score,
            metadata=candidate.metadata,
        )
        collision_score = _external_collision_score(reason_codes, score)
        collision_risk = _external_collision_risk(collision_score, reason_codes)
        return cls(
            external_skill_id=str(candidate.object_id),
            source=(
                str(candidate.metadata["source"])
                if candidate.metadata.get("source") is not None
                else None
            ),
            status=status,
            slug=slug,
            score=score,
            summary=candidate.summary,
            collision_risk=collision_risk,
            collision_score=collision_score,
            recommendation=_external_collision_recommendation(
                collision_risk,
                status,
                reason_codes,
            ),
            reason_codes=reason_codes,
        )

    def to_json(self) -> dict[str, object]:
        return {
            "external_skill_id": self.external_skill_id,
            "source": self.source,
            "status": self.status,
            "slug": self.slug,
            "score": self.score,
            "summary": self.summary,
            "collision_risk": self.collision_risk,
            "collision_score": self.collision_score,
            "recommendation": self.recommendation,
            "reason_codes": self.reason_codes,
        }


@dataclass(frozen=True)
class SkillMatchResult:
    decision: str
    retrieval_log_id: str | None
    active_matches: list[SkillMatch]
    archived_matches: list[SkillMatch]
    external_matches: list[ExternalSkillMatch]

    def to_json(self) -> dict[str, object]:
        return {
            "decision": self.decision,
            "retrieval_log_id": self.retrieval_log_id,
            "active_matches": [match.to_json() for match in self.active_matches],
            "archived_matches": [match.to_json() for match in self.archived_matches],
            "external_matches": [match.to_json() for match in self.external_matches],
        }


async def match_existing_skills(
    retrieval: RetrievalStore,
    request: SkillMatchRequest,
) -> SkillMatchResult:
    query_results: list[tuple[str, RetrievalResult]] = []
    bounded_limit = max(1, min(request.limit, 50))
    for query in _query_variants(request):
        result = await retrieval.lexical_query(
            workspace_key=request.workspace_key,
            query=query,
            limit=bounded_limit,
            record_decision=request.record_retrieval,
        )
        query_results.append((query, result))
    if not query_results:
        query_results.append(
            (
                "",
                RetrievalResult(
                    retrieval_log_id=None,
                    decision="empty_query",
                    candidates=[],
                ),
            )
        )
    active_by_skill: dict[str, SkillMatch] = {}
    archived_by_skill: dict[str, SkillMatch] = {}
    external_by_id: dict[str, ExternalSkillMatch] = {}
    selected_retrieval_log_id: str | None = None
    fallback_retrieval_log_id: str | None = None
    for query, result in query_results:
        if result.retrieval_log_id:
            fallback_retrieval_log_id = str(result.retrieval_log_id)
            if result.candidates and selected_retrieval_log_id is None:
                selected_retrieval_log_id = str(result.retrieval_log_id)
        query_terms = _terms(query)
        for candidate in result.candidates:
            if candidate.object_type == "external_skill":
                external_match = ExternalSkillMatch.from_candidate(
                    candidate,
                    _score(candidate, query_terms, request.candidate_slug),
                    request.candidate_slug,
                )
                existing = external_by_id.get(external_match.external_skill_id)
                if existing is None or external_match.score > existing.score:
                    external_by_id[external_match.external_skill_id] = external_match
                continue
            if candidate.object_type != "body_index_document" or candidate.skill_id is None:
                continue
            skill_key = str(candidate.skill_id)
            score = _score(candidate, query_terms, request.candidate_slug)
            match = SkillMatch.from_candidate(candidate, score)
            if match.lifecycle_state == "archived":
                existing = archived_by_skill.get(skill_key)
                if existing is None or match.score > existing.score:
                    archived_by_skill[skill_key] = match
            elif match.lifecycle_state in {"active", "candidate"}:
                existing = active_by_skill.get(skill_key)
                if existing is None or match.score > existing.score:
                    active_by_skill[skill_key] = match

    active = list(active_by_skill.values())
    archived = list(archived_by_skill.values())
    external = list(external_by_id.values())
    active.sort(key=lambda match: match.score, reverse=True)
    archived.sort(key=lambda match: match.score, reverse=True)
    external.sort(key=lambda match: match.score, reverse=True)
    decision = _decision(active, archived, external)
    return SkillMatchResult(
        decision=decision,
        retrieval_log_id=selected_retrieval_log_id or fallback_retrieval_log_id,
        active_matches=active,
        archived_matches=archived,
        external_matches=external,
    )


def _query_text(request: SkillMatchRequest) -> str:
    return _query_from_parts(
        request,
        request.candidate_description,
        request.candidate_runtime_text,
    )


def _query_variants(request: SkillMatchRequest) -> list[str]:
    variants = [
        _query_text(request),
        _query_from_parts(request, request.candidate_runtime_text),
        _query_from_parts(request, request.candidate_description),
        _query_from_parts(request, request.candidate_slug.replace("-", " ")),
    ]
    deduped: list[str] = []
    for variant in variants:
        if variant and variant not in deduped:
            deduped.append(variant)
    return deduped


def _query_from_parts(request: SkillMatchRequest, *parts: str) -> str:
    raw_query = " ".join(part.strip() for part in parts if part.strip())
    terms = [
        term
        for term in _ordered_terms(raw_query)
        if term not in MATCH_STOP_WORDS
    ]
    if not terms:
        terms = _ordered_terms(request.candidate_slug.replace("-", " "))
    return " ".join(terms[:6])


def _score(candidate: RetrievalCandidate, query_terms: set[str], slug: str) -> float:
    candidate_terms = _terms(candidate.summary)
    overlap = len(query_terms & candidate_terms)
    slug_bonus = 0.25 if candidate.metadata.get("slug") == slug else 0.0
    return candidate.rank + (overlap * 0.1) + slug_bonus


def _decision(
    active: list[SkillMatch],
    archived: list[SkillMatch],
    external: list[ExternalSkillMatch],
) -> str:
    if active and active[0].score >= 0.45:
        return "reuse_active"
    if archived and archived[0].score >= 0.45:
        return "consider_archive_promotion"
    if external and external[0].score >= 0.45:
        return "external_collision_review"
    return "create_candidate"


def _external_collision_reason_codes(
    *,
    slug: str | None,
    candidate_slug: str,
    status: str,
    score: float,
    metadata: dict[str, object],
) -> list[str]:
    reasons: list[str] = []
    if slug == candidate_slug:
        reasons.append("exact_slug_collision")
    elif slug and _slug_overlap(slug, candidate_slug) >= 0.5:
        reasons.append("slug_family_overlap")
    if score >= 0.75:
        reasons.append("high_similarity")
    elif score >= 0.45:
        reasons.append("moderate_similarity")
    if status == "changed":
        reasons.append("external_skill_changed")
    if status == "visible":
        reasons.append("external_skill_visible")
    if status in {"ignored", "quarantined"}:
        reasons.append(f"external_skill_{status}")
    risk_summary = metadata.get("risk_summary")
    if isinstance(risk_summary, dict):
        scanner_status = str(risk_summary.get("scanner_status") or "")
        if scanner_status == "blocked":
            reasons.append("external_skill_scanner_blocked")
        if risk_summary.get("changed_since_review") is True:
            reasons.append("external_skill_changed_since_review")
        if risk_summary.get("stored_raw_root_path") is False:
            reasons.append("external_skill_path_safe")
    return reasons


def _external_collision_score(reason_codes: list[str], retrieval_score: float) -> float:
    score = min(max(retrieval_score, 0.0), 1.0)
    weights = {
        "exact_slug_collision": 0.35,
        "slug_family_overlap": 0.2,
        "high_similarity": 0.3,
        "moderate_similarity": 0.15,
        "external_skill_changed": 0.15,
        "external_skill_changed_since_review": 0.15,
        "external_skill_scanner_blocked": 0.25,
        "external_skill_quarantined": 0.25,
        "external_skill_ignored": -0.2,
        "external_skill_path_safe": -0.05,
    }
    for reason in reason_codes:
        score += weights.get(reason, 0.0)
    return round(min(max(score, 0.0), 1.0), 3)


def _external_collision_risk(collision_score: float, reason_codes: list[str]) -> str:
    if (
        "external_skill_scanner_blocked" in reason_codes
        or "external_skill_quarantined" in reason_codes
    ):
        return "blocked"
    if collision_score >= 0.75:
        return "high"
    if collision_score >= 0.45:
        return "medium"
    return "low"


def _external_collision_recommendation(
    collision_risk: str,
    status: str,
    reason_codes: list[str],
) -> str:
    if collision_risk == "blocked":
        return "do_not_import_external_skill_until_unquarantined"
    if "external_skill_changed_since_review" in reason_codes or status == "changed":
        return "review_changed_external_skill_before_candidate_creation"
    if collision_risk == "high":
        return "operator_review_import_or_reuse_external_skill"
    if collision_risk == "medium":
        return "review_external_collision_before_candidate_creation"
    return "record_external_overlap_signal"


def _terms(text: str) -> set[str]:
    return {term for term in text.lower().replace("-", " ").split() if len(term) > 2}


def _slug_overlap(left: str, right: str) -> float:
    left_terms = _terms(left)
    right_terms = _terms(right)
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / max(len(left_terms), len(right_terms))


def _ordered_terms(text: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for term in text.lower().replace("-", " ").split():
        cleaned = "".join(ch for ch in term if ch.isalnum())
        if len(cleaned) <= 2 or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return ordered
