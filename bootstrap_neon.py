"""Safely reconcile repository inventory snapshots with Neon.

Physical inventory stays at room level. The official standard is attached to an
explicit standard unit, which may contain one room or multiple rooms such as
101-102. This file is idempotent and never overwrites a physically checked room.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

from sqlalchemy import select

from app.database import ActualDB, Base, RequirementDB, SessionLocal, engine
from app.main import ensure_schema

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
FIELDS = ("beds", "mattresses", "closets", "ac_units", "ac_remotes")
STD_CAPS = {"beds": 4, "mattresses": 4, "closets": 4, "ac_units": 4, "ac_remotes": 1}


def read_csv(name: str) -> list[dict[str, str]]:
    path = DATA / name
    if not path.exists():
        raise RuntimeError(f"Required repository snapshot is missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def number_or_none(row: dict[str, str], key: str) -> int | None:
    raw = (row.get(key) or "").strip()
    if not raw:
        return None
    return max(0, int(float(raw)))


def number(row: dict[str, str], key: str) -> int:
    value = number_or_none(row, key)
    return 0 if value is None else value


def requirement_values(row: dict[str, str]) -> dict[str, int]:
    planned = {field: number(row, field) for field in FIELDS}
    return {
        **{f"{field}_plan": planned[field] for field in FIELDS},
        **{f"{field}_std": min(planned[field], STD_CAPS[field]) for field in FIELDS},
    }


def actual_values(row: dict[str, str]) -> dict[str, int]:
    return {field: number(row, field) for field in FIELDS}


def main() -> None:
    if not os.getenv("DATABASE_URL", "").strip():
        raise RuntimeError("DATABASE_URL must be configured before bootstrapping Neon")

    ensure_schema()
    Base.metadata.create_all(bind=engine)

    requirements_snapshot = read_csv("inventory.csv")
    unit_rows = read_csv("room_units.csv")
    unit_map = {
        (row.get("apartment") or "").strip(): {
            "standard_unit_id": (row.get("standard_unit_id") or "").strip(),
            "standard_unit_label": (row.get("standard_unit_label") or "").strip(),
        }
        for row in unit_rows
        if (row.get("apartment") or "").strip()
    }
    actual_snapshot = {
        (row.get("apartment") or "").strip(): row
        for row in read_csv("actual_inventory.csv")
        if (row.get("apartment") or "").strip()
    }

    db = SessionLocal()
    added_req = updated_req = added_actual = repaired_actual = reset_bootstrap = 0
    try:
        existing_req = {row.apartment: row for row in db.scalars(select(RequirementDB)).all()}
        existing_actual = {row.apartment: row for row in db.scalars(select(ActualDB)).all()}

        for actual in existing_actual.values():
            if actual.checked_by == "repository-bootstrap":
                actual.checked_at = None
                actual.checked_by = None
                reset_bootstrap += 1

        for row in requirements_snapshot:
            apartment = (row.get("apartment") or "").strip()
            if not apartment:
                continue

            mapping = unit_map.get(apartment)
            if not mapping or not mapping["standard_unit_id"]:
                # An unmapped room remains a one-room standard unit. This keeps
                # the bootstrap safe if a new room is added before its mapping.
                mapping = {"standard_unit_id": apartment, "standard_unit_label": apartment}

            expected = {
                **requirement_values(row),
                **mapping,
            }
            record = existing_req.get(apartment)
            if record is None:
                db.add(RequirementDB(apartment=apartment, **expected))
                added_req += 1
            else:
                changed = False
                for field, value in expected.items():
                    if getattr(record, field) != value:
                        setattr(record, field, value)
                        changed = True
                if changed:
                    updated_req += 1

            snapshot = actual_snapshot.get(apartment)
            if snapshot is None:
                continue

            values = actual_values(snapshot)
            actual = existing_actual.get(apartment)
            if actual is None:
                db.add(ActualDB(apartment=apartment, **values, checked_at=None, checked_by=None))
                added_actual += 1
                continue

            if actual.checked_at is not None:
                continue

            current = {field: int(getattr(actual, field) or 0) for field in FIELDS}
            if current != values:
                for field, value in values.items():
                    setattr(actual, field, value)
                repaired_actual += 1

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(
        "Neon bootstrap complete: "
        f"requirements_added={added_req}, requirements_updated={updated_req}, "
        f"actuals_added={added_actual}, actuals_repaired={repaired_actual}, "
        f"old_bootstrap_checks_reset={reset_bootstrap}"
    )


if __name__ == "__main__":
    main()
