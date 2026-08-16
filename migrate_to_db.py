"""One-time legacy CSV bootstrap for local development.

IMPORTANT:
- This script is NOT a Render/production build step.
- Production/Render deployments must use the configured PostgreSQL/Neon DATABASE_URL
  and let app.main.ensure_schema() perform only non-destructive schema upgrades.
- The script refuses to import CSV data when running in production/Render so an old
  Render Build Command cannot silently overwrite the Neon database.
"""

from __future__ import annotations

import os

import pandas as pd
from sqlalchemy import select

from app.database import ActualDB, Base, RequirementDB, SessionLocal, engine
from app.main import ensure_schema


FIELDS = ("beds", "mattresses", "closets", "ac_units", "ac_remotes")


def _is_production() -> bool:
    environment = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "")).strip().lower()
    render = os.getenv("RENDER", "").strip().lower()
    return environment in {"production", "prod"} or render == "true"


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
    if _is_production():
        raise SystemExit(
            "Refusing CSV-to-DB migration in production/Render. "
            "Use DATABASE_URL pointing to Neon and let the application perform "
            "the non-destructive schema upgrade."
        )

    Base.metadata.create_all(bind=engine)
    ensure_schema()
    with SessionLocal.begin() as session:
        migrate_requirements(session)
        migrate_actuals(session)
    print("Migration completed safely. No tables were replaced.")


if __name__ == "__main__":
    main()
