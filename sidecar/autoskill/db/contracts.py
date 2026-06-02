from __future__ import annotations

import json
import os
import shutil
import socket
from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.core.hashing import sha256_json
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
    probes_created: int = 0
    probes_retired: int = 0
    false_positive: int = 0

    def to_json(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "valid": self.valid,
            "violated": self.violated,
            "unknown": self.unknown,
            "probes_created": self.probes_created,
            "probes_retired": self.probes_retired,
            "false_positive": self.false_positive,
            "events": self.events,
        }


@dataclass(frozen=True)
class DriftFalsePositiveResult:
    environment_contract_id: UUID
    status: str
    probes_retired: int
    drift_events_closed: int
    metadata: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "environment_contract_id": str(self.environment_contract_id),
            "status": self.status,
            "probes_retired": self.probes_retired,
            "drift_events_closed": self.drift_events_closed,
            "metadata": self.metadata,
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

    async def mark_drift_false_positive(
        self,
        *,
        workspace_key: str,
        environment_contract_id: UUID,
        operator_id: str | None = None,
        rationale: str | None = None,
    ) -> DriftFalsePositiveResult:
        """Suppress a known-noisy contract and retire its active drift probes."""


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
        return DriftCheckResult(
            scanned=0,
            valid=0,
            violated=0,
            unknown=0,
            probes_created=0,
            probes_retired=0,
            false_positive=0,
            events=[],
        )

    async def mark_drift_false_positive(
        self,
        *,
        workspace_key: str,
        environment_contract_id: UUID,
        operator_id: str | None = None,
        rationale: str | None = None,
    ) -> DriftFalsePositiveResult:
        return DriftFalsePositiveResult(
            environment_contract_id=environment_contract_id,
            status="not_found",
            probes_retired=0,
            drift_events_closed=0,
            metadata={
                "workspace_key": workspace_key,
                "operator_id": operator_id,
                "rationale": rationale,
            },
        )


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
        probes_created = 0
        probes_retired = 0
        false_positive = 0
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
                if _is_false_positive_contract(row):
                    false_positive += 1
                    probes_retired += await _retire_resolved_drift_probes(
                        conn,
                        workspace_id=workspace_id,
                        contract_id=row["environment_contract_id"],
                    )
                    await _close_false_positive_drift_events(
                        conn,
                        workspace_id=workspace_id,
                        contract_id=row["environment_contract_id"],
                    )
                    await conn.execute(
                        """
                        UPDATE autoskill.environment_contracts
                        SET status = 'false_positive',
                            last_checked_at = now(),
                            metadata = metadata || $2::jsonb
                        WHERE environment_contract_id = $1
                        """,
                        row["environment_contract_id"],
                        _json({"last_reason": "operator-marked false positive"}),
                    )
                    continue
                status, reason = _check_contract(row)
                if status == "valid":
                    valid += 1
                    probes_retired += await _retire_resolved_drift_probes(
                        conn,
                        workspace_id=workspace_id,
                        contract_id=row["environment_contract_id"],
                    )
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
                    probe_hash, probe_created = await _upsert_drift_probe(
                        conn,
                        workspace_id=workspace_id,
                        contract=row,
                        reason=reason,
                    )
                    probes_created += int(probe_created)
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
                                "contract_expectation": row["expectation"],
                                "validation_method": row["validation_method"],
                                "drift_probe_hash": probe_hash,
                                "repair_plan": _repair_plan_for_contract(row, reason),
                                "activation_gate": "proposal_only",
                            }
                        ),
                    )
                    events.append(
                        {
                            "drift_event_id": str(event["drift_event_id"]),
                            "environment_contract_id": str(row["environment_contract_id"]),
                            "skill_id": str(row["skill_id"]),
                            "reason": reason,
                            "drift_probe_hash": probe_hash,
                            "probe_created": probe_created,
                        }
                    )
        return DriftCheckResult(
            scanned=len(rows),
            valid=valid,
            violated=violated,
            unknown=unknown,
            probes_created=probes_created,
            probes_retired=probes_retired,
            false_positive=false_positive,
            events=events,
        )

    async def mark_drift_false_positive(
        self,
        *,
        workspace_key: str,
        environment_contract_id: UUID,
        operator_id: str | None = None,
        rationale: str | None = None,
    ) -> DriftFalsePositiveResult:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                UPDATE autoskill.environment_contracts
                SET status = 'false_positive',
                    last_checked_at = now(),
                    metadata = metadata || jsonb_build_object(
                      'false_positive',
                      jsonb_build_object(
                        'marked_at', now(),
                        'operator_id', $3::text,
                        'rationale', $4::text
                      ),
                      'last_reason',
                      'operator-marked false positive'
                    )
                WHERE workspace_id = $1
                  AND environment_contract_id = $2
                RETURNING *
                """,
                workspace_id,
                environment_contract_id,
                operator_id,
                rationale,
            )
            if row is None:
                return DriftFalsePositiveResult(
                    environment_contract_id=environment_contract_id,
                    status="not_found",
                    probes_retired=0,
                    drift_events_closed=0,
                    metadata={},
                )
            probes_retired = await _retire_resolved_drift_probes(
                conn,
                workspace_id=workspace_id,
                contract_id=environment_contract_id,
            )
            drift_events_closed = await _close_false_positive_drift_events(
                conn,
                workspace_id=workspace_id,
                contract_id=environment_contract_id,
            )
            return DriftFalsePositiveResult(
                environment_contract_id=environment_contract_id,
                status=row["status"],
                probes_retired=probes_retired,
                drift_events_closed=drift_events_closed,
                metadata=_json_dict(row["metadata"]),
            )


async def _upsert_drift_probe(
    conn: asyncpg.Connection,
    *,
    workspace_id: Any,
    contract: asyncpg.Record,
    reason: str,
) -> tuple[str, bool]:
    spec = {
        "schema": "autoskill.probe.v1",
        "kind": "drift",
        "environment_contract_id": str(contract["environment_contract_id"]),
        "skill_id": str(contract["skill_id"]),
        "skill_version_id": str(contract["skill_version_id"]),
        "contract_name": contract["name"],
        "contract_type": contract["contract_type"],
        "expectation": contract["expectation"],
        "validation_method": contract["validation_method"],
        "reason": reason,
        "probe": _json_dict(contract["metadata"]).get("probe"),
    }
    expected = {
        "status": "valid",
        "repair_must_clear_violation": True,
    }
    probe_hash = sha256_json({"spec": spec, "expected": expected})
    row = await conn.fetchrow(
        """
        INSERT INTO autoskill.probes (
          probe_id, workspace_id, probe_hash, kind, maturity, spec, expected, active
        )
        VALUES (gen_random_uuid(), $1, $2, 'drift', 'observed', $3::jsonb, $4::jsonb, true)
        ON CONFLICT (workspace_id, probe_hash) DO UPDATE
        SET active = true,
            retired_at = NULL,
            spec = EXCLUDED.spec,
            expected = EXCLUDED.expected
        RETURNING (xmax = 0) AS created
        """,
        workspace_id,
        probe_hash,
        _json(spec),
        _json(expected),
    )
    return probe_hash, bool(row["created"]) if row is not None else False


async def _retire_resolved_drift_probes(
    conn: asyncpg.Connection,
    *,
    workspace_id: Any,
    contract_id: Any,
) -> int:
    command = await conn.execute(
        """
        UPDATE autoskill.probes
        SET active = false,
            retired_at = now()
        WHERE workspace_id = $1
          AND kind = 'drift'
          AND active
          AND spec->>'environment_contract_id' = $2
        """,
        workspace_id,
        str(contract_id),
    )
    return _command_count(command)


async def _close_false_positive_drift_events(
    conn: asyncpg.Connection,
    *,
    workspace_id: Any,
    contract_id: Any,
) -> int:
    command = await conn.execute(
        """
        UPDATE autoskill.drift_events
        SET status = 'false_positive',
            repair_candidate = repair_candidate || $3::jsonb
        WHERE workspace_id = $1
          AND environment_contract_id = $2
          AND status = 'open'
        """,
        workspace_id,
        contract_id,
        _json({"closed_reason": "operator-marked false positive"}),
    )
    return _command_count(command)


def _is_false_positive_contract(row: asyncpg.Record | dict[str, Any]) -> bool:
    metadata = _json_dict(row["metadata"])
    try:
        status = row["status"]
    except KeyError:
        status = None
    return bool(metadata.get("false_positive")) or status == "false_positive"


def _repair_plan_for_contract(contract: asyncpg.Record, reason: str) -> dict[str, Any]:
    return {
        "kind": "localized_contract_repair",
        "source": "drift.check",
        "contract_name": contract["name"],
        "contract_type": contract["contract_type"],
        "validation_method": contract["validation_method"],
        "reason": reason,
        "required_actions": [
            "inspect the current SkillIR environment contract",
            "propose a scoped SkillIR contract or procedure update",
            "run the generated drift probe and existing regression probes",
        ],
    }


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
    if probe.startswith("static:python-package:"):
        package_name = probe.removeprefix("static:python-package:").strip()
        if not _safe_package_name(package_name):
            return "unknown", "python package probe is empty or invalid"
        try:
            importlib_metadata.version(package_name)
        except importlib_metadata.PackageNotFoundError:
            return "violated", f"python package missing: {package_name}"
        return "valid", f"python package found: {package_name}"
    if probe.startswith("static:json-schema:"):
        path = Path(probe.removeprefix("static:json-schema:")).expanduser()
        if not path.exists():
            return "violated", f"json schema path missing: {path}"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return "violated", f"json schema unreadable: {type(error).__name__}"
        if not isinstance(payload, dict):
            return "violated", "json schema is not an object"
        if "$schema" in payload or "type" in payload or "properties" in payload:
            return "valid", f"json schema loaded: {path}"
        return "unknown", "json schema lacks schema/type/properties markers"
    if probe.startswith("static:tcp:"):
        target = probe.removeprefix("static:tcp:").strip()
        host, port = _parse_host_port(target)
        if host is None or port is None:
            return "unknown", "tcp service probe must be host:port"
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return "valid", f"tcp service reachable: {host}:{port}"
        except OSError:
            return "violated", f"tcp service unreachable: {host}:{port}"
    return "unknown", "no deterministic validation probe configured"


def _validation_method_for_probe(probe: str) -> str:
    if probe.startswith("static:exists:"):
        return "static_path_exists"
    if probe.startswith("static:which:"):
        return "static_command_exists"
    if probe.startswith("static:env:"):
        return "static_env_present"
    if probe.startswith("static:python-package:"):
        return "static_python_package_present"
    if probe.startswith("static:json-schema:"):
        return "static_json_schema_loadable"
    if probe.startswith("static:tcp:"):
        return "static_tcp_reachable"
    return "manual"


def _safe_package_name(package_name: str) -> bool:
    if not package_name:
        return False
    return all(character.isalnum() or character in {"_", "-", "."} for character in package_name)


def _parse_host_port(target: str) -> tuple[str | None, int | None]:
    if ":" not in target:
        return None, None
    host, port_text = target.rsplit(":", 1)
    host = host.strip()
    try:
        port = int(port_text)
    except ValueError:
        return None, None
    if not host or port < 1 or port > 65535:
        return None, None
    return host, port


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
