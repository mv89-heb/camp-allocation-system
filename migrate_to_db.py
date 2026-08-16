"""Idempotently migrate legacy CSV data into the canonical database schema.

This script never uses if_exists='replace' and therefore does not destroy existing
rows or ORM constraints. Run it once after deploying the hardened version.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select

from app.database import ActualDB, Base, RequirementDB, SessionLocal, engine
from app.main import ensure_schema


FIELDS = ("beds", "mattresses", "closets", "ac_units", "ac_remotes")


def non_negative(value, default=0) -> int:
    try:
        if pd.isna(value):
            return default
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


def migrate_requirements(session):
    df = pd.read_csv("data/inventory.csv").fillna(0)
    if "apartment" not in df.columns:
        raise ValueError("data/inventory.csv must contain apartment")

    for _, row in df.iterrows():
        apartment = str(row["apartment"]).strip()
        if not apartment:
            continue
        existing = session.get(RequirementDB, apartment)
        plan = {field: non_negative(row.get(field, 0)) for field in FIELDS}
        std = {
            field: min(plan[field], 4 if field != "ac_remotes" else 1)
            for field in FIELDS
        }
        values = {}
        for field in FIELDS:
            values[f"{field}_std"] = std[field]
            values[f"{field}_plan"] = plan[field]

        if existing is None:
            session.add(RequirementDB(apartment=apartment, **values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)


def migrate_actuals(session):
    try:
        df = pd.read_csv("data/actual_inventory.csv").fillna(0)
    except FileNotFoundError:
        return
    if "apartment" not in df.columns:
        return

    for _, row in df.iterrows():
        apartment = str(row["apartment"]).strip()
        if not apartment:
            continue
        values = {field: non_negative(row.get(field, 0)) for field in FIELDS}
        existing = session.get(ActualDB, apartment)
        if existing is None:
            session.add(ActualDB(apartment=apartment, **values))
        else:
            for field, value in values.items():
                setattr(existing, field, value)


def main():
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    with SessionLocal.begin() as session:
        migrate_requirements(session)
        migrate_actuals(session)
    print("Migration completed safely. No tables were replaced.")


if __name__ == "__main__":
    main()
