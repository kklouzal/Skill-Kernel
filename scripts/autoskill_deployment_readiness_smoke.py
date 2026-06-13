#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sidecar"))

from autoskill.api.app import create_app
from autoskill.core.config import get_settings
from autoskill.db.broker_policy import AsyncpgBrokerPolicyStore
from autoskill.db.jobs import AsyncpgJobStore
from autoskill.db.profiles import AsyncpgProfileStore
from autoskill.db.workspaces import ensure_workspace

REQUIRED_CHECKS = (
    "storage_plane_schema_ready",
    "read_model_contract_compatible",
    "scheduler_worker_heartbeat",
    "active_executor_profile",
    "qualified_text_model_profile",
    "active_embedding_profile",
    "active_broker_policy",
    "broker_replay_corpus",
    "operator_reviewed_broker_replay_corpus",
)

EXECUTOR_PROFILE_DETAIL_KEYS = (
    "profile_key",
    "status",
    "agent_backend",
    "model_family",
    "sandbox",
    "os_name",
    "tool_count",
    "tool_keys",
    "binary_count",
    "binary_keys",
    "api_contract_count",
    "api_contract_keys",
    "permission_keys",
    "reason_codes",
)


def main() -> None:
    args = _parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, indent=2, sort_keys=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a real-Postgres deployment readiness smoke proving migrated "
            "pgvector storage and asyncpg-backed readiness records satisfy "
            "/v1/deployment/readiness without exposing raw evidence or "
            "mutating OpenClaw runtime state."
        )
    )
    parser.add_argument("--database-url", default=_default_database_url())
    parser.add_argument(
        "--workspace-id",
        default=None,
        help="Optional workspace key. Defaults to an isolated smoke workspace.",
    )
    parser.add_argument(
        "--skip-migrations",
        "--skip-migrate",
        action="store_true",
        help="Assume migrations have already been applied.",
    )
    parser.add_argument(
        "--keep-rows",
        action="store_true",
        help="Leave smoke rows in Postgres for manual inspection.",
    )
    parser.add_argument(
        "--replay-tag",
        default="production",
        help="Replay tag to require on the seeded content-safe replay episode.",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    if not args.skip_migrations:
        await _apply_migration(args.database_url)
    smoke_id = f"deployment-readiness-smoke-{uuid4()}"
    workspace_key = args.workspace_id or smoke_id
    worker_id = f"{smoke_id}:scheduler"
    jobs = AsyncpgJobStore(args.database_url)
    profiles = AsyncpgProfileStore(args.database_url)
    broker_policies = AsyncpgBrokerPolicyStore(args.database_url)
    try:
        await _delete_smoke_workspace(args.database_url, workspace_key, worker_id)
        seeded = await _seed_readiness_records(
            database_url=args.database_url,
            jobs=jobs,
            profiles=profiles,
            broker_policies=broker_policies,
            workspace_key=workspace_key,
            smoke_id=smoke_id,
            worker_id=worker_id,
            replay_tag=args.replay_tag,
        )
        response = await _call_readiness_route(
            database_url=args.database_url,
            jobs=jobs,
            profiles=profiles,
            broker_policies=broker_policies,
            workspace_key=workspace_key,
            replay_tag=args.replay_tag,
        )
        summary = _summarize_response(
            response=response.model_dump(mode="json"),
            seeded=seeded,
            smoke_id=smoke_id,
        )
        _assert_smoke(summary)
        return summary
    finally:
        await jobs.close()
        await profiles.close()
        await broker_policies.close()
        if not args.keep_rows:
            await _delete_smoke_workspace(args.database_url, workspace_key, worker_id)


async def _seed_readiness_records(
    *,
    database_url: str,
    jobs: AsyncpgJobStore,
    profiles: AsyncpgProfileStore,
    broker_policies: AsyncpgBrokerPolicyStore,
    workspace_key: str,
    smoke_id: str,
    worker_id: str,
    replay_tag: str,
) -> dict[str, Any]:
    await profiles.upsert_executor_profile(
        workspace_key=workspace_key,
        profile_key="deployment-readiness-smoke-executor",
        model_family="gpt",
        agent_backend="codex",
        sandbox="danger-full-access",
        os_name="linux",
        available_tools=["exec"],
        available_binaries=["git", "uv"],
        permissions={"filesystem": "workspace"},
        api_contracts={"skillkernel": "deployment-readiness-smoke"},
        status="active",
    )
    await profiles.upsert_model_profile(
        workspace_key=workspace_key,
        profile_key="deployment-readiness-smoke-text",
        provider="openai-compatible",
        model="content-safe-smoke-text-model",
        route_kind="openai_compatible",
        endpoint_ref="AUTOSKILL_LLM_API_BASE_URL",
        endpoint_kind="chat_completions",
        timeout_seconds=30.0,
        status="qualified",
        qualification={
            "schema": "autoskill.deployment-readiness-smoke.qualification.v1",
            "latest_qualification_verdict": "qualified_autonomous",
            "content_safe": True,
        },
        thinking_level="medium",
        thinking_fallback_policy="omit",
    )
    await profiles.upsert_embedding_profile(
        workspace_key=workspace_key,
        profile_key="deployment-readiness-smoke-embedding",
        provider="openai-compatible",
        model="content-safe-smoke-embedding-model",
        route_kind="openai_compatible",
        embedding_dim=768,
        endpoint_ref="AUTOSKILL_EMBEDDING_API_BASE_URL",
        timeout_seconds=15.0,
        status="active",
        qualification={
            "schema": "autoskill.deployment-readiness-smoke.embedding-qualification.v1",
            "latest_qualification_verdict": "qualified",
            "content_safe": True,
        },
    )
    policy = await broker_policies.upsert_policy_version(
        workspace_key=workspace_key,
        version=f"{smoke_id}.policy.v1",
        status="active",
        policy={
            "schema": "autoskill.deployment-readiness-smoke.broker-policy.v1",
            "max_context_hint_tokens": 800,
            "content_safe": True,
        },
    )
    retrieval_log_id = await _insert_content_safe_retrieval_log(
        database_url=database_url,
        workspace_key=workspace_key,
        broker_policy_version_id=policy.broker_policy_version_id,
        smoke_id=smoke_id,
    )
    replay = await broker_policies.record_replay_episode(
        workspace_key=workspace_key,
        episode_key=f"{smoke_id}:operator-reviewed",
        redacted_user_intent="Content-safe deployment readiness smoke replay.",
        expected_decision="skill_hint",
        tags=[replay_tag, "operator-reviewed", "telemetry-derived"],
        metadata={
            "schema": "autoskill.deployment-readiness-smoke.replay.v1",
            "source": "automatic_replay_synthesis",
            "evidence_fidelity": "redacted_derivative",
            "content_safe": True,
        },
        source_retrieval_log_id=retrieval_log_id,
    )
    heartbeat = await jobs.record_worker_heartbeat(
        worker_id=worker_id,
        pool="scheduler",
        concurrency=1,
        status="running",
        summary={
            "schema": "autoskill.deployment-readiness-smoke.scheduler.v1",
            "scheduler_ticks": 1,
            "runtime_skill_writes": False,
        },
    )
    return {
        "workspace_id": workspace_key,
        "broker_policy_version_id": str(policy.broker_policy_version_id),
        "replay_episode_id": str(replay.broker_replay_episode_id),
        "retrieval_log_id": str(retrieval_log_id),
        "scheduler_worker_id": heartbeat.worker_id,
    }


async def _call_readiness_route(
    *,
    database_url: str,
    jobs: AsyncpgJobStore,
    profiles: AsyncpgProfileStore,
    broker_policies: AsyncpgBrokerPolicyStore,
    workspace_key: str,
    replay_tag: str,
) -> Any:
    with _readiness_environment(database_url):
        app = create_app(
            job_store=jobs,
            profile_store=profiles,
            broker_policy_store=broker_policies,
            writer_workspace_root=ROOT,
        )
        route = next(
            route for route in app.routes if route.path == "/v1/deployment/readiness"
        )
        return await route.endpoint(
            authorization="Bearer deployment-readiness-smoke-control",
            workspace_id=workspace_key,
            replay_tag=replay_tag,
        )


@contextmanager
def _readiness_environment(database_url: str) -> Iterator[None]:
    updates = {
        "AUTOSKILL_DATABASE_URL": database_url,
        "AUTOSKILL_CONTROL_TOKEN": "deployment-readiness-smoke-control",
        "AUTOSKILL_INGEST_TOKEN": "deployment-readiness-smoke-ingest",
        "AUTOSKILL_LLM_API_BASE_URL": "http://127.0.0.1:9/v1",
        "AUTOSKILL_EMBEDDING_PROVIDER": "openai_compatible",
        "AUTOSKILL_EMBEDDING_API_BASE_URL": "http://127.0.0.1:9/v1",
        "AUTOSKILL_EMBEDDING_API_KEY": "deployment-readiness-smoke-key",
        "AUTOSKILL_RUNTIME_CONTEXT_BROKER_ENABLED": "true",
    }
    previous = {key: os.environ.get(key) for key in updates}
    try:
        os.environ.update(updates)
        get_settings.cache_clear()
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


def _summarize_response(
    *,
    response: dict[str, Any],
    seeded: dict[str, Any],
    smoke_id: str,
) -> dict[str, Any]:
    checks = response["checks"]
    key_checks = {
        name: _concise_check(name, _json_object(checks.get(name)))
        for name in REQUIRED_CHECKS
    }
    return {
        "schema": "autoskill.deployment-readiness-smoke.v1",
        "ok": bool(response["ready"]),
        "smoke_id": smoke_id,
        "workspace_id": response["workspace_id"],
        "blockers": response["blockers"],
        "warnings": response["warnings"],
        "key_checks": key_checks,
        "seeded_refs": seeded,
        "raw_evidence_returned": False,
        "runtime_skill_writes": False,
        "activation_authority": False,
        "live_openclaw_mutation": False,
    }


def _concise_check(name: str, check: dict[str, Any]) -> dict[str, Any]:
    if name == "storage_plane_schema_ready":
        return {
            "status": check.get("status"),
            "reachable": check.get("reachable"),
            "pgvector_available": check.get("pgvector_available"),
            "migration_version": check.get("migration_version"),
            "schema_contract": check.get("schema_contract"),
            "missing_tables": check.get("missing_tables"),
        }
    if name == "read_model_contract_compatible":
        return {
            "status": check.get("status"),
            "compatible": check.get("compatible"),
            "reason_code": check.get("reason_code"),
            "advertised_contract_version": check.get("advertised_contract_version"),
            "expected_contract_version": check.get("expected_contract_version"),
            "missing_catalogs": check.get("missing_catalogs"),
        }
    if name == "scheduler_worker_heartbeat":
        return {
            "status": check.get("status"),
            "observed": check.get("observed"),
            "ready_worker_ids": check.get("ready_worker_ids"),
        }
    if name == "active_executor_profile":
        return {
            "status": check.get("status"),
            "count": check.get("count"),
            "profile_keys": check.get("profile_keys"),
            "compatible_profiles": [
                _concise_executor_profile(profile)
                for profile in _json_objects(check.get("compatible_profiles"))
            ],
            "blocked_profiles": [
                _concise_executor_profile(profile)
                for profile in _json_objects(check.get("blocked_profiles"))
            ],
        }
    if name in {"qualified_text_model_profile", "active_embedding_profile"}:
        return {
            "status": check.get("status"),
            "count": check.get("count"),
            "profile_keys": check.get("profile_keys"),
        }
    if name == "active_broker_policy":
        return {
            "status": check.get("status"),
            "version": check.get("version"),
            "broker_policy_version_id": check.get("broker_policy_version_id"),
        }
    if name == "broker_replay_corpus":
        return {
            "status": check.get("status"),
            "sampled": check.get("sampled"),
            "operator_reviewed": check.get("operator_reviewed"),
            "source_linked": check.get("source_linked"),
            "telemetry_derived": check.get("telemetry_derived"),
            "degraded_fidelity": check.get("degraded_fidelity"),
            "expected_decisions": check.get("expected_decisions"),
        }
    if name == "operator_reviewed_broker_replay_corpus":
        return {
            "status": check.get("status"),
            "operator_reviewed": check.get("operator_reviewed"),
            "sampled": check.get("sampled"),
        }
    return {"status": check.get("status")}


def _assert_smoke(summary: dict[str, Any]) -> None:
    if summary["ok"] is not True:
        raise SystemExit(f"deployment readiness was not ready: {summary['blockers']}")
    if summary["blockers"]:
        raise SystemExit(f"deployment readiness reported blockers: {summary['blockers']}")
    for name, check in summary["key_checks"].items():
        if check.get("status") != "passed":
            raise SystemExit(f"readiness check did not pass: {name}={check}")
    storage = summary["key_checks"]["storage_plane_schema_ready"]
    if storage.get("pgvector_available") is not True:
        raise SystemExit("storage readiness did not observe pgvector")
    if storage.get("migration_version") != "0001_autoskill_schema":
        raise SystemExit("storage readiness did not observe the schema marker")
    read_model = summary["key_checks"]["read_model_contract_compatible"]
    if read_model.get("reason_code") != "read_model_contract_compatible":
        raise SystemExit("read-model compatibility did not report compatible")
    _assert_executor_profile_contract(summary["key_checks"]["active_executor_profile"])
    replay = summary["key_checks"]["broker_replay_corpus"]
    if replay.get("operator_reviewed") != 1 or replay.get("source_linked") != 1:
        raise SystemExit("operator-reviewed and telemetry-linked replay was not observed")
    if (
        summary["raw_evidence_returned"]
        or summary["runtime_skill_writes"]
        or summary["activation_authority"]
        or summary["live_openclaw_mutation"]
    ):
        raise SystemExit("smoke summary claimed an unsafe authority or mutation flag")


def _concise_executor_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {key: profile.get(key) for key in EXECUTOR_PROFILE_DETAIL_KEYS}


def _assert_executor_profile_contract(check: dict[str, Any]) -> None:
    compatible_profiles = check.get("compatible_profiles")
    if not isinstance(compatible_profiles, list) or not compatible_profiles:
        raise SystemExit(
            "executor profile readiness did not report compatibility detail"
        )
    if check.get("profile_keys") != ["deployment-readiness-smoke-executor"]:
        raise SystemExit(
            "executor profile readiness did not report the seeded profile key"
        )
    if check.get("blocked_profiles") != []:
        raise SystemExit("executor profile readiness reported blocked profiles")
    profile = _json_object(compatible_profiles[0])
    for key in EXECUTOR_PROFILE_DETAIL_KEYS:
        if key not in profile:
            raise SystemExit(f"executor profile readiness omitted {key}")
    expected_scalars = {
        "profile_key": "deployment-readiness-smoke-executor",
        "status": "active",
        "agent_backend": "codex",
        "model_family": "gpt",
        "sandbox": "danger-full-access",
        "os_name": "linux",
    }
    for key, value in expected_scalars.items():
        if profile.get(key) != value:
            raise SystemExit(f"executor profile readiness mismatched {key}")
    expected_members = {
        "tool_keys": "exec",
        "binary_keys": "git",
        "api_contract_keys": "skillkernel",
        "permission_keys": "filesystem",
    }
    for key, value in expected_members.items():
        members = profile.get(key)
        if not isinstance(members, list) or value not in members:
            raise SystemExit(f"executor profile readiness missed {key}")
    if not isinstance(profile.get("tool_count"), int) or profile["tool_count"] < 1:
        raise SystemExit("executor profile readiness missed tool count")
    if not isinstance(profile.get("binary_count"), int) or profile["binary_count"] < 2:
        raise SystemExit("executor profile readiness missed binary count")
    if (
        not isinstance(profile.get("api_contract_count"), int)
        or profile["api_contract_count"] < 1
    ):
        raise SystemExit("executor profile readiness missed API contract count")
    if profile.get("reason_codes") != []:
        raise SystemExit("executor profile readiness included unexpected reason codes")


async def _insert_content_safe_retrieval_log(
    *,
    database_url: str,
    workspace_key: str,
    broker_policy_version_id: UUID,
    smoke_id: str,
) -> UUID:
    conn = await asyncpg.connect(database_url)
    try:
        workspace_id = await ensure_workspace(conn, workspace_key)
        return await conn.fetchval(
            """
            INSERT INTO autoskill.retrieval_logs (
              retrieval_log_id,
              workspace_id,
              broker_policy_version_id,
              decision,
              candidate_skill_ids,
              rendered_skill_ids,
              no_skill_control,
              metadata
            )
            VALUES (
              gen_random_uuid(),
              $1,
              $2,
              'skill_hint',
              '{}'::uuid[],
              '{}'::uuid[],
              false,
              $3::jsonb
            )
            RETURNING retrieval_log_id
            """,
            workspace_id,
            broker_policy_version_id,
            json.dumps(
                {
                    "schema": "autoskill.deployment-readiness-smoke.retrieval.v1",
                    "smoke_id": smoke_id,
                    "query_hash": f"sha256:{smoke_id}",
                    "content_safe": True,
                },
                sort_keys=True,
            ),
        )
    finally:
        await conn.close()


async def _apply_migration(database_url: str) -> None:
    migration = (ROOT / "migrations" / "0001_autoskill_schema.sql").read_text(
        encoding="utf-8"
    )
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(migration)
    finally:
        await conn.close()


async def _delete_smoke_workspace(
    database_url: str,
    workspace_key: str,
    worker_id: str,
) -> None:
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(
            "DELETE FROM autoskill.worker_heartbeats WHERE worker_id = $1",
            worker_id,
        )
        workspace_id = await conn.fetchval(
            "SELECT workspace_id FROM autoskill.workspaces WHERE external_key = $1",
            workspace_key,
        )
        if workspace_id is None:
            return
        async with conn.transaction():
            for statement in (
                "DELETE FROM autoskill.broker_replay_episodes WHERE workspace_id = $1",
                "DELETE FROM autoskill.retrieval_events WHERE workspace_id = $1",
                "DELETE FROM autoskill.retrieval_logs WHERE workspace_id = $1",
                "DELETE FROM autoskill.broker_policy_versions WHERE workspace_id = $1",
                "DELETE FROM autoskill.embedding_profiles WHERE workspace_id = $1",
                "DELETE FROM autoskill.text_model_profiles WHERE workspace_id = $1",
                "DELETE FROM autoskill.model_profiles WHERE workspace_id = $1",
                "DELETE FROM autoskill.executor_profiles WHERE workspace_id = $1",
                "DELETE FROM autoskill.jobs WHERE workspace_id = $1",
                "DELETE FROM autoskill.memory_contracts WHERE workspace_id = $1",
                "DELETE FROM autoskill.workspaces WHERE workspace_id = $1",
            ):
                await conn.execute(statement, workspace_id)
    finally:
        await conn.close()


def _json_object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_objects(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _default_database_url() -> str:
    explicit = os.environ.get("AUTOSKILL_DATABASE_URL") or os.environ.get(
        "SKILLKERNEL_DATABASE_URL"
    )
    if explicit:
        return explicit
    password = os.environ.get("AUTOSKILL_POSTGRES_PASSWORD", "autoskill-dev")
    return f"postgresql://autoskill:{password}@127.0.0.1:55432/autoskill"


if __name__ == "__main__":
    main()
