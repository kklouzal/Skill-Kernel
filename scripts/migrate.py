#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    dsn = os.environ.get("AUTOSKILL_DATABASE_URL")
    if not dsn:
        raise SystemExit("AUTOSKILL_DATABASE_URL is required")
    migration = (ROOT / "migrations" / "0001_autoskill_schema.sql").read_text(encoding="utf-8")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(migration)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
