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
    """Reconcile repository snapshots into Neon exactly once per process startup."""
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
            record = ActualDB(apartment=apartment_name, **values, checked_at=utc_now(), checked_by=actor)
            db.add(record)
        else:
            previous = {field: getattr(record, field) for field in values}
            for field, value in values.items():
                setattr(record, field, value)
            record.checked_at = utc_now()
            record.checked_by = actor
        db.add(InventoryAuditDB(apartment=apartment_name, changed_at=utc_now(), changed_by=actor, old_values=previous, new_values=values))
        db.commit()
        return {"status": "ok", "apartment": apartment_name, "values": values}
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Inventory update conflicted with another change") from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Actual inventory update failed")
        raise HTTPException(status_code=500, detail="Unable to update actual inventory") from exc


@app.get("/audit/{apartment}")
def audit(apartment: str, _: None = Depends(require_auth)):
    with Session(bind=engine) as db:
        rows = db.scalars(select(InventoryAuditDB).where(InventoryAuditDB.apartment == apartment).order_by(InventoryAuditDB.changed_at.desc())).all()
        return [
            {
                "changed_at": row.changed_at.isoformat() if row.changed_at else None,
                "changed_by": row.changed_by,
                "old_values": row.old_values,
                "new_values": row.new_values,
            }
            for row in rows
        ]


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/favicon.ico")
def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)


@app.get("/damages")
def list_damages(
    apartment: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    _: None = Depends(require_auth),
):
    with Session(bind=engine) as db:
        query = select(DamageReportDB).order_by(DamageReportDB.created_at.desc())
        if apartment:
            query = query.where(DamageReportDB.apartment.ilike(f"%{apartment}%"))
        if status:
            query = query.where(DamageReportDB.status == status)
        if severity:
            query = query.where(DamageReportDB.severity == severity)
        rows = db.scalars(query.limit(MAX_ROWS)).all()
        return [
            {
                "id": row.id,
                "apartment": row.apartment,
                "category": row.category,
                "severity": row.severity,
                "status": row.status,
                "description": row.description,
                "estimated_cost": row.estimated_cost,
                "responsible_party": row.responsible_party,
                "evidence_urls": row.evidence_urls or [],
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]


@app.post("/damages")
def create_damage(
    data: DamageCreateRequest,
    db: Session = Depends(get_db),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    if not _safe_token_equal(x_admin_token):
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        now = utc_now()
        row = DamageReportDB(
            apartment=data.apartment,
            category=data.category,
            severity=data.severity,
            status="OPEN",
            description=data.description,
            estimated_cost=data.estimated_cost,
            responsible_party=data.responsible_party,
            evidence_urls=data.evidence_urls or [],
            created_at=now,
            updated_at=now,
            created_by=_actor(x_admin_token),
            updated_by=_actor(x_admin_token),
        )
        db.add(row)
        db.flush()
        db.add(DamageAuditDB(damage_id=row.id, changed_at=now, changed_by=_actor(x_admin_token), action="CREATE", old_values=None, new_values={"status": "OPEN", "severity": data.severity}))
        db.commit()
        return {"status": "ok", "id": row.id}
    except Exception as exc:
        db.rollback()
        logger.exception("Damage creation failed")
        raise HTTPException(status_code=500, detail="Unable to create damage report") from exc


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
    old_values = {"status": row.status, "severity": row.severity, "responsible_party": row.responsible_party}
    if data.status is not None:
        if data.status not in DAMAGE_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")
        allowed = STATUS_TRANSITIONS.get(row.status, set())
        if data.status != row.status and data.status not in allowed:
            raise HTTPException(status_code=409, detail=f"Invalid status transition: {row.status} -> {data.status}")
        row.status = data.status
    if data.severity is not None:
        if data.severity not in DAMAGE_SEVERITIES:
            raise HTTPException(status_code=400, detail="Invalid severity")
        row.severity = data.severity
    if data.responsible_party is not None:
        row.responsible_party = data.responsible_party
    if data.description is not None:
        row.description = data.description
    if data.estimated_cost is not None:
        row.estimated_cost = data.estimated_cost
    if data.evidence_urls is not None:
        row.evidence_urls = data.evidence_urls
    row.updated_at = utc_now()
    row.updated_by = actor
    db.add(DamageAuditDB(damage_id=row.id, changed_at=row.updated_at, changed_by=actor, action="UPDATE", old_values=old_values, new_values={"status": row.status, "severity": row.severity, "responsible_party": row.responsible_party}))
    db.commit()
    return {"status": "ok", "id": row.id}


@app.post("/allocate")
def allocate(data: AllocationRequest, _: None = Depends(require_auth)):
    try:
        return assign_groups(data.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
