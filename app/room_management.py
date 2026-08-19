from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import ActualDB, InventoryAuditDB, RequirementDB, get_db, utc_now

router = APIRouter(prefix="/rooms", tags=["rooms"])


class RoomCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    apartment: str = Field(min_length=1, max_length=120, pattern=r"^[0-9A-Za-z\u0590-\u05FF ._/#-]+$")
    beds_std: int = Field(default=4, ge=0, le=1000)
    mattresses_std: int = Field(default=4, ge=0, le=1000)
    closets_std: int = Field(default=4, ge=0, le=1000)
    ac_units_std: int = Field(default=4, ge=0, le=1000)
    ac_remotes_std: int = Field(default=1, ge=0, le=1000)
    beds_plan: int = Field(default=6, ge=0, le=1000)
    mattresses_plan: int = Field(default=6, ge=0, le=1000)
    closets_plan: int = Field(default=6, ge=0, le=1000)
    ac_units_plan: int = Field(default=4, ge=0, le=1000)
    ac_remotes_plan: int = Field(default=1, ge=0, le=1000)


@router.post("", status_code=201)
def create_room(data: RoomCreateRequest, db: Session = Depends(get_db)):
    apartment = data.apartment.strip()
    if db.scalar(select(RequirementDB).where(RequirementDB.apartment == apartment)) is not None:
        raise HTTPException(status_code=409, detail="החדר כבר קיים במערכת")
    if db.scalar(select(ActualDB).where(ActualDB.apartment == apartment)) is not None:
        raise HTTPException(status_code=409, detail="החדר כבר קיים במערכת")

    now = utc_now()
    req = RequirementDB(
        apartment=apartment,
        beds_std=data.beds_std,
        mattresses_std=data.mattresses_std,
        closets_std=data.closets_std,
        ac_units_std=data.ac_units_std,
        ac_remotes_std=data.ac_remotes_std,
        beds_plan=data.beds_plan,
        mattresses_plan=data.mattresses_plan,
        closets_plan=data.closets_plan,
        ac_units_plan=data.ac_units_plan,
        ac_remotes_plan=data.ac_remotes_plan,
    )
    actual = ActualDB(
        apartment=apartment,
        beds=0,
        mattresses=0,
        closets=0,
        ac_units=0,
        ac_remotes=0,
        checked_at=None,
        checked_by=None,
    )
    db.add_all([req, actual])
    db.add(
        InventoryAuditDB(
            apartment=apartment,
            changed_at=now,
            changed_by="room-management",
            previous_values=None,
            new_values={
                "action": "ROOM_CREATED",
                "apartment": apartment,
                "beds_std": data.beds_std,
                "mattresses_std": data.mattresses_std,
                "closets_std": data.closets_std,
                "ac_units_std": data.ac_units_std,
                "ac_remotes_std": data.ac_remotes_std,
                "beds_plan": data.beds_plan,
                "mattresses_plan": data.mattresses_plan,
                "closets_plan": data.closets_plan,
                "ac_units_plan": data.ac_units_plan,
                "ac_remotes_plan": data.ac_remotes_plan,
            },
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="החדר כבר קיים במערכת")

    return {
        "status": "created",
        "apartment": apartment,
        "inventory_checked": False,
        "actual": {"beds": 0, "mattresses": 0, "closets": 0, "ac_units": 0, "ac_remotes": 0},
    }
