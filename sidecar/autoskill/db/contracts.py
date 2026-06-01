from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class ContractExtractResult:
    scanned_versions: int
    extracted: int

    def to_json(self) -> dict[str, int]:
        return {"scanned_versions": self.scanned_versions, "extracted": self.extracted}


@dataclass(frozen=True)
class DriftCheckResult:
    scanned: int
    valid: int
    violated: int
    unknown: int
    events: list[dict[str, Any]]

    def to_json(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "valid": self.valid,
            "violated": self.violated,
            "unknown": self.unknown,
            "events": self.events,
        }


class ContractStore(Protocol):
    async def extract_contracts(
        self,
        *,
        workspace_key: str,
        limit: int = 250,
    ) -> ContractExtractResult:
        """Extract environment contracts from SkillIR revisions."""

    async def run_drift_checks(
        self,
        *,
        workspace_key: str,
        limit: int = 250,
    ) -> DriftCheckResult:
        """Run deterministic first-pass drift checks for extracted contracts."""


class NullContractStore:
    async def extract_contracts(
        self,
        *,
        workspace_key: str,
        limit: int = 250,
    ) -> ContractExtractResult:
        return ContractExtractResult(scanned_versions=0, extracted=0)

    async def run_drift_checks(
        self,
        *,
        workspace_key: str,
        limit: int = 250,
    ) -> DriftCheckResult:
        return DriftCheckResult(scanned=0, valid=0, violated=0, unknown=0, events=[])


class AsyncpgContractStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def extract_contracts(
        self,
        *,
        workspace_key: str,
        limit: int = 250,
    ) -> ContractExtractResult:
        pool = await self._get_pool()
        extracted = 0
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                SELECT s.skill_id, sv.skill_version_id, sv.skill_ir
                FROM autoskill.skill_versions sv
                JOIN autoskill.skills s USING (skill_id)
                WHERE s.workspace_id = $1
                ORDER BY sv.created_at DESC
                LIMIT $2
                """,
                workspace_id,
                max(1, min(limit, 1000)),
            )
            for row in rows:
                payload = _json_dict(row["skill_ir"])
                for contract in _contracts_from_skill_ir(payload):
                    await conn.execute(
                        """
                        INSERT INTO autoskill.environment_contracts (
                          environment_contract_id,
                          workspace_id,
                          skill_id,
                          skill_version_id,
                          contract_type,
                          name,
                          expectation,
                          validation_method,
                          status,
                          severity,
                          metadata
                        )
                        VALUES (
                          gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, 'unknown', $8, $9::jsonb
                        )
                        ON CONFLICT (workspace_id, skill_version_id, name, expectation) DO UPDATE
                        SET contract_type = EXCLUDED.contract_type,
                            validation_method = EXCLUDED.validation_method,
                            severity = EXCLUDED.severity,
                            metadata = EXCLUDED.metadata
                        """,
                        workspace_id,
                        row["skill_id"],
                        row["skill_version_id"],
                        contract["contract_type"],
                        contract["name"],
                        contract["expectation"],
                        contract["validation_method"],
                        contract["severity"],
                        _json(contract["metadata"]),
                    )
                    extracted += 1
        return ContractExtractResult(scanned_versions=len(rows), extracted=extracted)

    async def run_drift_checks(
        self,
        *,
        workspace_key: str,
        limit: int = 250,
    ) -> DriftCheckResult:
        pool = await self._get_pool()
        events: list[dict[str, Any]] = []
        valid = violated = unknown = 0
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                SELECT *
                FROM autoskill.environment_contracts
                WHERE workspace_id = $1
                ORDER BY created_at ASC
                LIMIT $2
                """,
                workspace_id,
                max(1, min(limit, 1000)),
            )
            for row in rows:
                status, reason = _check_contract(row)
                if status == "valid":
                    valid += 1
                elif status == "violated":
                    violated += 1
                else:
                    unknown += 1
                await conn.execute(
                    """
                    UPDATE autoskill.environment_contracts
                    SET status = $2,
                        last_checked_at = now(),
                        metadata = metadata || $3::jsonb
                    WHERE environment_contract_id = $1
                    """,
                    row["environment_contract_id"],
                    status,
                    _json({"last_reason": reason}),
                )
                if status == "violated":
                    event = await conn.fetchrow(
                        """
                        INSERT INTO autoskill.drift_events (
                          drift_event_id,
                          workspace_id,
                          environment_contract_id,
                          skill_id,
                          skill_version_id,
                          status,
                          reason,
                          repair_candidate
                        )
                        VALUES (gen_random_uuid(), $1, $2, $3, $4, 'open', $5, $6::jsonb)
                        RETURNING *
                        """,
                        workspace_id,
                        row["environment_contract_id"],
                        row["skill_id"],
                        row["skill_version_id"],
                        reason,
                        _json(
                            {
                                "kind": "contract_repair",
                                "contract_name": row["name"],
                                "contract_type": row["contract_type"],
                            }
                        ),
                    )
                    events.append(
                        {
                            "drift_event_id": str(event["drift_event_id"]),
                            "environment_contract_id": str(row["environment_contract_id"]),
                            "skill_id": str(row["skill_id"]),
                            "reason": reason,
                        }
                    )
        return DriftCheckResult(
            scanned=len(rows),
            valid=valid,
            violated=violated,
            unknown=unknown,
            events=events,
        )


def _contracts_from_skill_ir(skill_ir: dict[str, Any]) -> list[dict[str, Any]]:
    contracts = []
    for item in skill_ir.get("environment_contracts") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        expectation = str(item.get("expectation") or "").strip()
        if not name or not expectation:
            continue
        probe = str(item.get("probe") or "").strip()
        validation_method = _validation_method_for_probe(probe)
        contracts.append(
            {
                "contract_type": str(item.get("kind") or "environment"),
                "name": name,
                "expectation": expectation,
                "validation_method": validation_method,
                "severity": "medium",
                "metadata": {"probe": probe} if probe else {},
            }
        )
    return contracts


def _check_contract(row: asyncpg.Record) -> tuple[str, str]:
    metadata = _json_dict(row["metadata"])
    probe = str(metadata.get("probe") or "")
    if probe.startswith("static:exists:"):
        path = Path(probe.removeprefix("static:exists:")).expanduser()
        if path.exists():
            return "valid", f"path exists: {path}"
        return "violated", f"path missing: {path}"
    if probe.startswith("static:which:"):
        command = probe.removeprefix("static:which:").strip()
        if not command or "/" in command:
            return "unknown", "command probe is empty or not a bare executable name"
        resolved = shutil.which(command)
        if resolved:
            return "valid", f"command found: {command}"
        return "violated", f"command missing: {command}"
    if probe.startswith("static:env:"):
        env_name = probe.removeprefix("static:env:").strip()
        if not env_name or not env_name.replace("_", "").isalnum():
            return "unknown", "environment probe is empty or invalid"
        if os.environ.get(env_name):
            return "valid", f"environment variable set: {env_name}"
        return "violated", f"environment variable missing: {env_name}"
    return "unknown", "no deterministic validation probe configured"


def _validation_method_for_probe(probe: str) -> str:
    if probe.startswith("static:exists:"):
        return "static_path_exists"
    if probe.startswith("static:which:"):
        return "static_command_exists"
    if probe.startswith("static:env:"):
        return "static_env_present"
    return "manual"


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
