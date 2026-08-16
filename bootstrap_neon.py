"""Restore the repository's preserved room/inventory snapshot into Neon safely.

This is intentionally idempotent:
- never drops or replaces tables;
- never overwrites an existing verified room;
- creates missing requirement/actual rows from the versioned CSV snapshots;
- repairs only legacy all-zero actual rows that have never been checked when the
  preserved snapshot contains real physical counts.

Run once after configuring DATABASE_URL, or safely on each Render start.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

from sqlalchemy import select

from app.database import ActualDB, Base, RequirementDB, SessionLocal, engine, utc_now
from app.main import ensure_schema

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
FIELDS = ("beds", "mattresses", "closets", "ac_units", "ac_remotes")


def read_csv(name: str) -> list[dict[str, str]]:
    path = DATA / name
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def number(row: dict[str, str], key: str) -> int:
    raw = (row.get(key) or "").strip()
    if not raw:
        return 0
    return max(0, int(float(raw)))


def main() -> None:
    if not os.getenv("DATABASE_URL", "").strip():
        raise RuntimeError("DATABASE_URL must be configured before bootstrapping Neon")

    ensure_schema()
    Base.metadata.create_all(bind=engine)

    requirements = read_csv("inventory.csv")
    actual_snapshot = {
        (r.get("apartment") or "").strip(): r
        for r in read_csv("actual_inventory.csv")
        if (r.get("apartment") or "").strip()
    }

    db = SessionLocal()
    now = utc_now()
    added_req = added_actual = repaired_actual = 0
    try:
        existing_req = {r.apartment: r for r in db.scalars(select(RequirementDB)).all()}
        existing_actual = {r.apartment: r for r in db.scalars(select(ActualDB)).all()}

        for row in requirements:
            apartment = (row.get("apartment") or "").strip()
            if not apartment:
                continue

            planned = {field: number(row, field) for field in FIELDS}
            if apartment not in existing_req:
                db.add(RequirementDB(
                    apartment=apartment,
                    beds_plan=planned["beds"],
                    mattresses_plan=planned["mattresses"],
                    closets_plan=planned["closets"],
                    ac_units_plan=planned["ac_units"],
                    ac_remotes_plan=planned["ac_remotes"],
                    beds_std=min(planned["beds"], 4),
                    mattresses_std=min(planned["mattresses"], 4),
                    closets_std=min(planned["closets"], 4),
                    ac_units_std=min(planned["ac_units"], 4),
                    ac_remotes_std=min(planned["ac_remotes"], 1),
                ))
                added_req += 1

            snapshot = actual_snapshot.get(apartment)
            if not snapshot:
                continue

            values = {field: number(snapshot, field) for field in FIELDS}
            actual = existing_actual.get(apartment)
            if actual is None:
                verified = any(values.values())
                db.add(ActualDB(
                    apartment=apartment,
                    **values,
                    checked_at=now if verified else None,
                    checked_by="repository-bootstrap" if verified else None,
                ))
                added_actual += 1
            elif actual.checked_at is None:
                current = {field: int(getattr(actual, field) or 0) for field in FIELDS}
                if all(v == 0 for v in current.values()) and any(values.values()):
                    for field, value in values.items():
                        setattr(actual, field, value)
                    actual.checked_at = now
                    actual.checked_by = "repository-bootstrap"
                    repaired_actual += 1

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(
        "Neon bootstrap complete: "
        f"requirements_added={added_req}, "
        f"actuals_added={added_actual}, "
        f"actuals_repaired={repaired_actual}"
    )


if __name__ == "__main__":
    main()
