"""
Database migration runner for NovaFlow Customer Success FTE.
Migrations live in database/migrations/ numbered sequentially.

Usage:
    python database/migrate.py up            # Apply all pending migrations
    python database/migrate.py status        # Show applied/pending migrations
    python database/migrate.py down --steps 1  # Roll back N migrations (runs DOWN block)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
MIGRATIONS_TABLE = "schema_migrations"


async def ensure_migrations_table(conn: asyncpg.Connection) -> None:
    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(255) NOT NULL UNIQUE,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


async def get_applied(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch(f"SELECT name FROM {MIGRATIONS_TABLE}")
    return {r["name"] for r in rows}


def load_migration_files() -> list[Path]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return files


def extract_up_block(sql: str) -> str:
    """Return everything before the DOWN section."""
    down_marker = re.search(r"--\s*={10,}\s*\n--\s*DOWN", sql)
    if down_marker:
        return sql[: down_marker.start()]
    return sql


def extract_down_block(sql: str) -> str:
    """Return the uncommented DROP statements from the DOWN section."""
    down_marker = re.search(r"--\s*={10,}\s*\n--\s*DOWN.*?\n(.*)", sql, re.DOTALL)
    if not down_marker:
        return ""
    down_section = down_marker.group(1)
    lines = []
    for line in down_section.splitlines():
        stripped = line.lstrip("-- ").strip()
        if stripped.upper().startswith(("DROP", "ALTER", "DELETE", "TRUNCATE")):
            lines.append(stripped)
    return "\n".join(lines)


async def cmd_up(conn: asyncpg.Connection) -> None:
    await ensure_migrations_table(conn)
    applied = await get_applied(conn)
    files = load_migration_files()
    pending = [f for f in files if f.name not in applied]

    if not pending:
        print("✅ All migrations already applied.")
        return

    for migration_file in pending:
        sql = migration_file.read_text(encoding="utf-8")
        up_sql = extract_up_block(sql)
        print(f"  Applying {migration_file.name} ...", end=" ")
        async with conn.transaction():
            await conn.execute(up_sql)
            await conn.execute(
                f"INSERT INTO {MIGRATIONS_TABLE} (name) VALUES ($1)",
                migration_file.name,
            )
        print("✅")

    print(f"\nApplied {len(pending)} migration(s).")


async def cmd_status(conn: asyncpg.Connection) -> None:
    await ensure_migrations_table(conn)
    applied = await get_applied(conn)
    files = load_migration_files()

    print(f"\n{'Migration':<45} {'Status'}")
    print("-" * 58)
    for f in files:
        status = "✅ applied" if f.name in applied else "⏳ pending"
        print(f"  {f.name:<43} {status}")
    print()


async def cmd_down(conn: asyncpg.Connection, steps: int) -> None:
    await ensure_migrations_table(conn)
    rows = await conn.fetch(
        f"SELECT name FROM {MIGRATIONS_TABLE} ORDER BY id DESC LIMIT $1", steps
    )
    if not rows:
        print("Nothing to roll back.")
        return

    for row in rows:
        name = row["name"]
        migration_file = MIGRATIONS_DIR / name
        if not migration_file.exists():
            print(f"⚠️  Migration file {name} not found — skipping rollback.")
            continue

        sql = migration_file.read_text(encoding="utf-8")
        down_sql = extract_down_block(sql)
        if not down_sql:
            print(f"⚠️  No DOWN block found in {name} — skipping.")
            continue

        print(f"  Rolling back {name} ...", end=" ")
        async with conn.transaction():
            await conn.execute(down_sql)
            await conn.execute(
                f"DELETE FROM {MIGRATIONS_TABLE} WHERE name = $1", name
            )
        print("✅")


async def main() -> None:
    parser = argparse.ArgumentParser(description="FTE database migration runner")
    parser.add_argument("command", choices=["up", "status", "down"])
    parser.add_argument("--steps", type=int, default=1, help="Number of migrations to roll back")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL environment variable not set.")
        sys.exit(1)

    conn = await asyncpg.connect(database_url)
    try:
        if args.command == "up":
            await cmd_up(conn)
        elif args.command == "status":
            await cmd_status(conn)
        elif args.command == "down":
            await cmd_down(conn, args.steps)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
