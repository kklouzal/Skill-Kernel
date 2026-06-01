from __future__ import annotations

from dataclasses import dataclass

from autoskill.db.retrieval import RetrievalCandidate, RetrievalStore


@dataclass(frozen=True)
class SkillMatchRequest:
    workspace_key: str
    candidate_slug: str
    candidate_description: str
    candidate_runtime_text: str = ""
    limit: int = 10


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
class SkillMatchResult:
    decision: str
    retrieval_log_id: str | None
    active_matches: list[SkillMatch]
    archived_matches: list[SkillMatch]

    def to_json(self) -> dict[str, object]:
        return {
            "decision": self.decision,
            "retrieval_log_id": self.retrieval_log_id,
            "active_matches": [match.to_json() for match in self.active_matches],
            "archived_matches": [match.to_json() for match in self.archived_matches],
        }


async def match_existing_skills(
    retrieval: RetrievalStore,
    request: SkillMatchRequest,
) -> SkillMatchResult:
    query = _query_text(request)
    result = await retrieval.lexical_query(
        workspace_key=request.workspace_key,
        query=query,
        limit=max(1, min(request.limit, 50)),
    )
    active: list[SkillMatch] = []
    archived: list[SkillMatch] = []
    seen: set[str] = set()
    query_terms = _terms(query)
    for candidate in result.candidates:
        if candidate.object_type != "body_index_document" or candidate.skill_id is None:
            continue
        skill_key = str(candidate.skill_id)
        if skill_key in seen:
            continue
        seen.add(skill_key)
        score = _score(candidate, query_terms, request.candidate_slug)
        match = SkillMatch.from_candidate(candidate, score)
        if match.lifecycle_state == "archived":
            archived.append(match)
        elif match.lifecycle_state in {"active", "candidate"}:
            active.append(match)

    active.sort(key=lambda match: match.score, reverse=True)
    archived.sort(key=lambda match: match.score, reverse=True)
    decision = _decision(active, archived)
    return SkillMatchResult(
        decision=decision,
        retrieval_log_id=str(result.retrieval_log_id) if result.retrieval_log_id else None,
        active_matches=active,
        archived_matches=archived,
    )


def _query_text(request: SkillMatchRequest) -> str:
    query = " ".join(
        part.strip()
        for part in (
            request.candidate_description,
            request.candidate_runtime_text,
        )
        if part.strip()
    )
    return query or request.candidate_slug.replace("-", " ")


def _score(candidate: RetrievalCandidate, query_terms: set[str], slug: str) -> float:
    candidate_terms = _terms(candidate.summary)
    overlap = len(query_terms & candidate_terms)
    slug_bonus = 0.25 if candidate.metadata.get("slug") == slug else 0.0
    return candidate.rank + (overlap * 0.1) + slug_bonus


def _decision(active: list[SkillMatch], archived: list[SkillMatch]) -> str:
    if active and active[0].score >= 0.45:
        return "reuse_active"
    if archived and archived[0].score >= 0.45:
        return "consider_archive_promotion"
    return "create_candidate"


def _terms(text: str) -> set[str]:
    return {term for term in text.lower().replace("-", " ").split() if len(term) > 2}
