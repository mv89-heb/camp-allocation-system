from __future__ import annotations

import hashlib
import logging
import os
from datetime import timezone
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.database import (
    ActualDB,
    Base,
    DamageAuditDB,
    DamageReportDB,
    InventoryAuditDB,
    RequirementDB,
    database_backend,
    engine,
    get_db,
    utc_now,
)
from app.logic import compute_gaps, dataframe_to_records
from app.models import (
    DAMAGE_CATEGORIES,
    DAMAGE_SEVERITIES,
    DAMAGE_STATUSES,
    STATUS_TRANSITIONS,
    ActualInventoryUpdate,
    AllocationRequest,
    DamageCreateRequest,
    DamageUpdateRequest,
    HealthResponse,
)
from app.rules import assign_groups

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("camp-allocation")
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Camp Allocation System", version="2.1.2")
app.add_middleware(GZipMiddleware, minimum_size=1000)
allowed_hosts = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "*").split(",") if h.strip()]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or ["*"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
AUTH_REQUIRED = bool(ADMIN_TOKEN)
MAX_ROWS = int(os.getenv("MAX_ANALYZE_ROWS", "5000"))


def _safe_token_equal(candidate: str | None) -> bool:
    if not AUTH_REQUIRED:
        return True
    if not candidate:
        return False
    return hashlib.sha256(candidate.encode()).digest() == hashlib.sha256(ADMIN_TOKEN.encode()).digest()


def require_auth(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    if not _safe_token_equal(x_admin_token):
        raise HTTPException(status_code=401, detail="Authentication required")


def _actor(x_admin_token: str | None) -> str:
    return "admin" if not x_admin_token else "token-user"


def _legacy_columns(table_name: str) -> set[str]:
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def ensure_schema() -> None:
    """Create the canonical schema and upgrade legacy columns without replacing tables."""
    Base.metadata.create_all(bind=engine)
    requirements = _legacy_columns("requirements")
    actuals = _legacy_columns("actuals")

    if requirements:
        additions = {
            "beds_std": "INTEGER DEFAULT 4",
            "mattresses_std": "INTEGER DEFAULT 4",
            "closets_std": "INTEGER DEFAULT 4",
            "ac_units_std": "INTEGER DEFAULT 4",
            "ac_remotes_std": "INTEGER DEFAULT 1",
            "beds_plan": "INTEGER DEFAULT 6",
            "mattresses_plan": "INTEGER DEFAULT 6",
            "closets_plan": "INTEGER DEFAULT 6",
            "ac_units_plan": "INTEGER DEFAULT 4",
            "ac_remotes_plan": "INTEGER DEFAULT 1",
        }
        with engine.begin() as conn:
            existing = set(requirements)
            for name, definition in additions.items():
                if name not in existing:
                    conn.execute(text(f'ALTER TABLE requirements ADD COLUMN "{name}" {definition}'))
            legacy_map = {
                "beds": ("beds_std", "beds_plan", 4),
                "mattresses": ("mattresses_std", "mattresses_plan", 4),
                "closets": ("closets_std", "closets_plan", 4),
                "ac_units": ("ac_units_std", "ac_units_plan", 4),
                "ac_remotes": ("ac_remotes_std", "ac_remotes_plan", 1),
            }
            for legacy, (std_col, plan_col, std_cap) in legacy_map.items():
                if legacy in existing:
                    conn.execute(
                        text(
                            f'UPDATE requirements SET "{plan_col}" = CAST("{legacy}" AS INTEGER), '
                            f'"{std_col}" = CASE WHEN CAST("{legacy}" AS INTEGER) < :cap '
                            f'THEN CAST("{legacy}" AS INTEGER) ELSE :cap END'
                        ),
                        {"cap": std_cap},
                    )

    if actuals:
        with engine.begin() as conn:
            if "checked_at" not in actuals:
                conn.execute(text('ALTER TABLE actuals ADD COLUMN checked_at TIMESTAMP'))
            if "checked_by" not in actuals:
                conn.execute(text('ALTER TABLE actuals ADD COLUMN checked_by VARCHAR(120)'))


def _assert_canonical_schema() -> None:
    """Fail with a useful message if a deployment still points at an incompatible DB."""
    required = {
        "requirements": {
            "apartment",
            "beds_std", "mattresses_std", "closets_std", "ac_units_std", "ac_remotes_std",
            "beds_plan", "mattresses_plan", "closets_plan", "ac_units_plan", "ac_remotes_plan",
        },
        "actuals": {"apartment", "beds", "mattresses", "closets", "ac_units", "ac_remotes"},
    }
    for table_name, expected in required.items():
        columns = _legacy_columns(table_name)
        missing = expected - columns
        if missing:
            raise RuntimeError(f"Database schema is not upgraded for {table_name}: missing {sorted(missing)}")


def _bootstrap_production_data() -> None:
    """Reconcile repository snapshots into Neon during every production startup."""
    if not os.getenv("DATABASE_URL", "").strip():
        return
    if os.getenv("DISABLE_PRODUCTION_BOOTSTRAP", "").strip().lower() in {"1", "true", "yes"}:
        logger.warning("Production Neon bootstrap disabled by DISABLE_PRODUCTION_BOOTSTRAP")
        return
    from bootstrap_neon import main as bootstrap_main
    logger.info("Starting production Neon bootstrap from repository snapshots")
    bootstrap_main()


@app.on_event("startup")
def startup() -> None:
    try:
        _bootstrap_production_data()
        ensure_schema()
        _assert_canonical_schema()
        logger.info("Camp Allocation System started; database_backend=%s auth_required=%s", database_backend(), AUTH_REQUIRED)
    except Exception:
        logger.exception("Production startup failed")
        raise


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "auth_required": AUTH_REQUIRED})


@app.get("/health", response_model=HealthResponse)
def health():
    try:
        ensure_schema()
        _assert_canonical_schema()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return HealthResponse(status="ok", database="ok", timestamp=utc_now())
    except Exception:
        logger.exception("Health check failed")
        raise HTTPException(status_code=503, detail="Database unavailable or schema upgrade required")


@app.get("/analyze")
def analyze(mode: str = "std", _: None = Depends(require_auth)):
    if mode not in {"std", "plan"}:
        raise HTTPException(status_code=400, detail="mode must be std or plan")
    try:
        ensure_schema()
        _assert_canonical_schema()
        with engine.connect() as conn:
            req_df = pd.read_sql(select(RequirementDB), conn)
            act_df = pd.read_sql(select(ActualDB), conn)
        if len(req_df) > MAX_ROWS:
            raise HTTPException(status_code=413, detail="Too many requirement rows")
        return dataframe_to_records(compute_gaps(req_df, act_df, mode=mode))
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Analyze schema validation failed")
        raise HTTPException(status_code=503, detail="Database schema upgrade required") from exc
    except Exception:
        logger.exception("Analyze failed")
        raise HTTPException(status_code=500, detail="Unable to analyze inventory")


@app.post("/update_actual")
def update_actual_inventory(
    data: ActualInventoryUpdate,
    db: Session = Depends(get_db),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    if not _safe_token_equal(x_admin_token):
        raise HTTPException(status_code=401, detail="Authentication required")
    apartment_name = data.apartment
    actor = _actor(x_admin_token)
    values = {field: getattr(data, field) for field in ("beds", "mattresses", "closets", "ac_units", "ac_remotes")}
    try:
        record = db.scalar(select(ActualDB).where(ActualDB.apartment == apartment_name).with_for_update())
        previous = None
        if record is None:
            record = ActualDB(apartment=apartment_name, **values)
            db.add(record)
        else:
            previous = {field: getattr(record, field) for field in values}
            for field, value in values.items():
                setattr(record, field, value)
        record.checked_at = utc_now()
        record.checked_by = actor
        db.flush()
        db.add(InventoryAuditDB(apartment=apartment_name, changed_at=utc_now(), changed_by=actor, previous_values=previous, new_values=values))
        db.commit()
        return {"status": "success", "apartment": apartment_name, "checked_at": record.checked_at}
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Concurrent update detected; please retry") from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Inventory update failed for apartment=%s", apartment_name)
        raise HTTPException(status_code=500, detail="Unable to save inventory") from exc


@app.get("/audit/{apartment}")
def audit(apartment: str, db: Session = Depends(get_db), _: None = Depends(require_auth)):
    apartment = apartment.strip()
    if not apartment:
        raise HTTPException(status_code=400, detail="Apartment is required")
    rows = db.scalars(
        select(InventoryAuditDB)
        .where(InventoryAuditDB.apartment == apartment)
        .order_by(InventoryAuditDB.changed_at.desc())
        .limit(100)
    ).all()
    return [
        {
            "id": row.id,
            "apartment": row.apartment,
            "changed_at": row.changed_at.astimezone(timezone.utc).isoformat(),
            "changed_by": row.changed_by,
            "previous_values": row.previous_values,
            "new_values": row.new_values,
        }
        for row in rows
    ]


@app.post("/allocate")
def allocate(request: AllocationRequest, db: Session = Depends(get_db), _: None = Depends(require_auth)):
    rows = db.execute(select(ActualDB.apartment, ActualDB.beds)).all()
    rooms = pd.DataFrame([{"room": apartment, "actual_capacity": beds} for apartment, beds in rows])
    assignments = assign_groups(rooms, [group.model_dump() for group in request.groups], allow_split=request.allow_split) if not rooms.empty else []
    return {"assignments": assignments}


DAMAGE_OUTPUT_FIELDS = (
    "id", "apartment", "category", "severity", "status", "description", "estimated_cost",
    "actual_cost", "responsible_party", "resolution_notes", "evidence_urls", "reported_by",
    "reported_at", "updated_by", "updated_at", "resolved_at",
)


def _damage_dict(row: DamageReportDB) -> dict:
    return {
        "id": row.id,
        "apartment": row.apartment,
        "category": row.category,
        "severity": row.severity,
        "status": row.status,
        "description": row.description,
        "estimated_cost": float(row.estimated_cost) if row.estimated_cost is not None else None,
        "actual_cost": float(row.actual_cost) if row.actual_cost is not None else None,
        "responsible_party": row.responsible_party,
        "resolution_notes": row.resolution_notes,
        "evidence_urls": row.evidence_urls or [],
        "reported_by": row.reported_by,
        "reported_at": row.reported_at.astimezone(timezone.utc).isoformat(),
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.astimezone(timezone.utc).isoformat(),
        "resolved_at": row.resolved_at.astimezone(timezone.utc).isoformat() if row.resolved_at else None,
    }


def _room_exists(db: Session, apartment: str) -> bool:
    return db.scalar(select(RequirementDB.apartment).where(RequirementDB.apartment == apartment)) is not None or db.scalar(select(ActualDB.apartment).where(ActualDB.apartment == apartment)) is not None


def _damage_snapshot(row: DamageReportDB) -> dict:
    return _damage_dict(row)


@app.get("/damages")
def list_damages(
    apartment: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_auth),
):
    query = select(DamageReportDB)
    if apartment:
        query = query.where(DamageReportDB.apartment == apartment.strip())
    if status:
        status = status.upper()
        if status not in DAMAGE_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid damage status")
        query = query.where(DamageReportDB.status == status)
    if severity:
        severity = severity.upper()
        if severity not in DAMAGE_SEVERITIES:
            raise HTTPException(status_code=400, detail="Invalid damage severity")
        query = query.where(DamageReportDB.severity == severity)
    if category:
        category = category.upper()
        if category not in DAMAGE_CATEGORIES:
            raise HTTPException(status_code=400, detail="Invalid damage category")
        query = query.where(DamageReportDB.category == category)
    rows = db.scalars(query.order_by(DamageReportDB.updated_at.desc()).limit(1000)).all()
    return [_damage_dict(row) for row in rows]


@app.post("/damages", status_code=201)
def create_damage(
    data: DamageCreateRequest,
    db: Session = Depends(get_db),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    if not _safe_token_equal(x_admin_token):
        raise HTTPException(status_code=401, detail="Authentication required")
    if not _room_exists(db, data.apartment):
        raise HTTPException(status_code=404, detail="Room/apartment does not exist")
    actor = _actor(x_admin_token)
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
        reported_by=actor,
        reported_at=now,
        updated_by=actor,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    db.add(DamageAuditDB(
        damage_id=row.id,
        apartment=row.apartment,
        changed_at=now,
        changed_by=actor,
        action="CREATED",
        previous_values=None,
        new_values=_damage_snapshot(row),
    ))
    db.commit()
    db.refresh(row)
    return _damage_dict(row)


@app.get("/damages/{damage_id}")
def get_damage(damage_id: int, db: Session = Depends(get_db), _: None = Depends(require_auth)):
    row = db.get(DamageReportDB, damage_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Damage report not found")
    return _damage_dict(row)


@app.patch("/damages/{damage_id}")
def update_damage(
    damage_id: int,
    data: DamageUpdateRequest,
    db: Session = Depends(get_db),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    if not _safe_token_equal(x_admin_token):
        raise HTTPException(status_code=401, detail="Authentication required")
    row = db.get(DamageReportDB, damage_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Damage report not found")
    actor = _actor(x_admin_token)
    previous = _damage_snapshot(row)
    updates = data.model_dump(exclude_unset=True)
    if "status" in updates:
        new_status = updates["status"]
        allowed = STATUS_TRANSITIONS.get(row.status, set())
        if new_status != row.status and new_status not in allowed:
            raise HTTPException(status_code=409, detail=f"Invalid status transition: {row.status} -> {new_status}")
        if new_status in {"RESOLVED", "CLOSED"} and not (updates.get("resolution_notes") or row.resolution_notes):
            raise HTTPException(status_code=422, detail="Resolution notes are required before resolving or closing")
    for field, value in updates.items():
        setattr(row, field, value)
    row.updated_by = actor
    row.updated_at = utc_now()
    if row.status in {"RESOLVED", "CLOSED"} and row.resolved_at is None:
        row.resolved_at = row.updated_at
    db.add(DamageAuditDB(
        damage_id=row.id,
        apartment=row.apartment,
        changed_at=row.updated_at,
        changed_by=actor,
        action="UPDATED",
        previous_values=previous,
        new_values=_damage_snapshot(row),
    ))
    db.commit()
    db.refresh(row)
    return _damage_dict(row)


@app.get("/damages/{damage_id}/audit")
def damage_audit(damage_id: int, db: Session = Depends(get_db), _: None = Depends(require_auth)):
    if db.get(DamageReportDB, damage_id) is None:
        raise HTTPException(status_code=404, detail="Damage report not found")
    rows = db.scalars(select(DamageAuditDB).where(DamageAuditDB.damage_id == damage_id).order_by(DamageAuditDB.changed_at.desc()).limit(500)).all()
    return [
        {
            "id": row.id,
            "damage_id": row.damage_id,
            "apartment": row.apartment,
            "changed_at": row.changed_at.astimezone(timezone.utc).isoformat(),
            "changed_by": row.changed_by,
            "action": row.action,
            "previous_values": row.previous_values,
            "new_values": row.new_values,
        }
        for row in rows
    ]
