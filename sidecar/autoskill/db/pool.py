from __future__ import annotations

import os

import asyncpg


class AsyncpgPoolOwner:
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        self._database_url = database_url
        self._statement_timeout_ms = statement_timeout_ms
        self._pool: asyncpg.Pool | None = None

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._database_url,
                min_size=_env_int("AUTOSKILL_DB_POOL_MIN_SIZE", 0),
                max_size=_env_int("AUTOSKILL_DB_POOL_MAX_SIZE", 1),
                server_settings={"statement_timeout": str(self._statement_timeout_ms)},
            )
        return self._pool


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed >= 0 else default
