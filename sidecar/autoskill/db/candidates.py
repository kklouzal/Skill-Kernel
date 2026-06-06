from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from math import ceil
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.core.enums import CANDIDATE_REVIEW_LIFECYCLE_STATES, LifecycleState
from autoskill.core.hashing import sha256_text
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace
from autoskill.services.candidates import CandidateSkillProposal

DEFAULT_MAX_CONTEXT_TOKENS = 1200


@dataclass(frozen=True)
class PersistedCandidate:
    candidate_slug: str
    skill_id: UUID
    skill_version_id: UUID
    evolution_transaction_id: UUID | None
    version: int
    created: bool
    scanner_status: str
    evaluator_status: str
    probe_hashes: list[str]
    evaluation_status: str

    def to_json(self) -> dict[str, object]:
        return {
            "candidate_slug": self.candidate_slug,
            "skill_id": str(self.skill_id),
            "skill_version_id": str(self.skill_version_id),
            "evolution_transaction_id": (
                str(self.evolution_transaction_id) if self.evolution_transaction_id else None
            ),
            "version": self.version,
            "created": self.created,
            "scanner_status": self.scanner_status,
            "evaluator_status": self.evaluator_status,
            "probe_hashes": self.probe_hashes,
            "evaluation_status": self.evaluation_status,
        }


@dataclass(frozen=True)
class CandidatePersistResult:
    persisted: int
    skipped: int
    candidates: list[PersistedCandidate]
    evolution_transaction_id: UUID | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "persisted": self.persisted,
            "skipped": self.skipped,
            "evolution_transaction_id": (
                str(self.evolution_transaction_id) if self.evolution_transaction_id else None
            ),
            "candidates": [candidate.to_json() for candidate in self.candidates],
        }


@dataclass(frozen=True)
class CandidateReviewRecord:
    workspace_id: UUID | None
    workspace_key: str | None
    skill_id: UUID
    skill_version_id: UUID
    slug: str
    name: str
    lifecycle_state: str
    version: int
    scanner_status: str
    evaluator_status: str
    latest_evaluation_status: str | None
    created_by_transaction_id: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> CandidateReviewRecord:
        return cls(
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            skill_id=row["skill_id"],
            skill_version_id=row["skill_version_id"],
            slug=row["slug"],
            name=row["name"],
            lifecycle_state=row["lifecycle_state"],
            version=int(row["version"]),
            scanner_status=row["scanner_status"],
            evaluator_status=row["evaluator_status"],
            latest_evaluation_status=_row_get(row, "latest_evaluation_status"),
            created_by_transaction_id=_row_get(row, "created_by_transaction_id"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_json(self) -> dict[str, object]:
        return {
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "skill_id": str(self.skill_id),
            "skill_version_id": str(self.skill_version_id),
            "slug": self.slug,
            "name": self.name,
            "lifecycle_state": self.lifecycle_state,
            "version": self.version,
            "scanner_status": self.scanner_status,
            "evaluator_status": self.evaluator_status,
            "latest_evaluation_status": self.latest_evaluation_status,
            "created_by_transaction_id": (
                str(self.created_by_transaction_id)
                if self.created_by_transaction_id
                else None
            ),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class CandidateStore(Protocol):
    async def persist_candidate_proposals(
        self,
        *,
        workspace_key: str,
        proposals: list[CandidateSkillProposal],
        evolution_transaction_id: UUID | None = None,
    ) -> CandidatePersistResult:
        """Persist inactive candidate SkillIR revisions and planned probes."""

    async def list_candidate_reviews(
        self,
        *,
        workspace_key: str | None = None,
        lifecycle_state: str | None = LifecycleState.LEGACY_CANDIDATE.value,
        limit: int = 100,
    ) -> list[CandidateReviewRecord]:
        """List proposal candidate revisions for operator review."""


class NullCandidateStore:
    def __init__(self) -> None:
        self.reviews: list[CandidateReviewRecord] = []

    async def persist_candidate_proposals(
        self,
        *,
        workspace_key: str,
        proposals: list[CandidateSkillProposal],
        evolution_transaction_id: UUID | None = None,
    ) -> CandidatePersistResult:
        return CandidatePersistResult(
            persisted=0,
            skipped=sum(1 for proposal in proposals if proposal.skillir is None),
            candidates=[],
            evolution_transaction_id=evolution_transaction_id,
        )

    async def list_candidate_reviews(
        self,
        *,
        workspace_key: str | None = None,
        lifecycle_state: str | None = LifecycleState.LEGACY_CANDIDATE.value,
        limit: int = 100,
    ) -> list[CandidateReviewRecord]:
        reviews = self.reviews
        if workspace_key is not None:
            reviews = [review for review in reviews if review.workspace_key == workspace_key]
        if lifecycle_state is not None:
            lifecycle_states = set(_candidate_lifecycle_filter(lifecycle_state) or ())
            reviews = [
                review for review in reviews if review.lifecycle_state in lifecycle_states
            ]
        return reviews[: max(1, min(limit, 250))]


class AsyncpgCandidateStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def persist_candidate_proposals(
        self,
        *,
        workspace_key: str,
        proposals: list[CandidateSkillProposal],
        evolution_transaction_id: UUID | None = None,
    ) -> CandidatePersistResult:
        pool = await self._get_pool()
        persisted: list[PersistedCandidate] = []
        skipped = 0
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            for proposal in proposals:
                if proposal.skillir is None or proposal.compiled_runtime_text is None:
                    skipped += 1
                    continue
                persisted.append(
                    await _persist_candidate(
                        conn,
                        workspace_id,
                        proposal,
                        evolution_transaction_id=evolution_transaction_id,
                    )
                )

        return CandidatePersistResult(
            persisted=len(persisted),
            skipped=skipped,
            candidates=persisted,
            evolution_transaction_id=evolution_transaction_id,
        )

    async def list_candidate_reviews(
        self,
        *,
        workspace_key: str | None = None,
        lifecycle_state: str | None = LifecycleState.LEGACY_CANDIDATE.value,
        limit: int = 100,
    ) -> list[CandidateReviewRecord]:
        pool = await self._get_pool()
        lifecycle_states = _candidate_lifecycle_filter(lifecycle_state)
        rows = await pool.fetch(
            """
            SELECT
              w.workspace_id,
              w.external_key AS workspace_key,
              s.skill_id,
              sv.skill_version_id,
              s.slug,
              s.name,
              s.lifecycle_state,
              sv.version,
              sv.scanner_status,
              sv.evaluator_status,
              latest_ev.status AS latest_evaluation_status,
              sv.created_by_transaction_id,
              sv.created_at,
              s.updated_at
            FROM autoskill.skill_versions sv
            JOIN autoskill.skills s USING (skill_id)
            JOIN autoskill.workspaces w USING (workspace_id)
            LEFT JOIN LATERAL (
              SELECT ev.status
              FROM autoskill.evaluations ev
              WHERE ev.skill_version_id = sv.skill_version_id
              ORDER BY ev.created_at DESC, ev.evaluation_id DESC
              LIMIT 1
            ) latest_ev ON true
            WHERE ($1::text IS NULL OR w.external_key = $1)
              AND ($2::text[] IS NULL OR s.lifecycle_state = ANY($2::text[]))
            ORDER BY s.updated_at DESC, sv.created_at DESC, sv.skill_version_id DESC
            LIMIT $3
            """,
            workspace_key,
            lifecycle_states,
            max(1, min(limit, 250)),
        )
        return [CandidateReviewRecord.from_row(row) for row in rows]


async def _persist_candidate(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    proposal: CandidateSkillProposal,
    *,
    evolution_transaction_id: UUID | None = None,
) -> PersistedCandidate:
    assert proposal.skillir is not None
    assert proposal.compiled_runtime_text is not None

    skill = proposal.skillir
    skill_row = await conn.fetchrow(
        """
        INSERT INTO autoskill.skills (
          skill_id, workspace_id, slug, name, source, lifecycle_state
        )
        VALUES ($1, $2, $3, $4, 'autoskill', 'ephemeral_candidate')
        ON CONFLICT (workspace_id, slug) DO UPDATE
        SET updated_at = now()
        RETURNING skill_id
        """,
        skill.skill_id,
        workspace_id,
        skill.slug,
        skill.name,
    )
    skill_id = skill_row["skill_id"]
    skill_payload = skill.model_copy(update={"skill_id": skill_id}).model_dump(
        by_alias=True,
        mode="json",
    )

    existing = await conn.fetchrow(
        """
        SELECT skill_version_id, version, scanner_status, evaluator_status
        FROM autoskill.skill_versions
        WHERE skill_id = $1 AND compiled_sha256 = $2
        ORDER BY version DESC
        LIMIT 1
        """,
        skill_id,
        proposal.compiled_sha256,
    )
    if existing is None:
        version = await conn.fetchval(
            """
            SELECT COALESCE(max(version), 0) + 1
            FROM autoskill.skill_versions
            WHERE skill_id = $1
            """,
            skill_id,
        )
        scanner_status = _scanner_status(proposal)
        evaluator_status = "pending"
        version_row = await conn.fetchrow(
            """
            INSERT INTO autoskill.skill_versions (
              skill_version_id,
              skill_id,
              version,
              skill_ir,
              compiled_sha256,
              manifest,
              scanner_status,
              evaluator_status,
              created_by_transaction_id
            )
            VALUES (gen_random_uuid(), $1, $2, $3::jsonb, $4, $5::jsonb, $6, $7, $8)
            RETURNING
              skill_version_id,
              version,
              scanner_status,
              evaluator_status,
              created_by_transaction_id
            """,
            skill_id,
            version,
            _json(skill_payload),
            proposal.compiled_sha256,
            _json(
                {
                    "proposal": {
                        "recommendation": proposal.recommendation,
                        "evidence_ids": proposal.evidence_ids,
                        "scanner_findings": proposal.scanner_findings,
                        "metadata": proposal.metadata,
                    }
                }
            ),
            scanner_status,
            evaluator_status,
            evolution_transaction_id,
        )
        created = True
    else:
        version_row = existing
        created = False

    skill_version_id = version_row["skill_version_id"]
    scanner_status = version_row["scanner_status"]
    evaluator_status = version_row["evaluator_status"]
    await _persist_candidate_artifacts(
        conn,
        workspace_id=workspace_id,
        skill_id=skill_id,
        skill_version_id=skill_version_id,
        proposal=proposal,
        skill_payload=skill_payload,
        scanner_status=scanner_status,
    )
    await _persist_evidence_provenance(conn, workspace_id, skill_version_id, proposal)
    probe_hashes = await _persist_probe_plan(conn, workspace_id, skill_version_id, proposal)
    evaluation_status = await _persist_evaluation_gate(
        conn,
        workspace_id=workspace_id,
        skill_version_id=skill_version_id,
        proposal=proposal,
        probe_hashes=probe_hashes,
        scanner_status=scanner_status,
    )
    if evolution_transaction_id is not None:
        await _persist_transaction_items(
            conn,
            evolution_transaction_id=evolution_transaction_id,
            skill_version_id=skill_version_id,
            proposal=proposal,
        )
    return PersistedCandidate(
        candidate_slug=proposal.candidate_slug,
        skill_id=skill_id,
        skill_version_id=skill_version_id,
        evolution_transaction_id=evolution_transaction_id,
        version=version_row["version"],
        created=created,
        scanner_status=scanner_status,
        evaluator_status=evaluator_status,
        probe_hashes=probe_hashes,
        evaluation_status=evaluation_status,
    )


async def _persist_transaction_items(
    conn: asyncpg.Connection,
    *,
    evolution_transaction_id: UUID,
    skill_version_id: UUID,
    proposal: CandidateSkillProposal,
) -> None:
    skill_path = f"skills/autoskill/{proposal.candidate_slug}/SKILL.md"
    rollback_action = {
        "delete_inactive_candidate_version": str(skill_version_id),
        "delete_compiled_file_path": skill_path,
    }
    if proposal.metadata.get("rollback_action"):
        rollback_action["proposal_rollback_action"] = proposal.metadata["rollback_action"]
    await _insert_transaction_item_once(
        conn,
        evolution_transaction_id=evolution_transaction_id,
        item_kind="skill_version",
        item_id=skill_version_id,
        relative_path=None,
        before_hash=None,
        after_hash=proposal.compiled_sha256,
        activation_state=LifecycleState.EPHEMERAL_CANDIDATE.value,
        rollback_action=rollback_action,
    )
    await _insert_transaction_item_once(
        conn,
        evolution_transaction_id=evolution_transaction_id,
        item_kind="compiled_skill_file",
        item_id=skill_version_id,
        relative_path=skill_path,
        before_hash=None,
        after_hash=proposal.compiled_sha256,
        activation_state="inactive",
        rollback_action=rollback_action,
    )


async def _insert_transaction_item_once(
    conn: asyncpg.Connection,
    *,
    evolution_transaction_id: UUID,
    item_kind: str,
    item_id: UUID,
    relative_path: str | None,
    before_hash: str | None,
    after_hash: str | None,
    activation_state: str,
    rollback_action: dict[str, Any],
) -> None:
    await conn.execute(
        """
        INSERT INTO autoskill.evolution_transaction_items (
          transaction_item_id,
          evolution_transaction_id,
          item_kind,
          item_id,
          relative_path,
          before_hash,
          after_hash,
          activation_state,
          rollback_action
        )
        SELECT gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8::jsonb
        WHERE NOT EXISTS (
          SELECT 1
          FROM autoskill.evolution_transaction_items
          WHERE evolution_transaction_id = $1
            AND item_kind = $2
            AND item_id = $3
            AND relative_path IS NOT DISTINCT FROM $4
            AND after_hash IS NOT DISTINCT FROM $6
        )
        """,
        evolution_transaction_id,
        item_kind,
        item_id,
        relative_path,
        before_hash,
        after_hash,
        activation_state,
        _json(rollback_action),
    )


async def _persist_candidate_artifacts(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    skill_id: UUID,
    skill_version_id: UUID,
    proposal: CandidateSkillProposal,
    skill_payload: dict[str, Any],
    scanner_status: str,
) -> None:
    runtime_text = proposal.compiled_runtime_text or ""
    await conn.execute(
        """
        INSERT INTO autoskill.compiled_files (
          compiled_file_id,
          skill_version_id,
          path,
          sha256,
          bytes,
          renderer_version,
          active
        )
        SELECT gen_random_uuid(), $1, $2, $3, $4, 'autoskill-compiler.v1', false
        WHERE NOT EXISTS (
          SELECT 1
          FROM autoskill.compiled_files
          WHERE skill_version_id = $1
            AND path = $2
            AND sha256 = $3
        )
        """,
        skill_version_id,
        f"skills/autoskill/{proposal.candidate_slug}/SKILL.md",
        proposal.compiled_sha256,
        len(runtime_text.encode("utf-8")),
    )
    docs = [
        ("skillir", _json(skill_payload)),
        ("runtime", runtime_text),
    ]
    for kind, content in docs:
        await conn.execute(
            """
            INSERT INTO autoskill.body_index_documents (
              body_index_document_id,
              workspace_id,
              skill_id,
              skill_version_id,
              document_kind,
              text_hash,
              text_content,
              secret_scan_status,
              taint
            )
            VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, '{}')
            ON CONFLICT DO NOTHING
            """,
            workspace_id,
            skill_id,
            skill_version_id,
            kind,
            sha256_text(content),
            content,
            "passed" if scanner_status == "passed" else "blocked",
        )
    await _persist_context_artifact(
        conn,
        workspace_id=workspace_id,
        skill_id=skill_id,
        skill_version_id=skill_version_id,
        proposal=proposal,
        scanner_status=scanner_status,
    )


async def _persist_context_artifact(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    skill_id: UUID,
    skill_version_id: UUID,
    proposal: CandidateSkillProposal,
    scanner_status: str,
) -> None:
    runtime_text = proposal.compiled_runtime_text or ""
    token_count = _estimate_tokens(runtime_text)
    budget_status = (
        "passed" if token_count <= DEFAULT_MAX_CONTEXT_TOKENS else "over_budget"
    )
    safety_status = "passed" if scanner_status == "passed" else "blocked"
    await conn.execute(
        """
        INSERT INTO autoskill.context_artifacts (
          context_artifact_id,
          workspace_id,
          artifact_kind,
          source_object_type,
          source_object_id,
          skill_id,
          skill_version_id,
          text_hash,
          token_count,
          max_tokens,
          safety_status,
          equivalence_status,
          budget_status,
          shadowing_status,
          metadata
        )
        VALUES (
          gen_random_uuid(),
          $1,
          'skill_md',
          'skill_version',
          $2,
          $3,
          $2,
          $4,
          $5,
          $6,
          $7,
          'passed',
          $8,
          'pending',
          $9::jsonb
        )
        ON CONFLICT (
          workspace_id,
          artifact_kind,
          source_object_type,
          source_object_id,
          text_hash
        )
        DO UPDATE SET
          token_count = EXCLUDED.token_count,
          max_tokens = EXCLUDED.max_tokens,
          safety_status = EXCLUDED.safety_status,
          equivalence_status = EXCLUDED.equivalence_status,
          budget_status = EXCLUDED.budget_status,
          shadowing_status = EXCLUDED.shadowing_status,
          metadata = EXCLUDED.metadata
        """,
        workspace_id,
        skill_version_id,
        skill_id,
        proposal.compiled_sha256,
        token_count,
        DEFAULT_MAX_CONTEXT_TOKENS,
        safety_status,
        budget_status,
        _json(
            {
                "loadability_class": "runtime_skill_body",
                "compiler": "autoskill-compiler.v1",
                "candidate_slug": proposal.candidate_slug,
                "scanner_status": scanner_status,
                "proposal_metadata": proposal.metadata,
                "source": "candidate_persistence",
            }
        ),
    )


async def _persist_probe_plan(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    skill_version_id: UUID,
    proposal: CandidateSkillProposal,
) -> list[str]:
    probe_hashes: list[str] = []
    for probe in proposal.probe_plan:
        probe_hashes.append(probe.probe_hash)
        spec = {
            **probe.spec,
            "skill_version_id": str(skill_version_id),
            "candidate_slug": proposal.candidate_slug,
        }
        await conn.execute(
            """
            INSERT INTO autoskill.probes (
              probe_id, workspace_id, probe_hash, kind, maturity, spec, expected, active
            )
            VALUES (gen_random_uuid(), $1, $2, $3, $4, $5::jsonb, $6::jsonb, false)
            ON CONFLICT (workspace_id, probe_hash) DO NOTHING
            """,
            workspace_id,
            probe.probe_hash,
            probe.kind,
            probe.maturity,
            _json(spec),
            _json(probe.expected),
        )
    return probe_hashes


async def _persist_evidence_provenance(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    skill_version_id: UUID,
    proposal: CandidateSkillProposal,
) -> None:
    for evidence_id in proposal.evidence_ids:
        try:
            source_id = UUID(evidence_id)
        except ValueError:
            continue
        await conn.execute(
            """
            INSERT INTO autoskill.provenance_edges (
              provenance_edge_id,
              workspace_id,
              source_kind,
              source_id,
              derived_kind,
              derived_id,
              relation
            )
            SELECT
              gen_random_uuid(), $1, 'evidence_item', $2, 'skill_version', $3, 'proposed_from'
            WHERE NOT EXISTS (
              SELECT 1
              FROM autoskill.provenance_edges
              WHERE workspace_id = $1
                AND source_kind = 'evidence_item'
                AND source_id = $2
                AND derived_kind = 'skill_version'
                AND derived_id = $3
                AND relation = 'proposed_from'
            )
            """,
            workspace_id,
            source_id,
            skill_version_id,
        )


async def _persist_evaluation_gate(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    skill_version_id: UUID,
    proposal: CandidateSkillProposal,
    probe_hashes: list[str],
    scanner_status: str,
) -> str:
    status = "blocked" if scanner_status != "passed" else "planned"
    await conn.execute(
        """
        INSERT INTO autoskill.evaluations (
          evaluation_id,
          workspace_id,
          skill_version_id,
          category,
          status,
          result
        )
        SELECT gen_random_uuid(), $1, $2, 'proposal_gate', $3, $4::jsonb
        WHERE NOT EXISTS (
          SELECT 1
          FROM autoskill.evaluations
          WHERE workspace_id = $1
            AND skill_version_id = $2
            AND category = 'proposal_gate'
        )
        """,
        workspace_id,
        skill_version_id,
        status,
        _json(
            {
                "candidate_slug": proposal.candidate_slug,
                "required_gates": ["target", "no_skill_control", "regression", "adversarial"],
                "probe_hashes": probe_hashes,
                "scanner_status": scanner_status,
                "proposal_metadata": proposal.metadata,
            }
        ),
    )
    return status


def _scanner_status(proposal: CandidateSkillProposal) -> str:
    blocking = any(
        finding["severity"] in {"error", "critical"}
        for finding in proposal.scanner_findings
    )
    return "blocked" if blocking else "passed"


def _candidate_lifecycle_filter(lifecycle_state: str | None) -> list[str] | None:
    if lifecycle_state is None:
        return None
    if lifecycle_state == LifecycleState.LEGACY_CANDIDATE.value:
        return list(CANDIDATE_REVIEW_LIFECYCLE_STATES)
    return [lifecycle_state]


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None


def _estimate_tokens(text: str) -> int:
    return max(1, ceil(len(text) / 4))
