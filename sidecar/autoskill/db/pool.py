from __future__ import annotations

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
                server_settings={"statement_timeout": str(self._statement_timeout_ms)},
            )
        return self._pool
