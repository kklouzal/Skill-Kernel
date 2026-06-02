#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg

DEFAULT_TAGS = ["production", "dev-01-canary", "redacted", "telemetry-derived"]
SCHEMA = "autoskill.replay_corpus.v1"


@dataclass(frozen=True)
class ReplayCandidate:
    retrieval_log_id: str
    created_at: str
    decision: str
    query_hash: str | None
    reason_codes: list[str]
    candidate_skill_ids: list[str]
    rendered_skill_ids: list[str]
    rendered_skill_slugs: list[str]
    candidate_count: int
    rendered_skill_count: int
    already_recorded: bool
    query_hash_recorded: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "retrieval_log_id": self.retrieval_log_id,
            "created_at": self.created_at,
            "decision": self.decision,
            "query_hash": self.query_hash,
            "reason_codes": self.reason_codes,
            "candidate_skill_ids": self.candidate_skill_ids,
            "rendered_skill_ids": self.rendered_skill_ids,
            "rendered_skill_slugs": self.rendered_skill_slugs,
            "candidate_count": self.candidate_count,
            "rendered_skill_count": self.rendered_skill_count,
            "already_recorded": self.already_recorded,
            "query_hash_recorded": self.query_hash_recorded,
        }


def main() -> None:
    args = _parse_args()
    if args.command == "candidates":
        result = asyncio.run(_list_candidates(args))
    elif args.command == "record":
        result = asyncio.run(_record_from_plan(args))
    else:  # pragma: no cover - argparse enforces choices
        raise SystemExit(f"unknown command: {args.command}")
    print(json.dumps(result, indent=2, sort_keys=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build broker replay corpus entries from content-safe retrieval telemetry. "
            "The script never reconstructs raw prompts; record mode requires an explicit "
            "operator-supplied redacted intent for each episode."
        )
    )
    parser.add_argument("--database-url", default=_default_database_url())
    subparsers = parser.add_subparsers(dest="command", required=True)

    candidates = subparsers.add_parser("candidates", help="List content-safe replay candidates")
    candidates.add_argument("--workspace-id", default="dev-01")
    candidates.add_argument("--limit", type=int, default=50)
    candidates.add_argument(
        "--decision",
        choices=["all", "skill_hint", "no_skill"],
        default="skill_hint",
        help="Filter retrieval logs by broker decision.",
    )
    candidates.add_argument(
        "--include-recorded",
        action="store_true",
        help="Include logs or query hashes already represented in replay episodes.",
    )
    candidates.add_argument(
        "--distinct-query-hash",
        action="store_true",
        help="Return only the newest candidate for each query hash.",
    )

    record = subparsers.add_parser("record", help="Record replay episodes from a JSON plan")
    record.add_argument("--plan", required=True, help="Path to replay plan JSON.")
    record.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _default_database_url() -> str:
    explicit = os.environ.get("AUTOSKILL_DATABASE_URL")
    if explicit:
        return explicit
    password = os.environ.get("AUTOSKILL_POSTGRES_PASSWORD", "autoskill-dev")
    return f"postgresql://autoskill:{password}@127.0.0.1:55432/autoskill"


async def _list_candidates(args: argparse.Namespace) -> dict[str, Any]:
    limit = max(1, min(args.limit, 500))
    conn = await asyncpg.connect(args.database_url)
    try:
        rows = await conn.fetch(
            """
            WITH selected AS (
              SELECT
                rl.retrieval_log_id,
                rl.created_at,
                rl.decision,
                rl.candidate_skill_ids,
                rl.rendered_skill_ids,
                rl.metadata,
                rl.metadata->>'query_hash' AS query_hash,
                EXISTS (
                  SELECT 1
                  FROM autoskill.broker_replay_episodes bre
                  WHERE bre.source_retrieval_log_id = rl.retrieval_log_id
                ) AS already_recorded,
                EXISTS (
                  SELECT 1
                  FROM autoskill.broker_replay_episodes bre
                  WHERE bre.metadata->>'source_query_hash' = rl.metadata->>'query_hash'
                ) AS query_hash_recorded,
                row_number() OVER (
                  PARTITION BY COALESCE(rl.metadata->>'query_hash', rl.retrieval_log_id::text)
                  ORDER BY rl.created_at DESC
                ) AS query_hash_rank
              FROM autoskill.retrieval_logs rl
              JOIN autoskill.workspaces w ON w.workspace_id = rl.workspace_id
              WHERE w.external_key = $1
                AND ($2::text = 'all' OR rl.decision = $2::text)
            )
            SELECT
              s.*,
              COALESCE(
                array_agg(sk.slug ORDER BY sk.slug)
                  FILTER (WHERE sk.slug IS NOT NULL),
                '{}'::text[]
              ) AS rendered_skill_slugs
            FROM selected s
            LEFT JOIN autoskill.skills sk ON sk.skill_id = ANY(s.rendered_skill_ids)
            WHERE ($4::bool OR (NOT s.already_recorded AND NOT s.query_hash_recorded))
              AND (NOT $5::bool OR s.query_hash_rank = 1)
            GROUP BY
              s.retrieval_log_id,
              s.created_at,
              s.decision,
              s.candidate_skill_ids,
              s.rendered_skill_ids,
              s.metadata,
              s.already_recorded,
              s.query_hash_recorded,
              s.query_hash,
              s.query_hash_rank
            ORDER BY s.created_at DESC
            LIMIT $3
            """,
            args.workspace_id,
            args.decision,
            limit,
            args.include_recorded,
            args.distinct_query_hash,
        )
    finally:
        await conn.close()

    candidates = [_candidate_from_row(row).to_json() for row in rows]
    return {
        "schema": SCHEMA,
        "workspace_id": args.workspace_id,
        "decision": args.decision,
        "count": len(candidates),
        "candidates": candidates,
        "plan_template": {
            "workspace_id": args.workspace_id,
            "default_tags": DEFAULT_TAGS,
            "episodes": [
                {
                    "source_retrieval_log_id": "<retrieval_log_id>",
                    "redacted_user_intent": "<operator-redacted-intent>",
                }
            ],
        },
    }


def _candidate_from_row(row: asyncpg.Record) -> ReplayCandidate:
    metadata = _json_dict(row["metadata"])
    reason_codes = metadata.get("reason_codes")
    if not isinstance(reason_codes, list):
        reason_codes = []
    candidate_skill_ids = [str(item) for item in (row["candidate_skill_ids"] or [])]
    rendered_skill_ids = [str(item) for item in (row["rendered_skill_ids"] or [])]
    return ReplayCandidate(
        retrieval_log_id=str(row["retrieval_log_id"]),
        created_at=row["created_at"].isoformat(),
        decision=row["decision"],
        query_hash=_optional_str(metadata.get("query_hash")),
        reason_codes=[str(item) for item in reason_codes],
        candidate_skill_ids=candidate_skill_ids,
        rendered_skill_ids=rendered_skill_ids,
        rendered_skill_slugs=[str(item) for item in (row["rendered_skill_slugs"] or [])],
        candidate_count=len(candidate_skill_ids),
        rendered_skill_count=len(rendered_skill_ids),
        already_recorded=bool(row["already_recorded"]),
        query_hash_recorded=bool(row["query_hash_recorded"]),
    )


async def _record_from_plan(args: argparse.Namespace) -> dict[str, Any]:
    plan_path = Path(args.plan)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    workspace_id = _required_str(plan, "workspace_id")
    default_tags = _tags(plan.get("default_tags", DEFAULT_TAGS))
    episodes = plan.get("episodes")
    if not isinstance(episodes, list) or not episodes:
        raise SystemExit("plan must contain a non-empty episodes list")

    conn = await asyncpg.connect(args.database_url)
    recorded: list[dict[str, Any]] = []
    try:
        for item in episodes:
            if not isinstance(item, dict):
                raise SystemExit("each episode must be an object")
            source_id = UUID(_required_str(item, "source_retrieval_log_id"))
            redacted_intent = _required_redacted_intent(item)
            row = await _fetch_retrieval_log(conn, workspace_id, source_id)
            episode_key = str(item.get("episode_key") or f"telemetry-{str(source_id)[:12]}")
            expected_decision = str(item.get("expected_decision") or row["decision"])
            expected_skill_ids = [
                UUID(str(value))
                for value in item.get("expected_skill_ids", row["rendered_skill_ids"] or [])
            ]
            tags = _tags([*default_tags, *item.get("tags", [])])
            metadata = _episode_metadata(item, row, plan_path)
            payload = {
                "episode_key": episode_key,
                "redacted_user_intent": redacted_intent,
                "expected_decision": expected_decision,
                "expected_skill_ids": [str(value) for value in expected_skill_ids],
                "tags": tags,
                "metadata": metadata,
                "source_retrieval_log_id": str(source_id),
            }
            if not args.dry_run:
                inserted = await _upsert_episode(
                    conn,
                    workspace_id=workspace_id,
                    source_retrieval_log_id=source_id,
                    episode_key=episode_key,
                    redacted_user_intent=redacted_intent,
                    expected_decision=expected_decision,
                    expected_skill_ids=expected_skill_ids,
                    tags=tags,
                    metadata=metadata,
                )
                payload["broker_replay_episode_id"] = str(inserted["broker_replay_episode_id"])
            recorded.append(payload)
    finally:
        await conn.close()

    return {
        "schema": SCHEMA,
        "dry_run": bool(args.dry_run),
        "workspace_id": workspace_id,
        "recorded": recorded,
        "count": len(recorded),
    }


async def _fetch_retrieval_log(
    conn: asyncpg.Connection,
    workspace_id: str,
    source_id: UUID,
) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        SELECT rl.*
        FROM autoskill.retrieval_logs rl
        JOIN autoskill.workspaces w ON w.workspace_id = rl.workspace_id
        WHERE w.external_key = $1
          AND rl.retrieval_log_id = $2
        """,
        workspace_id,
        source_id,
    )
    if row is None:
        raise SystemExit(f"retrieval log not found for workspace {workspace_id}: {source_id}")
    return row


async def _upsert_episode(
    conn: asyncpg.Connection,
    *,
    workspace_id: str,
    source_retrieval_log_id: UUID,
    episode_key: str,
    redacted_user_intent: str,
    expected_decision: str,
    expected_skill_ids: list[UUID],
    tags: list[str],
    metadata: dict[str, Any],
) -> asyncpg.Record:
    return await conn.fetchrow(
        """
        WITH workspace AS (
          SELECT workspace_id
          FROM autoskill.workspaces
          WHERE external_key = $1
        )
        INSERT INTO autoskill.broker_replay_episodes (
          broker_replay_episode_id,
          workspace_id,
          source_retrieval_log_id,
          episode_key,
          redacted_user_intent,
          expected_decision,
          expected_skill_ids,
          tags,
          metadata
        )
        SELECT
          gen_random_uuid(),
          workspace.workspace_id,
          $2,
          $3,
          $4,
          $5,
          $6,
          $7,
          $8::jsonb
        FROM workspace
        ON CONFLICT (workspace_id, episode_key)
        DO UPDATE SET
          source_retrieval_log_id = EXCLUDED.source_retrieval_log_id,
          redacted_user_intent = EXCLUDED.redacted_user_intent,
          expected_decision = EXCLUDED.expected_decision,
          expected_skill_ids = EXCLUDED.expected_skill_ids,
          tags = EXCLUDED.tags,
          metadata = EXCLUDED.metadata
        RETURNING broker_replay_episode_id
        """,
        workspace_id,
        source_retrieval_log_id,
        episode_key,
        redacted_user_intent,
        expected_decision,
        expected_skill_ids,
        tags,
        json.dumps(metadata, sort_keys=True, separators=(",", ":")),
    )


def _episode_metadata(
    item: dict[str, Any],
    row: asyncpg.Record,
    plan_path: Path,
) -> dict[str, Any]:
    source_metadata = _json_dict(row["metadata"])
    metadata = _json_dict(item.get("metadata", {}))
    metadata.update(
        {
            "source": "retrieval_log",
            "source_created_at": row["created_at"].isoformat(),
            "source_decision": row["decision"],
            "source_query_hash": source_metadata.get("query_hash"),
            "source_reason_codes": source_metadata.get("reason_codes", []),
            "source_candidate_count": len(row["candidate_skill_ids"] or []),
            "source_rendered_skill_count": len(row["rendered_skill_ids"] or []),
            "plan_file": str(plan_path),
        }
    )
    return metadata


def _required_redacted_intent(item: dict[str, Any]) -> str:
    intent = _required_str(item, "redacted_user_intent")
    if len(intent) < 3:
        raise SystemExit("redacted_user_intent must be at least 3 characters")
    if any(marker in intent.lower() for marker in ("sk-", "password", "authorization:", "bearer ")):
        raise SystemExit("redacted_user_intent appears to contain sensitive material")
    return intent


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"missing required string field: {key}")
    return value.strip()


def _tags(values: Any) -> list[str]:
    if not isinstance(values, list):
        raise SystemExit("tags/default_tags must be lists")
    seen: set[str] = set()
    tags: list[str] = []
    for value in values:
        tag = str(value).strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


def _json_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    return dict(value)


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


if __name__ == "__main__":
    main()
