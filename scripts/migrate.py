#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Protocol

import asyncpg

ROOT = Path(__file__).resolve().parents[1]


class MigrationConnection(Protocol):
    async def execute(self, query: str) -> str:
        """Execute one SQL statement."""


def split_sql_statements(sql: str) -> list[str]:
    """Split the bootstrap SQL without breaking quoted strings or dollar blocks."""
    statements: list[str] = []
    start = 0
    index = 0
    dollar_tag: str | None = None
    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False
    length = len(sql)

    while index < length:
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < length else ""

        if in_line_comment:
            if char == "\n":
                in_line_comment = False
            index += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
                continue
            index += 1
            continue

        if dollar_tag is not None:
            if sql.startswith(dollar_tag, index):
                index += len(dollar_tag)
                dollar_tag = None
                continue
            index += 1
            continue

        if in_single_quote:
            if char == "'":
                if next_char == "'":
                    index += 2
                    continue
                in_single_quote = False
            index += 1
            continue

        if in_double_quote:
            if char == '"':
                if next_char == '"':
                    index += 2
                    continue
                in_double_quote = False
            index += 1
            continue

        if char == "-" and next_char == "-":
            in_line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue
        if char == "'":
            in_single_quote = True
            index += 1
            continue
        if char == '"':
            in_double_quote = True
            index += 1
            continue
        if char == "$":
            tag_end = sql.find("$", index + 1)
            if tag_end != -1:
                tag = sql[index : tag_end + 1]
                tag_name = tag[1:-1]
                if tag == "$$" or (
                    tag_name
                    and (tag_name[0].isalpha() or tag_name[0] == "_")
                    and all(char.isalnum() or char == "_" for char in tag_name)
                ):
                    dollar_tag = tag
                    index = tag_end + 1
                    continue
        if char == ";":
            statement = sql[start : index + 1].strip()
            if statement:
                statements.append(statement)
            start = index + 1
        index += 1

    tail = sql[start:].strip()
    if tail:
        statements.append(tail)
    return statements


async def run_migration(conn: MigrationConnection, migration: str) -> None:
    for index, statement in enumerate(split_sql_statements(migration), start=1):
        try:
            await conn.execute(statement)
        except Exception:
            preview = " ".join(statement.split())[:240]
            print(
                f"migration statement {index} failed: {preview}",
                file=sys.stderr,
            )
            raise


async def main() -> None:
    dsn = os.environ.get("AUTOSKILL_DATABASE_URL")
    if not dsn:
        raise SystemExit("AUTOSKILL_DATABASE_URL is required")
    migration = (ROOT / "migrations" / "0001_autoskill_schema.sql").read_text(encoding="utf-8")
    conn = await asyncpg.connect(dsn)
    try:
        await run_migration(conn, migration)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
