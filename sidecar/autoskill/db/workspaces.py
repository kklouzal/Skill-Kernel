from __future__ import annotations

from uuid import UUID

import asyncpg


async def ensure_workspace(conn: asyncpg.Connection, external_key: str) -> UUID:
    return await conn.fetchval(
        """
        INSERT INTO autoskill.workspaces (workspace_id, external_key)
        VALUES (gen_random_uuid(), $1)
        ON CONFLICT (external_key) DO UPDATE
        SET external_key = EXCLUDED.external_key
        RETURNING workspace_id
        """,
        external_key,
    )
