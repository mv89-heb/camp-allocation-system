from __future__ import annotations

import hashlib
import os
import re

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import ActualDB, DamageAuditDB, DamageReportDB, InventoryAuditDB, RequirementDB, get_db, utc_now
from app.models import ActualInventoryUpdate, DamageCreateRequest, FieldRoomReportRequest

router = APIRouter(prefix="/field-api", tags=["field"])
FIELD_TOKEN = os.getenv("FIELD_TOKEN", "").strip()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
ROOM_NUMBER_RE = re.compile(r"(\d{3})$")


def _matches(candidate: str | None, expected: str) -> bool:
    if not candidate or not expected:
        return False
    return hashlib.sha256(candidate.encode()).digest() == hashlib.sha256(expected.encode()).digest()


def require_field_token(
    x_field_token: str | None = Header(default=None, alias="X-Field-Token"),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> str:
    if _matches(x_field_token, FIELD_TOKEN):
        return "field-reporter"
    if _matches(x_admin_token, ADMIN_TOKEN):
        return "admin"
    raise HTTPException(status_code=401, detail="Field authentication required")


def _room_exists(db: Session, apartment: str) -> bool:
    return (
        db.scalar(select(RequirementDB.apartment).where(RequirementDB.apartment == apartment)) is not None
        or db.scalar(select(ActualDB.apartment).where(ActualDB.apartment == apartment)) is not None
    )


def _room_rows(db: Session):
    requirements = {r.apartment: r for r in db.scalars(select(RequirementDB)).all()}
    actuals = {r.apartment: r for r in db.scalars(select(ActualDB)).all()}
    names = sorted(set(requirements) | set(actuals))
    return requirements, actuals, names


def _room_number(name: str) -> int:
    match = ROOM_NUMBER_RE.search(str(name).strip())
    return int(match.group(1)) if match else 9999


def _room_group(name: str) -> tuple[int, str]:
    value = str(name).strip()
    number = _room_number(value)
    if 101 <= number <= 108:
        return 1, "קומה 1"
    if 201 <= number <= 212:
        return 2, "קומה 2"
    if 301 <= number <= 313:
        return 3, "קומה 3"
    if value.startswith("קרוון"):
        return 4, "מתחם קרוואנים"
    return 5, "יחידות נוספות"


@router.get("/rooms")
def field_rooms(db: Session = Depends(get_db), _: str = Depends(require_field_token)):
    requirements, actuals, names = _room_rows(db)
    names.sort(key=lambda name: (_room_group(name)[0], _room_number(name), name))
    out = []
    for name in names:
        req = requirements.get(name)
        act = actuals.get(name)
        open_damage = db.scalar(
            select(DamageReportDB.id)
            .where(
                DamageReportDB.apartment == name,
                DamageReportDB.status.in_(["OPEN", "INSPECTION", "IN_PROGRESS"]),
            )
            .limit(1)
        )
        out.append({
            "apartment": name,
            "group": _room_group(name)[1],
            "beds_req": getattr(req, "beds_std", 0) if req else 0,
            "mattresses_req": getattr(req, "mattresses_std", 0) if req else 0,
            "closets_req": getattr(req, "closets_std", 0) if req else 0,
            "ac_units_req": getattr(req, "ac_units_std", 0) if req else 0,
            "ac_remotes_req": getattr(req, "ac_remotes_std", 0) if req else 0,
            "beds_act": getattr(act, "beds", 0) if act else 0,
            "mattresses_act": getattr(act, "mattresses", 0) if act else 0,
            "closets_act": getattr(act, "closets", 0) if act else 0,
            "ac_units_act": getattr(act, "ac_units", 0) if act else 0,
            "ac_remotes_act": getattr(act, "ac_remotes", 0) if act else 0,
            "inventory_checked": bool(act and act.checked_at),
            "checked_at": act.checked_at.isoformat() if act and act.checked_at else None,
            "open_damage": bool(open_damage),
        })
    return out


@router.post("/room-report")
def field_room_report(
    data: FieldRoomReportRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_field_token),
):
    apartment = data.inventory.apartment
    if not _room_exists(db, apartment):
        raise HTTPException(status_code=404, detail="Room/apartment does not exist")

    now = utc_now()
    values = {f: getattr(data.inventory, f) for f in ("beds", "mattresses", "closets", "ac_units", "ac_remotes")}
    record = db.scalar(select(ActualDB).where(ActualDB.apartment == apartment).with_for_update())
    previous = None
    try:
        if record is None:
            record = ActualDB(apartment=apartment, **values)
            db.add(record)
        else:
            previous = {f: getattr(record, f) for f in values}
            for field, value in values.items():
                setattr(record, field, value)
        record.checked_at = now
        record.checked_by = actor
        db.flush()
        db.add(InventoryAuditDB(
            apartment=apartment,
            changed_at=now,
            changed_by=actor,
            previous_values=previous,
            new_values=values,
        ))

        created = []
        for damage in data.damages:
            row = DamageReportDB(
                apartment=apartment,
                category=damage.category,
                severity=damage.severity,
                status="OPEN",
                description=damage.description,
                estimated_cost=damage.estimated_cost,
                responsible_party=damage.responsible_party,
                resolution_notes=damage.resolution_notes,
                evidence_urls=damage.evidence_urls,
                reported_by=actor,
                reported_at=now,
                updated_by=actor,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            db.add(DamageAuditDB(
                damage_id=row.id,
                apartment=apartment,
                changed_at=now,
                changed_by=actor,
                action="CREATED",
                previous_values=None,
                new_values={"id": row.id, "apartment": apartment, "category": row.category, "severity": row.severity, "status": row.status, "description": row.description},
            ))
            created.append(row.id)

        db.commit()
        return {"status": "success", "apartment": apartment, "checked_at": now, "damage_ids": created}
    except Exception:
        db.rollback()
        raise


@router.post("/inventory")
def field_inventory(data: ActualInventoryUpdate, db: Session = Depends(get_db), actor: str = Depends(require_field_token)):
    if not _room_exists(db, data.apartment):
        raise HTTPException(status_code=404, detail="Room/apartment does not exist")
    values = {f: getattr(data, f) for f in ("beds", "mattresses", "closets", "ac_units", "ac_remotes")}
    record = db.scalar(select(ActualDB).where(ActualDB.apartment == data.apartment).with_for_update())
    previous = None
    now = utc_now()
    try:
        if record is None:
            record = ActualDB(apartment=data.apartment, **values)
            db.add(record)
        else:
            previous = {f: getattr(record, f) for f in values}
            for f, v in values.items():
                setattr(record, f, v)
        record.checked_at = now
        record.checked_by = actor
        db.add(InventoryAuditDB(apartment=data.apartment, changed_at=now, changed_by=actor, previous_values=previous, new_values=values))
        db.commit()
        return {"status": "success", "apartment": data.apartment, "checked_at": record.checked_at}
    except Exception:
        db.rollback()
        raise


@router.post("/damages", status_code=201)
def field_damage(data: DamageCreateRequest, db: Session = Depends(get_db), actor: str = Depends(require_field_token)):
    if not _room_exists(db, data.apartment):
        raise HTTPException(status_code=404, detail="Room/apartment does not exist")
    now = utc_now()
    row = DamageReportDB(
        apartment=data.apartment, category=data.category, severity=data.severity, status="OPEN",
        description=data.description, estimated_cost=data.estimated_cost,
        responsible_party=data.responsible_party, resolution_notes=data.resolution_notes,
        evidence_urls=data.evidence_urls, reported_by=actor, reported_at=now,
        updated_by=actor, updated_at=now,
    )
    db.add(row)
    try:
        db.flush()
        db.add(DamageAuditDB(
            damage_id=row.id, apartment=row.apartment, changed_at=now, changed_by=actor,
            action="CREATED", previous_values=None,
            new_values={"id": row.id, "apartment": row.apartment, "category": row.category, "severity": row.severity, "status": row.status, "description": row.description},
        ))
        db.commit()
        db.refresh(row)
        return {"id": row.id, "status": row.status, "apartment": row.apartment}
    except Exception:
        db.rollback()
        raise
