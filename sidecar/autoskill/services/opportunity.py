from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from autoskill.db.evidence import EvidenceRecord, EvidenceStore
from autoskill.db.retrieval import RetrievalStore
from autoskill.services.matching import (
    SkillMatchRequest,
    SkillMatchResult,
    match_existing_skills,
)


@dataclass(frozen=True)
class OpportunityCandidate:
    key: str
    evidence_ids: list[str]
    support_count: int
    candidate_slug: str
    candidate_description: str
    match: SkillMatchResult

    @property
    def recommendation(self) -> str:
        if self.match.decision == "reuse_active":
            return "reuse_active"
        if self.match.decision == "consider_archive_promotion":
            return "promote_archived"
        if self.match.decision == "external_collision_review":
            return "review_external_collision"
        return "propose_candidate"

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "evidence_ids": self.evidence_ids,
            "support_count": self.support_count,
            "candidate_slug": self.candidate_slug,
            "candidate_description": self.candidate_description,
            "recommendation": self.recommendation,
            "match": self.match.to_json(),
        }


@dataclass(frozen=True)
class OpportunityMineResult:
    scanned: int
    candidates: list[OpportunityCandidate]

    def to_json(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "candidates": [candidate.to_json() for candidate in self.candidates],
        }


async def mine_opportunities(
    evidence_store: EvidenceStore,
    retrieval_store: RetrievalStore,
    *,
    workspace_key: str,
    limit: int = 100,
    min_support: int = 2,
) -> OpportunityMineResult:
    evidence = await evidence_store.list_evidence(workspace_key=workspace_key, limit=limit)
    grouped: dict[str, list[EvidenceRecord]] = defaultdict(list)
    for record in evidence:
        grouped[_opportunity_key(record)].append(record)

    candidates: list[OpportunityCandidate] = []
    for key, records in sorted(grouped.items()):
        support_count = _support_count(records)
        if support_count < min_support:
            continue
        slug = _candidate_slug(key)
        description = _candidate_description(key, records, support_count)
        match = await match_existing_skills(
            retrieval_store,
            SkillMatchRequest(
                workspace_key=workspace_key,
                candidate_slug=slug,
                candidate_description=description,
                limit=10,
            ),
        )
        candidates.append(
            OpportunityCandidate(
                key=key,
                evidence_ids=[str(record.evidence_id) for record in records],
                support_count=support_count,
                candidate_slug=slug,
                candidate_description=description,
                match=match,
            )
        )

    return OpportunityMineResult(scanned=len(evidence), candidates=candidates)


def _opportunity_key(record: EvidenceRecord) -> str:
    if record.kind == "recurring_evidence_cluster":
        signature = record.payload.get("signature")
        if signature:
            return str(signature).replace(":", "-")
    source = record.payload.get("source_event", {})
    event_type = str(source.get("event_type") or record.kind)
    payload = record.payload.get("redacted_payload", {})
    content = ""
    if isinstance(payload, dict):
        content = str(payload.get("content") or payload.get("message") or "")
    terms = [term for term in content.lower().replace("-", " ").split() if len(term) > 4]
    return "-".join([event_type, *terms[:3]]) if terms else event_type


def _candidate_slug(key: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in key.lower())
    collapsed = "-".join(part for part in cleaned.split("-") if part)
    return f"autoskill-{collapsed}"[:80].strip("-")


def _support_count(records: list[EvidenceRecord]) -> int:
    cluster_counts = [
        int(record.payload.get("support_count") or 0)
        for record in records
        if record.kind == "recurring_evidence_cluster"
    ]
    if cluster_counts:
        observed_count = sum(
            1 for record in records if record.kind != "recurring_evidence_cluster"
        )
        return max(observed_count, *cluster_counts)
    return len(records)


def _candidate_description(
    key: str,
    records: list[EvidenceRecord],
    support_count: int,
) -> str:
    parts = key.split("-")
    event_type = parts[0].replace("_", " ")
    trigger = " ".join(parts[1:]).strip()
    trigger_text = f" around {trigger}" if trigger else ""
    return (
        f"Repeated {event_type} workflow evidence{trigger_text} observed {support_count} times; "
        "derive a guarded procedural skill only if active and archived matches are insufficient."
    )
