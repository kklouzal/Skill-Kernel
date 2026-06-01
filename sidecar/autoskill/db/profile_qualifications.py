from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace

ModelQualificationVerdict = Literal[
    "qualified_autonomous",
    "qualified_propose_only",
    "qualified_classify",
    "failed",
    "expired",
]
EmbeddingQualificationVerdict = Literal["qualified", "failed", "expired"]


@dataclass(frozen=True)
class ModelProfileQualificationRunRecord:
    model_profile_qualification_run_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    model_profile_id: UUID | None
    profile_key: str
    route_kind: str
    provider: str
    model: str
    thinking_level: str | None
    probe_set_version: str
    verdict: str
    probe_results: dict[str, Any]
    created_at: datetime
    expires_at: datetime | None

    @classmethod
    def from_row(
        cls,
        row: asyncpg.Record | dict[str, Any],
    ) -> ModelProfileQualificationRunRecord:
        return cls(
            model_profile_qualification_run_id=row["model_profile_qualification_run_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            model_profile_id=_row_get(row, "model_profile_id"),
            profile_key=row["profile_key"],
            route_kind=row["route_kind"],
            provider=row["provider"],
            model=row["model"],
            thinking_level=_row_get(row, "thinking_level"),
            probe_set_version=row["probe_set_version"],
            verdict=row["verdict"],
            probe_results=_json_dict(row["probe_results"]),
            created_at=row["created_at"],
            expires_at=_row_get(row, "expires_at"),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "model_profile_qualification_run_id": str(
                self.model_profile_qualification_run_id
            ),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "model_profile_id": (
                str(self.model_profile_id) if self.model_profile_id else None
            ),
            "profile_key": self.profile_key,
            "route_kind": self.route_kind,
            "provider": self.provider,
            "model": self.model,
            "thinking_level": self.thinking_level,
            "probe_set_version": self.probe_set_version,
            "verdict": self.verdict,
            "probe_results": self.probe_results,
            "created_at": self.created_at.isoformat(),
            "expires_at": _iso_or_none(self.expires_at),
        }


@dataclass(frozen=True)
class EmbeddingProfileQualificationRunRecord:
    embedding_profile_qualification_run_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    embedding_profile_id: UUID | None
    profile_key: str
    route_kind: str
    provider: str
    model: str
    embedding_dim: int
    distance_metric: str
    probe_set_version: str
    verdict: str
    probe_results: dict[str, Any]
    created_at: datetime
    expires_at: datetime | None

    @classmethod
    def from_row(
        cls,
        row: asyncpg.Record | dict[str, Any],
    ) -> EmbeddingProfileQualificationRunRecord:
        return cls(
            embedding_profile_qualification_run_id=row[
                "embedding_profile_qualification_run_id"
            ],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            embedding_profile_id=_row_get(row, "embedding_profile_id"),
            profile_key=row["profile_key"],
            route_kind=row["route_kind"],
            provider=row["provider"],
            model=row["model"],
            embedding_dim=int(row["embedding_dim"]),
            distance_metric=row["distance_metric"],
            probe_set_version=row["probe_set_version"],
            verdict=row["verdict"],
            probe_results=_json_dict(row["probe_results"]),
            created_at=row["created_at"],
            expires_at=_row_get(row, "expires_at"),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "embedding_profile_qualification_run_id": str(
                self.embedding_profile_qualification_run_id
            ),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "embedding_profile_id": (
                str(self.embedding_profile_id) if self.embedding_profile_id else None
            ),
            "profile_key": self.profile_key,
            "route_kind": self.route_kind,
            "provider": self.provider,
            "model": self.model,
            "embedding_dim": self.embedding_dim,
            "distance_metric": self.distance_metric,
            "probe_set_version": self.probe_set_version,
            "verdict": self.verdict,
            "probe_results": self.probe_results,
            "created_at": self.created_at.isoformat(),
            "expires_at": _iso_or_none(self.expires_at),
        }


class ProfileQualificationStore(Protocol):
    async def record_model_qualification_run(
        self,
        *,
        workspace_key: str,
        model_profile_id: UUID | None,
        profile_key: str,
        route_kind: str,
        provider: str,
        model: str,
        thinking_level: str | None,
        probe_set_version: str,
        verdict: ModelQualificationVerdict,
        probe_results: dict[str, Any],
        expires_at: datetime | None = None,
    ) -> ModelProfileQualificationRunRecord:
        """Persist one text model qualification run and update profile status."""

    async def record_embedding_qualification_run(
        self,
        *,
        workspace_key: str,
        embedding_profile_id: UUID | None,
        profile_key: str,
        route_kind: str,
        provider: str,
        model: str,
        embedding_dim: int,
        distance_metric: str,
        probe_set_version: str,
        verdict: EmbeddingQualificationVerdict,
        probe_results: dict[str, Any],
        expires_at: datetime | None = None,
    ) -> EmbeddingProfileQualificationRunRecord:
        """Persist one embedding qualification run and update profile status."""


class NullProfileQualificationStore:
    def __init__(self) -> None:
        self.model_runs: list[ModelProfileQualificationRunRecord] = []
        self.embedding_runs: list[EmbeddingProfileQualificationRunRecord] = []

    async def record_model_qualification_run(
        self,
        *,
        workspace_key: str,
        model_profile_id: UUID | None,
        profile_key: str,
        route_kind: str,
        provider: str,
        model: str,
        thinking_level: str | None,
        probe_set_version: str,
        verdict: ModelQualificationVerdict,
        probe_results: dict[str, Any],
        expires_at: datetime | None = None,
    ) -> ModelProfileQualificationRunRecord:
        record = ModelProfileQualificationRunRecord(
            model_profile_qualification_run_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            model_profile_id=model_profile_id,
            profile_key=profile_key,
            route_kind=route_kind,
            provider=provider,
            model=model,
            thinking_level=thinking_level,
            probe_set_version=probe_set_version,
            verdict=verdict,
            probe_results=probe_results,
            created_at=datetime.now(),
            expires_at=expires_at,
        )
        self.model_runs.append(record)
        return record

    async def record_embedding_qualification_run(
        self,
        *,
        workspace_key: str,
        embedding_profile_id: UUID | None,
        profile_key: str,
        route_kind: str,
        provider: str,
        model: str,
        embedding_dim: int,
        distance_metric: str,
        probe_set_version: str,
        verdict: EmbeddingQualificationVerdict,
        probe_results: dict[str, Any],
        expires_at: datetime | None = None,
    ) -> EmbeddingProfileQualificationRunRecord:
        record = EmbeddingProfileQualificationRunRecord(
            embedding_profile_qualification_run_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            embedding_profile_id=embedding_profile_id,
            profile_key=profile_key,
            route_kind=route_kind,
            provider=provider,
            model=model,
            embedding_dim=embedding_dim,
            distance_metric=distance_metric,
            probe_set_version=probe_set_version,
            verdict=verdict,
            probe_results=probe_results,
            created_at=datetime.now(),
            expires_at=expires_at,
        )
        self.embedding_runs.append(record)
        return record


class AsyncpgProfileQualificationStore(AsyncpgPoolOwner):
    async def record_model_qualification_run(
        self,
        *,
        workspace_key: str,
        model_profile_id: UUID | None,
        profile_key: str,
        route_kind: str,
        provider: str,
        model: str,
        thinking_level: str | None,
        probe_set_version: str,
        verdict: ModelQualificationVerdict,
        probe_results: dict[str, Any],
        expires_at: datetime | None = None,
    ) -> ModelProfileQualificationRunRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            status = "qualified" if verdict.startswith("qualified_") else "failed"
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.model_profile_qualification_runs (
                  model_profile_qualification_run_id,
                  workspace_id,
                  model_profile_id,
                  profile_key,
                  route_kind,
                  provider,
                  model,
                  thinking_level,
                  probe_set_version,
                  verdict,
                  probe_results,
                  expires_at
                )
                VALUES (
                  gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11
                )
                RETURNING *, $12::text AS workspace_key
                """,
                workspace_id,
                model_profile_id,
                profile_key,
                route_kind,
                provider,
                model,
                thinking_level,
                probe_set_version,
                verdict,
                _json(probe_results),
                expires_at,
                workspace_key,
            )
            await conn.execute(
                """
                UPDATE autoskill.model_profiles
                SET status = $3,
                    qualification = qualification || $4::jsonb,
                    updated_at = now()
                WHERE workspace_id = $1
                  AND profile_key = $2
                """,
                workspace_id,
                profile_key,
                status,
                _json(
                    {
                        "latest_qualification_run_id": str(
                            row["model_profile_qualification_run_id"]
                        ),
                        "latest_qualification_verdict": verdict,
                        "latest_probe_set_version": probe_set_version,
                        "qualification_expires_at": _iso_or_none(expires_at),
                    }
                ),
            )
        return ModelProfileQualificationRunRecord.from_row(row)

    async def record_embedding_qualification_run(
        self,
        *,
        workspace_key: str,
        embedding_profile_id: UUID | None,
        profile_key: str,
        route_kind: str,
        provider: str,
        model: str,
        embedding_dim: int,
        distance_metric: str,
        probe_set_version: str,
        verdict: EmbeddingQualificationVerdict,
        probe_results: dict[str, Any],
        expires_at: datetime | None = None,
    ) -> EmbeddingProfileQualificationRunRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            status = "qualified" if verdict == "qualified" else "failed"
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.embedding_profile_qualification_runs (
                  embedding_profile_qualification_run_id,
                  workspace_id,
                  embedding_profile_id,
                  profile_key,
                  route_kind,
                  provider,
                  model,
                  embedding_dim,
                  distance_metric,
                  probe_set_version,
                  verdict,
                  probe_results,
                  expires_at
                )
                VALUES (
                  gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                  $11::jsonb, $12
                )
                RETURNING *, $13::text AS workspace_key
                """,
                workspace_id,
                embedding_profile_id,
                profile_key,
                route_kind,
                provider,
                model,
                embedding_dim,
                distance_metric,
                probe_set_version,
                verdict,
                _json(probe_results),
                expires_at,
                workspace_key,
            )
            await conn.execute(
                """
                UPDATE autoskill.embedding_profiles
                SET status = $3,
                    qualification = qualification || $4::jsonb,
                    updated_at = now()
                WHERE workspace_id = $1
                  AND profile_key = $2
                """,
                workspace_id,
                profile_key,
                status,
                _json(
                    {
                        "latest_qualification_run_id": str(
                            row["embedding_profile_qualification_run_id"]
                        ),
                        "latest_qualification_verdict": verdict,
                        "latest_probe_set_version": probe_set_version,
                        "qualification_expires_at": _iso_or_none(expires_at),
                    }
                ),
            )
        return EmbeddingProfileQualificationRunRecord.from_row(row)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
