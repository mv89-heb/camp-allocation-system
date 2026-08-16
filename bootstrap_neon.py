"""Safely reconcile the versioned room snapshot with the Neon database.

Rules:
- Neon is the production database; never drop or replace tables.
- requirements are reconciled to the repository's canonical inventory.csv snapshot.
- actual inventory is restored from actual_inventory.csv only when a room has never
  been physically checked in the database.
- a real zero snapshot remains zero and *unchecked*; it is never converted into a
  confirmed shortage.
- an already checked actual inventory row is never overwritten by bootstrap.

The script is idempotent and safe to run on every Render start.
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
    actual_snapshot = {
        (row.get("apartment") or "").strip(): row
        for row in read_csv("actual_inventory.csv")
        if (row.get("apartment") or "").strip()
    }

    db = SessionLocal()
    now = utc_now()
    added_req = updated_req = added_actual = repaired_actual = 0
    try:
        existing_req = {row.apartment: row for row in db.scalars(select(RequirementDB)).all()}
        existing_actual = {row.apartment: row for row in db.scalars(select(ActualDB)).all()}

        for row in requirements_snapshot:
            apartment = (row.get("apartment") or "").strip()
            if not apartment:
                continue

            expected = requirement_values(row)
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
                # Preserve the distinction between "real zero" and "checked zero".
                verified = any(values.values())
                db.add(ActualDB(
                    apartment=apartment,
                    **values,
                    checked_at=now if verified else None,
                    checked_by="repository-bootstrap" if verified else None,
                ))
                added_actual += 1
                continue

            # Only rows that have never been checked may be restored from the
            # repository snapshot. A non-zero source snapshot is authoritative for
            # an unchecked row, even when the database contains an older non-zero
            # value. A zero source snapshot never erases an existing non-zero value.
            if actual.checked_at is None:
                current = {field: int(getattr(actual, field) or 0) for field in FIELDS}
                if any(values.values()):
                    if current != values:
                        for field, value in values.items():
                            setattr(actual, field, value)
                        repaired_actual += 1
                    actual.checked_at = now
                    actual.checked_by = "repository-bootstrap"
                elif all(v == 0 for v in current.values()):
                    # Keep genuine zero snapshots explicitly unverified.
                    pass

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(
        "Neon bootstrap complete: "
        f"requirements_added={added_req}, "
        f"requirements_updated={updated_req}, "
        f"actuals_added={added_actual}, "
        f"actuals_repaired={repaired_actual}"
    )


if __name__ == "__main__":
    main()
