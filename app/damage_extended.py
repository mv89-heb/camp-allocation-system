from __future__ import annotations

import hashlib
import os
from datetime import date, timezone
from decimal import Decimal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, select
from sqlalchemy.orm import Session

from app.database import Base, DamageAuditDB, DamageReportDB, get_db, utc_now


class DamageItemDB(Base):
    __tablename__ = "damage_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    damage_id = Column(Integer, ForeignKey("damage_reports.id"), nullable=False, index=True)
    item_name = Column(String(160), nullable=False)
    description = Column(Text, nullable=True)
    quantity = Column(Integer, nullable=False, default=1)
    estimated_unit_cost = Column(Numeric(12, 2), nullable=True)
    actual_unit_cost = Column(Numeric(12, 2), nullable=True)
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    evidence_urls = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class RepairQuoteDB(Base):
    __tablename__ = "repair_quotes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    damage_id = Column(Integer, ForeignKey("damage_reports.id"), nullable=False, index=True)
    vendor = Column(String(160), nullable=False)
    quote_number = Column(String(100), nullable=True)
    quoted_cost = Column(Numeric(12, 2), nullable=False)
    valid_until = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="RECEIVED", index=True)
    evidence_url = Column(String(2048), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


router = APIRouter(prefix="/damages", tags=["damage-extended"])
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
AUTH_REQUIRED = bool(ADMIN_TOKEN)


def _authorized(candidate: str | None) -> bool:
    if not AUTH_REQUIRED:
        return True
    if not candidate:
        return False
    return hashlib.sha256(candidate.encode()).digest() == hashlib.sha256(ADMIN_TOKEN.encode()).digest()


def require_auth(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    if not _authorized(x_admin_token):
        raise HTTPException(status_code=401, detail="Authentication required")


MONEY = Field(default=None, ge=0, le=100000000, max_digits=12, decimal_places=2)
ITEM_STATUSES = {"OPEN", "REPAIRED", "REPLACED", "REMOVED"}
QUOTE_STATUSES = {"RECEIVED", "SELECTED", "REJECTED", "EXPIRED"}


def _valid_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must use http or https")
    return value


class DamageItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    item_name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    quantity: int = Field(default=1, ge=1, le=10000)
    estimated_unit_cost: Decimal | None = Field(default=None, ge=0, le=100000000, max_digits=12, decimal_places=2)
    actual_unit_cost: Decimal | None = Field(default=None, ge=0, le=100000000, max_digits=12, decimal_places=2)
    status: str = "OPEN"
    evidence_urls: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        value = value.upper()
        if value not in ITEM_STATUSES:
            raise ValueError("invalid item status")
        return value

    @field_validator("evidence_urls")
    @classmethod
    def validate_urls(cls, values: list[str]) -> list[str]:
        return [_valid_url(value) for value in values]


class DamageItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    item_name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    quantity: int | None = Field(default=None, ge=1, le=10000)
    estimated_unit_cost: Decimal | None = Field(default=None, ge=0, le=100000000, max_digits=12, decimal_places=2)
    actual_unit_cost: Decimal | None = Field(default=None, ge=0, le=100000000, max_digits=12, decimal_places=2)
    status: str | None = None
    evidence_urls: list[str] | None = Field(default=None, max_length=10)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if value not in ITEM_STATUSES:
            raise ValueError("invalid item status")
        return value

    @field_validator("evidence_urls")
    @classmethod
    def validate_urls(cls, values: list[str] | None) -> list[str] | None:
        return None if values is None else [_valid_url(value) for value in values]


class RepairQuoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    vendor: str = Field(min_length=1, max_length=160)
    quote_number: str | None = Field(default=None, max_length=100)
    quoted_cost: Decimal = Field(ge=0, le=100000000, max_digits=12, decimal_places=2)
    valid_until: date | None = None
    status: str = "RECEIVED"
    evidence_url: str | None = Field(default=None, max_length=2048)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        value = value.upper()
        if value not in QUOTE_STATUSES:
            raise ValueError("invalid quote status")
        return value

    @field_validator("evidence_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return None if value is None else _valid_url(value)


class RepairQuoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    vendor: str | None = Field(default=None, min_length=1, max_length=160)
    quote_number: str | None = Field(default=None, max_length=100)
    quoted_cost: Decimal | None = Field(default=None, ge=0, le=100000000, max_digits=12, decimal_places=2)
    valid_until: date | None = None
    status: str | None = None
    evidence_url: str | None = Field(default=None, max_length=2048)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if value not in QUOTE_STATUSES:
            raise ValueError("invalid quote status")
        return value

    @field_validator("evidence_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return None if value is None else _valid_url(value)


def _damage(db: Session, damage_id: int) -> DamageReportDB:
    row = db.get(DamageReportDB, damage_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Damage report not found")
    return row


def _item_dict(row: DamageItemDB) -> dict:
    return {
        "id": row.id,
        "damage_id": row.damage_id,
        "item_name": row.item_name,
        "description": row.description,
        "quantity": row.quantity,
        "estimated_unit_cost": float(row.estimated_unit_cost) if row.estimated_unit_cost is not None else None,
        "actual_unit_cost": float(row.actual_unit_cost) if row.actual_unit_cost is not None else None,
        "status": row.status,
        "evidence_urls": row.evidence_urls or [],
        "created_at": row.created_at.astimezone(timezone.utc).isoformat(),
        "updated_at": row.updated_at.astimezone(timezone.utc).isoformat(),
    }


def _quote_dict(row: RepairQuoteDB) -> dict:
    return {
        "id": row.id,
        "damage_id": row.damage_id,
        "vendor": row.vendor,
        "quote_number": row.quote_number,
        "quoted_cost": float(row.quoted_cost),
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "status": row.status,
        "evidence_url": row.evidence_url,
        "notes": row.notes,
        "created_at": row.created_at.astimezone(timezone.utc).isoformat(),
        "updated_at": row.updated_at.astimezone(timezone.utc).isoformat(),
    }


def _audit(db: Session, damage: DamageReportDB, actor: str, action: str, previous: dict | None, new: dict) -> None:
    db.add(DamageAuditDB(
        damage_id=damage.id,
        apartment=damage.apartment,
        changed_at=utc_now(),
        changed_by=actor,
        action=action,
        previous_values=previous,
        new_values=new,
    ))


@router.get("/{damage_id}/items")
def list_items(damage_id: int, db: Session = Depends(get_db), _: None = Depends(require_auth)):
    _damage(db, damage_id)
    rows = db.scalars(select(DamageItemDB).where(DamageItemDB.damage_id == damage_id).order_by(DamageItemDB.id)).all()
    return [_item_dict(row) for row in rows]


@router.post("/{damage_id}/items", status_code=201)
def create_item(damage_id: int, data: DamageItemCreate, db: Session = Depends(get_db), x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    if not _authorized(x_admin_token):
        raise HTTPException(status_code=401, detail="Authentication required")
    damage = _damage(db, damage_id)
    now = utc_now()
    actor = "admin" if not x_admin_token else "token-user"
    row = DamageItemDB(damage_id=damage.id, item_name=data.item_name, description=data.description, quantity=data.quantity, estimated_unit_cost=data.estimated_unit_cost, actual_unit_cost=data.actual_unit_cost, status=data.status, evidence_urls=data.evidence_urls, created_at=now, updated_at=now)
    db.add(row)
    db.flush()
    _audit(db, damage, actor, "ITEM_CREATED", None, _item_dict(row))
    db.commit()
    db.refresh(row)
    return _item_dict(row)


@router.patch("/{damage_id}/items/{item_id}")
def update_item(damage_id: int, item_id: int, data: DamageItemUpdate, db: Session = Depends(get_db), x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    if not _authorized(x_admin_token):
        raise HTTPException(status_code=401, detail="Authentication required")
    damage = _damage(db, damage_id)
    row = db.get(DamageItemDB, item_id)
    if row is None or row.damage_id != damage_id:
        raise HTTPException(status_code=404, detail="Damage item not found")
    previous = _item_dict(row)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = utc_now()
    actor = "admin" if not x_admin_token else "token-user"
    _audit(db, damage, actor, "ITEM_UPDATED", previous, _item_dict(row))
    db.commit()
    db.refresh(row)
    return _item_dict(row)


@router.get("/{damage_id}/quotes")
def list_quotes(damage_id: int, db: Session = Depends(get_db), _: None = Depends(require_auth)):
    _damage(db, damage_id)
    rows = db.scalars(select(RepairQuoteDB).where(RepairQuoteDB.damage_id == damage_id).order_by(RepairQuoteDB.quoted_cost.asc(), RepairQuoteDB.id.asc())).all()
    return [_quote_dict(row) for row in rows]


@router.post("/{damage_id}/quotes", status_code=201)
def create_quote(damage_id: int, data: RepairQuoteCreate, db: Session = Depends(get_db), x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    if not _authorized(x_admin_token):
        raise HTTPException(status_code=401, detail="Authentication required")
    damage = _damage(db, damage_id)
    now = utc_now()
    actor = "admin" if not x_admin_token else "token-user"
    row = RepairQuoteDB(damage_id=damage.id, vendor=data.vendor, quote_number=data.quote_number, quoted_cost=data.quoted_cost, valid_until=data.valid_until, status=data.status, evidence_url=data.evidence_url, notes=data.notes, created_at=now, updated_at=now)
    db.add(row)
    db.flush()
    _audit(db, damage, actor, "QUOTE_CREATED", None, _quote_dict(row))
    db.commit()
    db.refresh(row)
    return _quote_dict(row)


@router.patch("/{damage_id}/quotes/{quote_id}")
def update_quote(damage_id: int, quote_id: int, data: RepairQuoteUpdate, db: Session = Depends(get_db), x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    if not _authorized(x_admin_token):
        raise HTTPException(status_code=401, detail="Authentication required")
    damage = _damage(db, damage_id)
    row = db.get(RepairQuoteDB, quote_id)
    if row is None or row.damage_id != damage_id:
        raise HTTPException(status_code=404, detail="Repair quote not found")
    previous = _quote_dict(row)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(row, field, value)
    row.updated_at = utc_now()
    actor = "admin" if not x_admin_token else "token-user"
    _audit(db, damage, actor, "QUOTE_UPDATED", previous, _quote_dict(row))
    db.commit()
    db.refresh(row)
    return _quote_dict(row)


@router.get("/{damage_id}/summary")
def damage_summary(damage_id: int, db: Session = Depends(get_db), _: None = Depends(require_auth)):
    damage = _damage(db, damage_id)
    items = db.scalars(select(DamageItemDB).where(DamageItemDB.damage_id == damage_id).order_by(DamageItemDB.id)).all()
    quotes = db.scalars(select(RepairQuoteDB).where(RepairQuoteDB.damage_id == damage_id).order_by(RepairQuoteDB.quoted_cost.asc(), RepairQuoteDB.id.asc())).all()
    audits = db.scalars(select(DamageAuditDB).where(DamageAuditDB.damage_id == damage_id).order_by(DamageAuditDB.changed_at.desc()).limit(100)).all()
    estimated_items = sum((Decimal(str(item.estimated_unit_cost or 0)) * item.quantity for item in items), Decimal("0"))
    actual_items = sum((Decimal(str(item.actual_unit_cost or 0)) * item.quantity for item in items), Decimal("0"))
    quote_total = sum((Decimal(str(quote.quoted_cost)) for quote in quotes if quote.status != "REJECTED"), Decimal("0"))
    return {
        "damage": {"id": damage.id, "apartment": damage.apartment, "status": damage.status, "estimated_cost": float(damage.estimated_cost) if damage.estimated_cost is not None else None, "actual_cost": float(damage.actual_cost) if damage.actual_cost is not None else None},
        "items": [_item_dict(item) for item in items],
        "quotes": [_quote_dict(quote) for quote in quotes],
        "audit": [{"id": audit.id, "action": audit.action, "changed_by": audit.changed_by, "changed_at": audit.changed_at.astimezone(timezone.utc).isoformat()} for audit in audits],
        "calculated": {"estimated_items_cost": float(estimated_items), "actual_items_cost": float(actual_items), "non_rejected_quotes_total": float(quote_total)},
    }
