from __future__ import annotations

import hashlib
import os
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import ActualDB, RequirementDB, DamageReportDB, get_db, utc_now
from app.models import ActualInventoryUpdate, DamageCreateRequest

router = APIRouter(prefix="/field-api", tags=["field"])
FIELD_TOKEN = os.getenv("FIELD_TOKEN", "").strip()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()

def _authorized(token: str | None) -> bool:
    if not FIELD_TOKEN and not ADMIN_TOKEN:
        # Development fallback only. Production should set FIELD_TOKEN.
        return True
    if not token:
        return False
    candidate = hashlib.sha256(token.encode()).digest()
    valid = []
    if FIELD_TOKEN:
        valid.append(hashlib.sha256(FIELD_TOKEN.encode()).digest())
    if ADMIN_TOKEN:
        valid.append(hashlib.sha256(ADMIN_TOKEN.encode()).digest())
    return any(candidate == expected for expected in valid)

def require_field_token(x_field_token: str | None = Header(default=None, alias="X-Field-Token"), x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    if _authorized(x_field_token) or _authorized(x_admin_token):
        return
    raise HTTPException(status_code=401, detail="Field authentication required")

@router.get("/rooms")
def field_rooms(db: Session = Depends(get_db), _: None = Depends(require_field_token)):
    requirements = {r.apartment: r for r in db.scalars(select(RequirementDB)).all()}
    actuals = {r.apartment: r for r in db.scalars(select(ActualDB)).all()}
    names = sorted(set(requirements) | set(actuals))
    out = []
    for name in names:
        req = requirements.get(name)
        act = actuals.get(name)
        out.append({
            "apartment": name,
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
            "open_damage": bool(db.scalar(select(DamageReportDB.id).where(DamageReportDB.apartment == name, DamageReportDB.status.in_(["OPEN", "INSPECTION", "IN_PROGRESS"])).limit(1))),
        })
    return out

@router.post("/inventory")
def field_inventory(data: ActualInventoryUpdate, db: Session = Depends(get_db), _: None = Depends(require_field_token)):
    record = db.scalar(select(ActualDB).where(ActualDB.apartment == data.apartment).with_for_update())
    values = {f: getattr(data, f) for f in ("beds", "mattresses", "closets", "ac_units", "ac_remotes")}
    if record is None:
        record = ActualDB(apartment=data.apartment, **values)
        db.add(record)
    else:
        for f, v in values.items():
            setattr(record, f, v)
    record.checked_at = utc_now()
    record.checked_by = "field-reporter"
    db.commit()
    return {"status": "success", "apartment": data.apartment, "checked_at": record.checked_at}

@router.post("/damages", status_code=201)
def field_damage(data: DamageCreateRequest, db: Session = Depends(get_db), _: None = Depends(require_field_token)):
    exists = db.scalar(select(RequirementDB.apartment).where(RequirementDB.apartment == data.apartment)) or db.scalar(select(ActualDB.apartment).where(ActualDB.apartment == data.apartment))
    if not exists:
        raise HTTPException(status_code=404, detail="Room/apartment does not exist")
    now = utc_now()
    row = DamageReportDB(
        apartment=data.apartment,
        category=data.category,
        severity=data.severity,
        status="OPEN",
        description=data.description,
        estimated_cost=data.estimated_cost,
        responsible_party=data.responsible_party,
        resolution_notes=data.resolution_notes,
        evidence_urls=data.evidence_urls,
        reported_by="field-reporter",
        reported_at=now,
        updated_by="field-reporter",
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "status": row.status, "apartment": row.apartment}
