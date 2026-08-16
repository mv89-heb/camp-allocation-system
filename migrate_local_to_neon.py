"""Copy an existing local SQLite database into the configured Neon/PostgreSQL database.

Usage (PowerShell):
  $env:SOURCE_DATABASE_URL="sqlite:///./data/inventory.db"
  $env:DATABASE_URL="postgresql://..."
  python migrate_local_to_neon.py

The target database is never dropped. Existing rows are updated by primary key
for the supported tables. The script is intended for the one-time move from a
local development DB to Neon.
"""

from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import MetaData, create_engine, inspect, select, text

SOURCE_DATABASE_URL = os.getenv("SOURCE_DATABASE_URL", "sqlite:///./data/inventory.db").strip()
TARGET_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not TARGET_DATABASE_URL:
    raise RuntimeError("DATABASE_URL must point to the Neon PostgreSQL database")
if TARGET_DATABASE_URL.startswith("postgres://"):
    TARGET_DATABASE_URL = TARGET_DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not TARGET_DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    raise RuntimeError("DATABASE_URL must be a PostgreSQL/Neon connection string")

source_engine = create_engine(SOURCE_DATABASE_URL, future=True)

# Import after DATABASE_URL is present so app.database targets Neon.
from app.database import Base, engine as target_engine  # noqa: E402
from app.main import ensure_schema  # noqa: E402


def _rows(connection, table_name: str):
    inspector = inspect(connection)
    if not inspector.has_table(table_name):
        return []
    table = MetaData().tables
    metadata = MetaData()
    source_table = __import__("sqlalchemy").Table(table_name, metadata, autoload_with=connection)
    return connection.execute(select(source_table)).mappings().all()


def _copy_table(source_connection, target_connection, table_name: str) -> int:
    source_inspector = inspect(source_connection)
    target_inspector = inspect(target_connection)
    if not source_inspector.has_table(table_name) or not target_inspector.has_table(table_name):
        return 0

    source_meta = MetaData()
    target_meta = MetaData()
    from sqlalchemy import Table

    source_table = Table(table_name, source_meta, autoload_with=source_connection)
    target_table = Table(table_name, target_meta, autoload_with=target_connection)
    source_columns = {c.name for c in source_table.columns}
    target_columns = {c.name for c in target_table.columns}

    rows = source_connection.execute(select(source_table)).mappings().all()
    if not rows:
        return 0

    # requirements is the one legacy table whose old schema used unsuffixed fields.
    if table_name == "requirements" and "beds" in source_columns:
        transformed = []
        caps = {"beds": 4, "mattresses": 4, "closets": 4, "ac_units": 4, "ac_remotes": 1}
        for row in rows:
            item = {"apartment": str(row["apartment"]).strip()}
            for field, cap in caps.items():
                value = row.get(field, 0) or 0
                value = max(0, int(value))
                item[f"{field}_plan"] = value
                item[f"{field}_std"] = min(value, cap)
            transformed.append(item)
        rows = transformed
    else:
        rows = [{key: value for key, value in row.items() if key in target_columns} for row in rows]

    rows = [{key: value for key, value in row.items() if key in target_columns} for row in rows]
    if not rows:
        return 0

    # Explicit row-by-row merge keeps the migration idempotent and avoids destructive
    # to_sql(..., if_exists="replace") behavior.
    pk_columns = [column.name for column in target_table.primary_key.columns]
    for row in rows:
        if not pk_columns:
            target_connection.execute(target_table.insert().values(**row))
            continue
        where = [target_table.c[key] == row[key] for key in pk_columns if key in row]
        existing = target_connection.execute(select(target_table).where(*where).limit(1)).first() if where else None
        if existing:
            non_pk = {k: v for k, v in row.items() if k not in pk_columns}
            if non_pk:
                target_connection.execute(target_table.update().where(*where).values(**non_pk))
        else:
            target_connection.execute(target_table.insert().values(**row))
    return len(rows)


def main() -> None:
    print("Starting local SQLite -> Neon migration...")
    ensure_schema()
    Base.metadata.create_all(bind=target_engine)

    supported_tables = (
        "requirements",
        "actuals",
        "inventory_audit",
        "damage_reports",
        "damage_audit",
    )

    with source_engine.connect() as source_connection, target_engine.begin() as target_connection:
        totals = {}
        for table_name in supported_tables:
            totals[table_name] = _copy_table(source_connection, target_connection, table_name)

        # Restore PostgreSQL sequences after copying explicit integer IDs.
        for table_name in ("inventory_audit", "damage_reports", "damage_audit"):
            if inspect(target_connection).has_table(table_name):
                target_connection.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM {table_name}), 1), true)"
                    )
                )

    print("Migration completed successfully.")
    for table_name, count in totals.items():
        print(f"  {table_name}: {count} rows processed")


if __name__ == "__main__":
    main()
