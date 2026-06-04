from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

import asyncpg

from autoskill.core.hashing import sha256_json
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace
from autoskill.services.utility import SkillUtilityFeatures, compute_utility_score
from autoskill.services.writer import (
    archive_active_skill_and_remove,
    latest_archive_manifest_for_slug,
    rollback_active_skill,
)


@dataclass(frozen=True)
class SkillUtilityRollupRecord:
    skill_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    slug: str | None
    lifecycle_state: str | None
    utility_score: float
    features: SkillUtilityFeatures
    computed_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> SkillUtilityRollupRecord:
        features = SkillUtilityFeatures.from_mapping(_json_dict(row["features"]))
        return cls(
            skill_id=row["skill_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            slug=_row_get(row, "slug"),
            lifecycle_state=_row_get(row, "lifecycle_state"),
            utility_score=float(row["utility_score"]),
            features=features,
            computed_at=row["computed_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "skill_id": str(self.skill_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "slug": self.slug,
            "lifecycle_state": self.lifecycle_state,
            "utility_score": self.utility_score,
            "features": self.features.to_json(),
            "computed_at": self.computed_at.isoformat(),
        }


@dataclass(frozen=True)
class CurationActionRecord:
    curation_action_id: UUID
    skill_id: UUID | None
    action: str
    status: str
    reason: str
    features: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> CurationActionRecord:
        return cls(
            curation_action_id=row["curation_action_id"],
            skill_id=_row_get(row, "skill_id"),
            action=row["action"],
            status=row["status"],
            reason=row["reason"],
            features=_json_dict(row["features"]),
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "curation_action_id": str(self.curation_action_id),
            "skill_id": str(self.skill_id) if self.skill_id else None,
            "action": self.action,
            "status": self.status,
            "reason": self.reason,
            "features": self.features,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class UtilityRollupResult:
    scanned: int
    rollups: list[SkillUtilityRollupRecord]

    def to_json(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "rollups": [rollup.to_json() for rollup in self.rollups],
        }


@dataclass(frozen=True)
class CurationRunResult:
    scanned: int
    archived: int
    promoted: int
    merged: int
    planned: int
    actions: list[CurationActionRecord]

    def to_json(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "archived": self.archived,
            "promoted": self.promoted,
            "merged": self.merged,
            "planned": self.planned,
            "actions": [action.to_json() for action in self.actions],
        }


class UtilityStore(Protocol):
    async def run_utility_rollup(
        self,
        *,
        workspace_key: str,
        limit: int = 250,
    ) -> UtilityRollupResult:
        """Compute deterministic utility rollups for skills."""

    async def run_curation(
        self,
        *,
        workspace_key: str,
        archive_threshold: float = -1.0,
        max_archive: int = 5,
        promotion_min_retrieval: int = 3,
        max_promote: int = 3,
        active_budget: int | None = None,
        max_merge: int = 5,
    ) -> CurationRunResult:
        """Promote recurring archived skills, archive weak active skills, and merge duplicates."""

    async def claim_planned_repair_actions(
        self,
        *,
        workspace_key: str,
        limit: int = 25,
        worker_id: str | None = None,
        job_id: UUID | None = None,
    ) -> list[CurationActionRecord]:
        """Claim planned curation repair proposals for deterministic execution."""

    async def complete_repair_action_execution(
        self,
        *,
        workspace_key: str,
        curation_action_id: UUID,
        status: str,
        execution: dict[str, Any],
    ) -> CurationActionRecord | None:
        """Attach repair execution metadata to a claimed curation action."""


class NullUtilityStore:
    async def run_utility_rollup(
        self,
        *,
        workspace_key: str,
        limit: int = 250,
    ) -> UtilityRollupResult:
        return UtilityRollupResult(scanned=0, rollups=[])

    async def run_curation(
        self,
        *,
        workspace_key: str,
        archive_threshold: float = -1.0,
        max_archive: int = 5,
        promotion_min_retrieval: int = 3,
        max_promote: int = 3,
        active_budget: int | None = None,
        max_merge: int = 5,
    ) -> CurationRunResult:
        return CurationRunResult(scanned=0, archived=0, promoted=0, merged=0, planned=0, actions=[])

    async def claim_planned_repair_actions(
        self,
        *,
        workspace_key: str,
        limit: int = 25,
        worker_id: str | None = None,
        job_id: UUID | None = None,
    ) -> list[CurationActionRecord]:
        return []

    async def complete_repair_action_execution(
        self,
        *,
        workspace_key: str,
        curation_action_id: UUID,
        status: str,
        execution: dict[str, Any],
    ) -> CurationActionRecord | None:
        return None


class AsyncpgUtilityStore(AsyncpgPoolOwner):
    def __init__(
        self,
        database_url: str,
        *,
        statement_timeout_ms: int = 30_000,
        workspace_root: Path | None = None,
        archive_root: Path | None = None,
    ) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)
        self.workspace_root = workspace_root
        self.archive_root = archive_root

    def set_writer_roots(self, *, workspace_root: Path, archive_root: Path) -> None:
        self.workspace_root = workspace_root
        self.archive_root = archive_root

    async def run_utility_rollup(
        self,
        *,
        workspace_key: str,
        limit: int = 250,
    ) -> UtilityRollupResult:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            skills = await _load_skill_feature_rows(conn, workspace_id, limit)
            rollups: list[SkillUtilityRollupRecord] = []
            for row in skills:
                features = SkillUtilityFeatures.from_mapping(dict(row))
                score = compute_utility_score(features)
                rollup = await _upsert_rollup(
                    conn,
                    workspace_id=workspace_id,
                    workspace_key=workspace_key,
                    skill_id=row["skill_id"],
                    slug=row["slug"],
                    lifecycle_state=row["lifecycle_state"],
                    features=features,
                    utility_score=score,
                )
                rollups.append(rollup)
        return UtilityRollupResult(scanned=len(skills), rollups=rollups)

    async def run_curation(
        self,
        *,
        workspace_key: str,
        archive_threshold: float = -1.0,
        max_archive: int = 5,
        promotion_min_retrieval: int = 3,
        max_promote: int = 3,
        active_budget: int | None = None,
        max_merge: int = 5,
    ) -> CurationRunResult:
        rollups = await self.run_utility_rollup(workspace_key=workspace_key)
        pool = await self._get_pool()
        actions: list[CurationActionRecord] = []
        archived = 0
        promoted = 0
        merged = 0
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            rollup_by_skill = {rollup.skill_id: rollup for rollup in rollups.rollups}

            for rollup in sorted(
                rollups.rollups,
                key=lambda item: (item.utility_score, item.slug or ""),
                reverse=True,
            ):
                if promoted >= max_promote:
                    break
                if rollup.lifecycle_state != "archived":
                    continue
                if rollup.features.retrieval_count < promotion_min_retrieval:
                    continue
                if rollup.features.canary_failure_count or rollup.features.hurt_count:
                    continue
                if not await _latest_evaluator_passed(conn, rollup.skill_id):
                    actions.append(
                        await _insert_curation_action(
                            conn,
                            workspace_id=workspace_id,
                            skill_id=rollup.skill_id,
                            action="promote_archive",
                            status="blocked",
                            reason="archived promotion requires evaluator pass",
                            features={
                                **rollup.features.to_json(),
                                "utility_score": rollup.utility_score,
                                "promotion_min_retrieval": promotion_min_retrieval,
                            },
                        )
                    )
                    continue
                contract_gate = await _latest_contract_gate(conn, rollup.skill_id)
                if contract_gate["status"] != "passed":
                    actions.append(
                        await _insert_curation_action(
                            conn,
                            workspace_id=workspace_id,
                            skill_id=rollup.skill_id,
                            action="promote_archive",
                            status="blocked",
                            reason="archived promotion requires current contracts valid",
                            features={
                                **rollup.features.to_json(),
                                "utility_score": rollup.utility_score,
                                "promotion_min_retrieval": promotion_min_retrieval,
                                "contract_gate": contract_gate,
                            },
                        )
                    )
                    continue
                filesystem_promotion = _restore_archived_files_for_promotion(
                    workspace_root=self.workspace_root,
                    archive_root=self.archive_root,
                    slug=rollup.slug or "",
                )
                if filesystem_promotion["status"] == "blocked":
                    actions.append(
                        await _insert_curation_action(
                            conn,
                            workspace_id=workspace_id,
                            skill_id=rollup.skill_id,
                            action="promote_archive",
                            status="blocked",
                            reason="archived promotion requires restorable archive snapshot",
                            features={
                                **rollup.features.to_json(),
                                "utility_score": rollup.utility_score,
                                "promotion_min_retrieval": promotion_min_retrieval,
                                "filesystem_promotion": filesystem_promotion,
                            },
                        )
                    )
                    continue
                if await _set_lifecycle_state(
                    conn,
                    workspace_id,
                    rollup.skill_id,
                    from_state="archived",
                    to_state="active",
                ):
                    actions.append(
                        await _insert_curation_action(
                            conn,
                            workspace_id=workspace_id,
                            skill_id=rollup.skill_id,
                            action="promote_archive",
                            status="applied",
                            reason="archived skill demand recurred",
                            features={
                                **rollup.features.to_json(),
                                "utility_score": rollup.utility_score,
                                "promotion_min_retrieval": promotion_min_retrieval,
                                "filesystem_promotion": filesystem_promotion,
                            },
                        )
                    )
                    promoted += 1
                elif filesystem_promotion["status"] == "restored":
                    _archive_active_files_for_curation(
                        workspace_root=self.workspace_root,
                        archive_root=self.archive_root,
                        slug=rollup.slug or "",
                    )

            duplicate_actions = await _archive_duplicate_edges(
                conn,
                workspace_id=workspace_id,
                rollup_by_skill=rollup_by_skill,
                max_merge=min(max_merge, max_archive),
                workspace_root=self.workspace_root,
                archive_root=self.archive_root,
            )
            actions.extend(duplicate_actions)
            archived += len(duplicate_actions)
            merged += len(duplicate_actions)

            archive_actions = await _archive_low_utility(
                conn,
                workspace_id=workspace_id,
                rollups=rollups.rollups,
                archive_threshold=archive_threshold,
                max_archive=max(0, max_archive - archived),
                workspace_root=self.workspace_root,
                archive_root=self.archive_root,
            )
            actions.extend(archive_actions)
            archived += len(archive_actions)

            if active_budget is not None and active_budget > 0:
                budget_actions = await _enforce_active_budget(
                    conn,
                    workspace_id=workspace_id,
                    rollup_by_skill=rollup_by_skill,
                    active_budget=active_budget,
                    max_archive=max(0, max_archive - archived),
                    workspace_root=self.workspace_root,
                    archive_root=self.archive_root,
                )
                actions.extend(budget_actions)
                archived += len(budget_actions)
            planning_actions = await _plan_improvements_and_splits(
                conn,
                workspace_id=workspace_id,
                rollups=rollups.rollups,
                max_actions=max(0, max_archive + max_promote - len(actions)),
            )
            actions.extend(planning_actions)
        return CurationRunResult(
            scanned=rollups.scanned,
            archived=archived,
            promoted=promoted,
            merged=merged,
            planned=sum(1 for action in actions if action.status == "planned"),
            actions=actions,
        )

    async def claim_planned_repair_actions(
        self,
        *,
        workspace_key: str,
        limit: int = 25,
        worker_id: str | None = None,
        job_id: UUID | None = None,
    ) -> list[CurationActionRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                WITH candidate AS (
                  SELECT curation_action_id
                  FROM autoskill.curation_actions
                  WHERE workspace_id = $1
                    AND status = 'planned'
                    AND action = ANY($2::text[])
                    AND features ? 'repair_proposal'
                  ORDER BY created_at ASC
                  FOR UPDATE SKIP LOCKED
                  LIMIT $3
                )
                UPDATE autoskill.curation_actions ca
                SET status = 'executing',
                    created_by_job_id = COALESCE($4, created_by_job_id),
                    features = features || $5::jsonb
                FROM candidate
                WHERE ca.curation_action_id = candidate.curation_action_id
                RETURNING ca.*
                """,
                workspace_id,
                [
                    "plan_improvement",
                    "plan_disambiguation_repair",
                    "plan_split",
                ],
                max(1, min(limit, 100)),
                job_id,
                _json(
                    {
                        "repair_execution_claim": {
                            "worker_id": worker_id,
                            "job_id": str(job_id) if job_id else None,
                        }
                    }
                ),
            )
        return [CurationActionRecord.from_row(row) for row in rows]

    async def complete_repair_action_execution(
        self,
        *,
        workspace_key: str,
        curation_action_id: UUID,
        status: str,
        execution: dict[str, Any],
    ) -> CurationActionRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                UPDATE autoskill.curation_actions
                SET status = $3,
                    features = features || $4::jsonb
                WHERE workspace_id = $1
                  AND curation_action_id = $2
                RETURNING *
                """,
                workspace_id,
                curation_action_id,
                status,
                _json({"repair_execution": execution}),
            )
        return CurationActionRecord.from_row(row) if row is not None else None


async def _archive_low_utility(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    rollups: list[SkillUtilityRollupRecord],
    archive_threshold: float,
    max_archive: int,
    workspace_root: Path | None,
    archive_root: Path | None,
) -> list[CurationActionRecord]:
    actions: list[CurationActionRecord] = []
    for rollup in sorted(rollups, key=lambda item: (item.utility_score, item.slug or "")):
        if len(actions) >= max_archive:
            break
        if rollup.lifecycle_state != "active":
            continue
        if rollup.utility_score > archive_threshold:
            continue
        filesystem_archive = _archive_active_files_for_curation(
            workspace_root=workspace_root,
            archive_root=archive_root,
            slug=rollup.slug or "",
        )
        if filesystem_archive["status"] == "blocked":
            actions.append(
                await _insert_curation_action(
                    conn,
                    workspace_id=workspace_id,
                    skill_id=rollup.skill_id,
                    action="archive",
                    status="blocked",
                    reason="utility archive requires filesystem archive snapshot",
                    features={
                        **rollup.features.to_json(),
                        "utility_score": rollup.utility_score,
                        "archive_threshold": archive_threshold,
                        "filesystem_archive": filesystem_archive,
                    },
                )
            )
            continue
        if not await _set_lifecycle_state(
            conn,
            workspace_id,
            rollup.skill_id,
            from_state="active",
            to_state="archived",
        ):
            _restore_files_after_failed_archive(
                workspace_root=workspace_root,
                archive_root=archive_root,
                filesystem_archive=filesystem_archive,
            )
            continue
        actions.append(
            await _insert_curation_action(
                conn,
                workspace_id=workspace_id,
                skill_id=rollup.skill_id,
                action="archive",
                status="applied",
                reason="utility below archive threshold",
                features={
                    **rollup.features.to_json(),
                    "utility_score": rollup.utility_score,
                    "archive_threshold": archive_threshold,
                    "filesystem_archive": filesystem_archive,
                },
            )
        )
    return actions


async def _archive_duplicate_edges(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    rollup_by_skill: dict[UUID, SkillUtilityRollupRecord],
    max_merge: int,
    workspace_root: Path | None,
    archive_root: Path | None,
) -> list[CurationActionRecord]:
    if max_merge <= 0:
        return []
    rows = await conn.fetch(
        """
        SELECT
          e.from_skill_id,
          e.to_skill_id,
          from_skill.slug AS from_slug,
          to_skill.slug AS to_slug
        FROM autoskill.skill_edges e
        JOIN autoskill.skills from_skill
          ON from_skill.skill_id = e.from_skill_id
         AND from_skill.workspace_id = e.workspace_id
        JOIN autoskill.skills to_skill
          ON to_skill.skill_id = e.to_skill_id
         AND to_skill.workspace_id = e.workspace_id
        WHERE e.workspace_id = $1
          AND e.edge_kind IN ('duplicate', 'duplicate_of')
          AND e.revoked_at IS NULL
          AND from_skill.lifecycle_state = 'active'
          AND to_skill.lifecycle_state = 'active'
        ORDER BY from_skill.slug ASC, to_skill.slug ASC
        LIMIT $2
        """,
        workspace_id,
        max_merge * 3,
    )
    actions: list[CurationActionRecord] = []
    archived_skill_ids: set[UUID] = set()
    for row in rows:
        if len(actions) >= max_merge:
            break
        left = row["from_skill_id"]
        right = row["to_skill_id"]
        if left in archived_skill_ids or right in archived_skill_ids:
            continue
        if not await _latest_evaluator_passed(conn, left) or not await _latest_evaluator_passed(
            conn,
            right,
        ):
            actions.append(
                await _insert_curation_action(
                    conn,
                    workspace_id=workspace_id,
                    skill_id=None,
                    action="merge_duplicate",
                    status="blocked",
                    reason="duplicate merge requires evaluator pass for both skills",
                    features={
                        "from_skill_id": str(left),
                        "to_skill_id": str(right),
                        "from_slug": row["from_slug"],
                        "to_slug": row["to_slug"],
                        "merge_probe_plan": _merge_probe_plan(
                            from_skill_id=left,
                            to_skill_id=right,
                            from_slug=row["from_slug"],
                            to_slug=row["to_slug"],
                        ),
                    },
                )
            )
            continue
        left_rollup = rollup_by_skill.get(left)
        right_rollup = rollup_by_skill.get(right)
        left_score = left_rollup.utility_score if left_rollup else 0.0
        right_score = right_rollup.utility_score if right_rollup else 0.0
        if (left_score, row["from_slug"]) >= (right_score, row["to_slug"]):
            keep_id, keep_slug = left, row["from_slug"]
            archive_id, archive_slug, archive_rollup = right, row["to_slug"], right_rollup
        else:
            keep_id, keep_slug = right, row["to_slug"]
            archive_id, archive_slug, archive_rollup = left, row["from_slug"], left_rollup
        filesystem_archive = _archive_active_files_for_curation(
            workspace_root=workspace_root,
            archive_root=archive_root,
            slug=archive_slug,
        )
        if filesystem_archive["status"] == "blocked":
            actions.append(
                await _insert_curation_action(
                    conn,
                    workspace_id=workspace_id,
                    skill_id=archive_id,
                    action="merge_duplicate",
                    status="blocked",
                    reason="duplicate merge archive requires filesystem archive snapshot",
                    features={
                        "archived_slug": archive_slug,
                        "kept_skill_id": str(keep_id),
                        "kept_slug": keep_slug,
                        "filesystem_archive": filesystem_archive,
                        "merge_probe_plan": _merge_probe_plan(
                            from_skill_id=left,
                            to_skill_id=right,
                            from_slug=row["from_slug"],
                            to_slug=row["to_slug"],
                        ),
                    },
                )
            )
            continue
        if not await _set_lifecycle_state(
            conn,
            workspace_id,
            archive_id,
            from_state="active",
            to_state="archived",
        ):
            _restore_files_after_failed_archive(
                workspace_root=workspace_root,
                archive_root=archive_root,
                filesystem_archive=filesystem_archive,
            )
            continue
        archived_skill_ids.add(archive_id)
        features = archive_rollup.features.to_json() if archive_rollup else {}
        actions.append(
            await _insert_curation_action(
                conn,
                workspace_id=workspace_id,
                skill_id=archive_id,
                action="merge_duplicate",
                status="applied",
                reason="explicit duplicate edge archived lower-utility skill",
                features={
                    **features,
                    "utility_score": archive_rollup.utility_score if archive_rollup else 0.0,
                    "archived_slug": archive_slug,
                    "kept_skill_id": str(keep_id),
                    "kept_slug": keep_slug,
                    "filesystem_archive": filesystem_archive,
                    "merge_probe_plan": _merge_probe_plan(
                        from_skill_id=left,
                        to_skill_id=right,
                        from_slug=row["from_slug"],
                        to_slug=row["to_slug"],
                    ),
                },
            )
        )
    return actions


def _merge_probe_plan(
    *,
    from_skill_id: UUID,
    to_skill_id: UUID,
    from_slug: str,
    to_slug: str,
) -> dict[str, Any]:
    pair = {
        "from_skill_id": str(from_skill_id),
        "to_skill_id": str(to_skill_id),
        "from_slug": from_slug,
        "to_slug": to_slug,
    }
    trials = [
        _merge_probe_trial(
            kind="target",
            pair=pair,
            objective="Prove one kept duplicate covers the verified task evidence for both skills.",
            checks=[
                "representative tasks from both duplicate skills pass with the kept skill visible",
                "the archived skill adds no distinct required output, effect, or safety boundary",
                "the kept skill preserves the better historical outcome",
            ],
            expected={
                "status": "pass",
                "both_latest_versions_passed": True,
                "kept_skill_covers_archived_skill": True,
            },
        ),
        _merge_probe_trial(
            kind="no_skill_control",
            pair=pair,
            objective="Reject merge if hiding both duplicates performs as well as keeping one.",
            checks=[
                "baseline without either duplicate cannot match verified task outcomes",
                "kept skill provides positive marginal value over no injected duplicate",
            ],
            expected={
                "status": "compare",
                "kept_skill_must_outperform_no_skill": True,
            },
        ),
        _merge_probe_trial(
            kind="regression",
            pair=pair,
            objective=(
                "Reject merge if the archived duplicate carried unique boundaries "
                "or failure handling."
            ),
            checks=[
                "do-not-use boundaries from both duplicates remain enforceable",
                "unsafe-when and failure modes are not weakened",
                "support artifacts and environment contracts remain covered",
            ],
            expected={
                "status": "pass",
                "no_lost_boundaries": True,
                "no_new_shadowing_regression": True,
            },
        ),
        _merge_probe_trial(
            kind="collision",
            pair=pair,
            objective=(
                "Reject merge if the duplicate pair should be decomposed "
                "or disambiguated instead."
            ),
            checks=[
                "retrieval examples select one kept skill for the shared intent",
                "sibling skills are not newly shadowed by the kept skill",
                "the pair does not represent two distinct task clusters",
            ],
            expected={
                "status": "pass",
                "no_decompose_signal": True,
                "no_sibling_collision": True,
            },
        ),
    ]
    return {
        "schema": "autoskill.merge_probe_plan.v1",
        "kind": "duplicate_merge",
        "candidate_pair": pair,
        "planned_trials": trials,
        "acceptance_gate": {
            "latest_evaluator_passed_for_both": True,
            "target_pass": True,
            "no_skill_control_improves": True,
            "regression_failures": 0,
            "collision_failures": 0,
            "rollback_plan_present": True,
        },
        "rollback": {
            "required": True,
            "restore_archived_duplicate": True,
            "revoke_duplicate_edge_changes": True,
        },
    }


def _merge_probe_trial(
    *,
    kind: str,
    pair: dict[str, str],
    objective: str,
    checks: list[str],
    expected: dict[str, Any],
) -> dict[str, Any]:
    spec = {
        "schema": "autoskill.merge_probe.v1",
        "mode": "duplicate_merge",
        "candidate_pair": pair,
        "objective": objective,
        "checks": checks,
    }
    payload = {"kind": kind, "spec": spec, "expected": expected}
    return {
        "probe_hash": sha256_json(payload),
        "kind": kind,
        "maturity": "planned",
        "spec": spec,
        "expected": expected,
    }


async def _enforce_active_budget(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    rollup_by_skill: dict[UUID, SkillUtilityRollupRecord],
    active_budget: int,
    max_archive: int,
    workspace_root: Path | None,
    archive_root: Path | None,
) -> list[CurationActionRecord]:
    rows = await conn.fetch(
        """
        SELECT s.skill_id, s.slug, COALESCE(r.utility_score, 0)::float AS utility_score
        FROM autoskill.skills s
        LEFT JOIN autoskill.skill_utility_rollups r
          ON r.workspace_id = s.workspace_id
         AND r.skill_id = s.skill_id
        WHERE s.workspace_id = $1
          AND s.lifecycle_state = 'active'
        ORDER BY COALESCE(r.utility_score, 0) DESC, s.updated_at DESC, s.slug ASC
        OFFSET $2
        LIMIT $3
        """,
        workspace_id,
        active_budget,
        max_archive,
    )
    actions: list[CurationActionRecord] = []
    for row in rows:
        skill_id = row["skill_id"]
        rollup = rollup_by_skill.get(skill_id)
        filesystem_archive = _archive_active_files_for_curation(
            workspace_root=workspace_root,
            archive_root=archive_root,
            slug=row["slug"],
        )
        if filesystem_archive["status"] == "blocked":
            actions.append(
                await _insert_curation_action(
                    conn,
                    workspace_id=workspace_id,
                    skill_id=skill_id,
                    action="enforce_active_budget",
                    status="blocked",
                    reason="active budget archive requires filesystem archive snapshot",
                    features={
                        **(rollup.features.to_json() if rollup else {}),
                        "utility_score": rollup.utility_score if rollup else row["utility_score"],
                        "active_budget": active_budget,
                        "filesystem_archive": filesystem_archive,
                    },
                )
            )
            continue
        if not await _set_lifecycle_state(
            conn,
            workspace_id,
            skill_id,
            from_state="active",
            to_state="archived",
        ):
            _restore_files_after_failed_archive(
                workspace_root=workspace_root,
                archive_root=archive_root,
                filesystem_archive=filesystem_archive,
            )
            continue
        features = rollup.features.to_json() if rollup else {}
        actions.append(
            await _insert_curation_action(
                conn,
                workspace_id=workspace_id,
                skill_id=skill_id,
                action="enforce_active_budget",
                status="applied",
                reason="active skill budget exceeded",
                features={
                    **features,
                    "utility_score": rollup.utility_score if rollup else row["utility_score"],
                    "active_budget": active_budget,
                    "filesystem_archive": filesystem_archive,
                },
            )
        )
    return actions


async def _plan_improvements_and_splits(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    rollups: list[SkillUtilityRollupRecord],
    max_actions: int,
) -> list[CurationActionRecord]:
    if max_actions <= 0:
        return []
    actions: list[CurationActionRecord] = []
    for rollup in sorted(rollups, key=_planning_priority, reverse=True):
        if len(actions) >= max_actions:
            break
        if rollup.lifecycle_state not in {"active", "candidate"}:
            continue
        action, reason = _planning_action_for_rollup(rollup)
        if action is None:
            continue
        actions.append(
            await _insert_curation_action(
                conn,
                workspace_id=workspace_id,
                skill_id=rollup.skill_id,
                action=action,
                status="planned",
                reason=reason,
                features={
                    **rollup.features.to_json(),
                    "utility_score": rollup.utility_score,
                    "planner": "deterministic-curation.v1",
                    "repair_proposal": _repair_proposal_for_rollup(
                        rollup,
                        action=action,
                        reason=reason,
                    ),
                },
            )
        )
    return actions


def _planning_priority(rollup: SkillUtilityRollupRecord) -> tuple[int, int, int, float]:
    return (
        rollup.features.shadow_count,
        rollup.features.hurt_count,
        rollup.features.ignored_load_count
        + rollup.features.false_positive_load_count
        + min(5, rollup.features.token_waste // 400),
        -rollup.utility_score,
    )


def _planning_action_for_rollup(rollup: SkillUtilityRollupRecord) -> tuple[str | None, str]:
    if rollup.features.shadow_count >= 2 and rollup.features.hurt_count >= 1:
        return "plan_split", "shadowing plus harm suggests unstable skill boundaries"
    if _has_decomposition_grade_context_waste(rollup.features):
        return (
            "plan_split",
            "material context waste suggests decomposing broad low-value runtime text",
        )
    if rollup.features.shadow_count >= 2:
        return "plan_disambiguation_repair", "repeated shadowing requires boundary repair"
    if rollup.features.hurt_count >= 2:
        return "plan_improvement", "repeated harmful outcomes require guarded improvement"
    if (
        rollup.features.context_value_per_token < 0
        or rollup.features.ignored_load_count >= 2
        or rollup.features.false_positive_load_count >= 1
    ):
        return (
            "plan_improvement",
            "context token outcomes show low or wasteful marginal value",
        )
    return None, ""


def _has_decomposition_grade_context_waste(features: SkillUtilityFeatures) -> bool:
    context_confusion = features.ignored_load_count + features.false_positive_load_count
    if context_confusion >= 3 and features.token_waste >= 600:
        return True
    if features.false_positive_load_count >= 2 and features.token_waste >= 400:
        return True
    return features.context_value_per_token <= -0.02 and features.token_waste >= 900


def _repair_proposal_for_rollup(
    rollup: SkillUtilityRollupRecord,
    *,
    action: str,
    reason: str,
) -> dict[str, Any]:
    proposal_kind = {
        "plan_split": "decompose",
        "plan_disambiguation_repair": "improve",
        "plan_improvement": "improve",
    }.get(action, "review")
    trial_kinds = ["target", "regression", "no_skill_control"]
    if action in {"plan_split", "plan_disambiguation_repair"}:
        trial_kinds.append("sibling")
    if rollup.features.hurt_count:
        trial_kinds.append("adversarial")
    if (
        rollup.features.context_value_per_token < 0
        or rollup.features.ignored_load_count
        or rollup.features.false_positive_load_count
    ):
        trial_kinds.append("context_value")
    return {
        "schema": "autoskill.curation_repair_proposal.v1",
        "proposal_kind": proposal_kind,
        "curation_action": action,
        "subject_skill_id": str(rollup.skill_id),
        "subject_slug": rollup.slug,
        "reason": reason,
        "signals": {
            **rollup.features.to_json(),
            "utility_score": rollup.utility_score,
            "lifecycle_state": rollup.lifecycle_state,
        },
        "objectives": _repair_objectives(action),
        "planned_trials": trial_kinds,
        "acceptance_gate": {
            "scanner_pass": True,
            "regression_failures": 0,
            "utility_delta_positive": True,
            "context_value_per_token_non_negative": True,
            "requires_no_skill_control": True,
        },
        "rollback": {
            "required": True,
            "scope": [
                "skill_version",
                "body_index_document",
                "embedding",
                "context_artifact",
                "retrieval_log",
                "skill_graph_edge",
            ],
        },
    }


def _repair_objectives(action: str) -> list[str]:
    if action == "plan_split":
        return [
            "separate broad behavior into narrower successor skills",
            "preserve subject effects through successor coverage",
            "reduce sibling shadowing under broker replay",
            "reduce false-positive or ignored context loads from broad runtime text",
        ]
    if action == "plan_disambiguation_repair":
        return [
            "tighten applicability and do-not-use boundaries",
            "reduce wrong-skill selection under sibling probes",
        ]
    if action == "plan_improvement":
        return [
            "address repeated harmful outcomes with a guarded SkillIR revision",
            "prove positive marginal utility and context value before activation",
        ]
    return ["review curation signal before mutation"]


def _archive_active_files_for_curation(
    *,
    workspace_root: Path | None,
    archive_root: Path | None,
    slug: str,
) -> dict[str, Any]:
    if not slug:
        return {"status": "blocked", "reason": "missing_slug"}
    if "/" in slug or "\\" in slug or ".." in slug:
        return {"status": "blocked", "reason": "unsafe_slug"}
    if workspace_root is None or archive_root is None:
        return {"status": "blocked", "reason": "writer_roots_not_configured"}
    active_path = workspace_root / "skills" / "autoskill" / slug
    if not active_path.exists():
        return {"status": "already_absent", "active_relative_path": f"skills/autoskill/{slug}"}
    try:
        snapshot = archive_active_skill_and_remove(
            workspace_root,
            archive_root,
            slug=slug,
            snapshot_id=f"curation-{uuid4()}",
        )
    except (FileExistsError, OSError, ValueError) as error:
        return {
            "status": "blocked",
            "reason": f"{type(error).__name__}: {error}",
            "active_relative_path": f"skills/autoskill/{slug}",
        }
    if snapshot is None:
        return {"status": "already_absent", "active_relative_path": f"skills/autoskill/{slug}"}
    return {
        "status": "archived",
        "active_relative_path": f"skills/autoskill/{slug}",
        "archive_manifest_relative_path": snapshot.manifest_relative_path,
        "archive_manifest_sha256": snapshot.manifest_sha256,
        "archive_relative_path": snapshot.archive_relative_path,
    }


def _restore_files_after_failed_archive(
    *,
    workspace_root: Path | None,
    archive_root: Path | None,
    filesystem_archive: dict[str, Any],
) -> None:
    manifest_path = filesystem_archive.get("archive_manifest_relative_path")
    if workspace_root is None or archive_root is None or not isinstance(manifest_path, str):
        return
    try:
        rollback_active_skill(
            workspace_root,
            archive_root,
            archive_manifest_relative_path=manifest_path,
        )
    except (FileExistsError, OSError, ValueError):
        return


def _restore_archived_files_for_promotion(
    *,
    workspace_root: Path | None,
    archive_root: Path | None,
    slug: str,
) -> dict[str, Any]:
    if not slug:
        return {"status": "blocked", "reason": "missing_slug"}
    if "/" in slug or "\\" in slug or ".." in slug:
        return {"status": "blocked", "reason": "unsafe_slug"}
    if workspace_root is None or archive_root is None:
        return {"status": "blocked", "reason": "writer_roots_not_configured"}
    active_path = workspace_root / "skills" / "autoskill" / slug
    if active_path.exists():
        return {
            "status": "active_path_already_present",
            "active_relative_path": f"skills/autoskill/{slug}",
        }
    try:
        manifest_path = latest_archive_manifest_for_slug(archive_root, slug=slug)
    except (OSError, ValueError) as error:
        return {"status": "blocked", "reason": f"{type(error).__name__}: {error}"}
    if manifest_path is None:
        return {"status": "blocked", "reason": "archive_manifest_not_found"}
    try:
        restored = rollback_active_skill(
            workspace_root,
            archive_root,
            archive_manifest_relative_path=manifest_path,
        )
    except (FileExistsError, OSError, ValueError) as error:
        return {
            "status": "blocked",
            "reason": f"{type(error).__name__}: {error}",
            "archive_manifest_relative_path": manifest_path,
        }
    return {
        "status": "restored",
        "archive_manifest_relative_path": manifest_path,
        "active_relative_path": restored.active_relative_path,
        "manifest_sha256": restored.manifest_sha256,
    }


async def _set_lifecycle_state(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    skill_id: UUID,
    *,
    from_state: str,
    to_state: str,
) -> bool:
    result = await conn.execute(
        """
        UPDATE autoskill.skills
        SET lifecycle_state = $4,
            updated_at = now()
        WHERE workspace_id = $1
          AND skill_id = $2
          AND lifecycle_state = $3
        """,
        workspace_id,
        skill_id,
        from_state,
        to_state,
    )
    return _command_count(result) > 0


async def _latest_evaluator_passed(conn: asyncpg.Connection, skill_id: UUID) -> bool:
    status = await conn.fetchval(
        """
        SELECT evaluator_status
        FROM autoskill.skill_versions
        WHERE skill_id = $1
        ORDER BY created_at DESC
        LIMIT 1
        """,
        skill_id,
    )
    return status == "passed"


async def _latest_contract_gate(conn: asyncpg.Connection, skill_id: UUID) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        WITH latest AS (
          SELECT skill_version_id
          FROM autoskill.skill_versions
          WHERE skill_id = $1
          ORDER BY created_at DESC
          LIMIT 1
        )
        SELECT
          count(ec.environment_contract_id)::int AS total,
          count(ec.environment_contract_id) FILTER (
            WHERE ec.last_checked_at IS NULL
          )::int AS stale,
          count(ec.environment_contract_id) FILTER (
            WHERE ec.status NOT IN ('valid', 'false_positive')
          )::int AS blocking
        FROM latest
        LEFT JOIN autoskill.environment_contracts ec
          ON ec.skill_version_id = latest.skill_version_id
        """,
        skill_id,
    )
    total = int(row["total"] or 0) if row is not None else 0
    stale = int(row["stale"] or 0) if row is not None else 0
    blocking = int(row["blocking"] or 0) if row is not None else 0
    status = "passed" if stale == 0 and blocking == 0 else "blocked"
    return {
        "status": status,
        "total": total,
        "stale": stale,
        "blocking": blocking,
    }


async def _load_skill_feature_rows(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    limit: int,
) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT
          s.skill_id,
          s.slug,
          s.lifecycle_state,
          COALESCE(helped.count, 0)::int AS helped_count,
          COALESCE(hurt.count, 0)::int AS hurt_count,
          COALESCE(shadow.count, 0)::int AS shadow_count,
          COALESCE(retrieved.count, 0)::int AS retrieval_count,
          COALESCE(canary_failed.count, 0)::int AS canary_failure_count,
          COALESCE(context_value.marginal_value, 0.0)::double precision AS marginal_value,
          COALESCE(
            context_value.context_value_per_token,
            0.0
          )::double precision AS context_value_per_token,
          COALESCE(context_value.ignored_load_count, 0)::int AS ignored_load_count,
          COALESCE(
            context_value.false_positive_load_count,
            0
          )::int AS false_positive_load_count,
          COALESCE(context_value.token_waste, 0)::int AS token_waste
        FROM autoskill.skills s
        LEFT JOIN LATERAL (
          SELECT count(*)::int AS count
          FROM autoskill.attribution_events ae
          WHERE ae.workspace_id = s.workspace_id
            AND s.skill_id = ANY(ae.skill_ids)
            AND ae.outcome = 'skill_helped'
        ) helped ON true
        LEFT JOIN LATERAL (
          SELECT count(*)::int AS count
          FROM autoskill.attribution_events ae
          WHERE ae.workspace_id = s.workspace_id
            AND s.skill_id = ANY(ae.skill_ids)
            AND ae.outcome = 'skill_hurt'
        ) hurt ON true
        LEFT JOIN LATERAL (
          SELECT count(*)::int AS count
          FROM autoskill.attribution_events ae
          WHERE ae.workspace_id = s.workspace_id
            AND s.skill_id = ANY(ae.skill_ids)
            AND ae.outcome = 'skill_shadowed'
        ) shadow ON true
        LEFT JOIN LATERAL (
          SELECT count(*)::int AS count
          FROM autoskill.retrieval_logs rl
          WHERE rl.workspace_id = s.workspace_id
            AND s.skill_id = ANY(rl.rendered_skill_ids)
        ) retrieved ON true
        LEFT JOIN LATERAL (
          SELECT count(*)::int AS count
          FROM autoskill.canary_results cr
          WHERE cr.workspace_id = s.workspace_id
            AND cr.skill_id = s.skill_id
            AND (cr.critical OR cr.status IN ('failed', 'critical'))
        ) canary_failed ON true
        LEFT JOIN LATERAL (
          SELECT
            COALESCE(
              sum(
                (
                  ctl.metadata #>> '{marginal_value,marginal_value}'
                )::double precision
              ),
              0.0
            ) AS marginal_value,
            COALESCE(
              avg(
                (
                  ctl.metadata #>> '{marginal_value,context_value_per_token}'
                )::double precision
              ) FILTER (
                WHERE ctl.metadata #>> '{marginal_value,context_value_per_token}'
                  IS NOT NULL
              ),
              0.0
            ) AS context_value_per_token,
            count(*) FILTER (
              WHERE ctl.outcome IN ('ignored', 'ignored_load', 'unused')
            )::int AS ignored_load_count,
            count(*) FILTER (
              WHERE ctl.outcome IN ('false_positive', 'false_positive_load')
            )::int AS false_positive_load_count,
            COALESCE(
              sum(ctl.token_count) FILTER (
                WHERE ctl.outcome IN (
                  'ignored',
                  'ignored_load',
                  'unused',
                  'false_positive',
                  'false_positive_load'
                )
                OR (
                  ctl.metadata #>> '{marginal_value,context_value_per_token}'
                )::double precision < 0
              ),
              0
            )::int AS token_waste
          FROM autoskill.context_token_ledgers ctl
          LEFT JOIN autoskill.context_artifacts ca
            ON ca.context_artifact_id = ctl.context_artifact_id
           AND ca.workspace_id = ctl.workspace_id
          WHERE ctl.workspace_id = s.workspace_id
            AND COALESCE(ctl.metadata->>'revoked', 'false') != 'true'
            AND (
              ctl.skill_id = s.skill_id
              OR ca.skill_id = s.skill_id
            )
        ) context_value ON true
        WHERE s.workspace_id = $1
        ORDER BY s.updated_at DESC, s.slug ASC
        LIMIT $2
        """,
        workspace_id,
        max(1, min(limit, 1000)),
    )


async def _upsert_rollup(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    workspace_key: str,
    skill_id: UUID,
    slug: str,
    lifecycle_state: str,
    features: SkillUtilityFeatures,
    utility_score: float,
) -> SkillUtilityRollupRecord:
    row = await conn.fetchrow(
        """
        INSERT INTO autoskill.skill_utility_rollups (
          skill_utility_rollup_id,
          workspace_id,
          skill_id,
          helped_count,
          hurt_count,
          shadow_count,
          retrieval_count,
          canary_failure_count,
          utility_score,
          features
        )
        VALUES (
          gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb
        )
        ON CONFLICT (workspace_id, skill_id) DO UPDATE
        SET helped_count = EXCLUDED.helped_count,
            hurt_count = EXCLUDED.hurt_count,
            shadow_count = EXCLUDED.shadow_count,
            retrieval_count = EXCLUDED.retrieval_count,
            canary_failure_count = EXCLUDED.canary_failure_count,
            utility_score = EXCLUDED.utility_score,
            features = EXCLUDED.features,
            computed_at = now()
        RETURNING *, $10::text AS workspace_key, $11::text AS slug, $12::text AS lifecycle_state
        """,
        workspace_id,
        skill_id,
        features.helped_count,
        features.hurt_count,
        features.shadow_count,
        features.retrieval_count,
        features.canary_failure_count,
        utility_score,
        _json(features.to_json()),
        workspace_key,
        slug,
        lifecycle_state,
    )
    return SkillUtilityRollupRecord.from_row(row)


async def _insert_curation_action(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    skill_id: UUID | None,
    action: str,
    status: str,
    reason: str,
    features: dict[str, Any],
) -> CurationActionRecord:
    row = await conn.fetchrow(
        """
        INSERT INTO autoskill.curation_actions (
          curation_action_id,
          workspace_id,
          skill_id,
          action,
          status,
          reason,
          features
        )
        VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6::jsonb)
        RETURNING *
        """,
        workspace_id,
        skill_id,
        action,
        status,
        reason,
        _json(features),
    )
    return CurationActionRecord.from_row(row)


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _command_count(command_tag: str) -> int:
    try:
        return int(command_tag.rsplit(" ", 1)[1])
    except (IndexError, ValueError):
        return 0


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None
