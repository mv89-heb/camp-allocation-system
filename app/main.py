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
    InventoryAuditDB,
    RequirementDB,
    engine,
    get_db,
    utc_now,
)
from app.logic import compute_gaps, dataframe_to_records
from app.models import ActualInventoryUpdate, AllocationRequest, HealthResponse
from app.rules import assign_groups


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("camp-allocation")

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Camp Allocation System", version="2.0.0", docs_url="/docs", redoc_url="/redoc")
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


def _legacy_column_map(table_name: str) -> dict[str, str]:
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return {}
    return {column["name"]: str(column["type"]) for column in inspector.get_columns(table_name)}


def ensure_schema() -> None:
    """Create the canonical schema and upgrade legacy columns without destructive replacement."""
    Base.metadata.create_all(bind=engine)
    requirements = _legacy_column_map("requirements")
    actuals = _legacy_column_map("actuals")

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
            for name, definition in additions.items():
                if name not in requirements:
                    conn.execute(text(f'ALTER TABLE requirements ADD COLUMN "{name}" {definition}'))
            # Legacy CSV schema used generic beds/mattresses/closets/ac_units/ac_remotes columns.
            if "beds" in requirements:
                conn.execute(text('UPDATE requirements SET beds_plan = COALESCE(beds_plan, CAST(beds AS INTEGER))'))
                conn.execute(text('UPDATE requirements SET beds_std = CASE WHEN CAST(beds AS INTEGER) < 4 THEN CAST(beds AS INTEGER) ELSE 4 END'))
            if "mattresses" in requirements:
                conn.execute(text('UPDATE requirements SET mattresses_plan = COALESCE(mattresses_plan, CAST(mattresses AS INTEGER))'))
                conn.execute(text('UPDATE requirements SET mattresses_std = CASE WHEN CAST(mattresses AS INTEGER) < 4 THEN CAST(mattresses AS INTEGER) ELSE 4 END'))
            if "closets" in requirements:
                conn.execute(text('UPDATE requirements SET closets_plan = COALESCE(closets_plan, CAST(closets AS INTEGER))'))
                conn.execute(text('UPDATE requirements SET closets_std = CASE WHEN CAST(closets AS INTEGER) < 4 THEN CAST(closets AS INTEGER) ELSE 4 END'))
            if "ac_units" in requirements:
                conn.execute(text('UPDATE requirements SET ac_units_plan = COALESCE(ac_units_plan, CAST(ac_units AS INTEGER))'))
                conn.execute(text('UPDATE requirements SET ac_units_std = CASE WHEN CAST(ac_units AS INTEGER) < 4 THEN CAST(ac_units AS INTEGER) ELSE 4 END'))
            if "ac_remotes" in requirements:
                conn.execute(text('UPDATE requirements SET ac_remotes_plan = COALESCE(ac_remotes_plan, CAST(ac_remotes AS INTEGER))'))
                conn.execute(text('UPDATE requirements SET ac_remotes_std = CASE WHEN CAST(ac_remotes AS INTEGER) < 1 THEN CAST(ac_remotes AS INTEGER) ELSE 1 END'))

    if actuals:
        with engine.begin() as conn:
            if "checked_at" not in actuals:
                conn.execute(text('ALTER TABLE actuals ADD COLUMN checked_at TIMESTAMP'))
            if "checked_by" not in actuals:
                conn.execute(text('ALTER TABLE actuals ADD COLUMN checked_by VARCHAR(120)'))


@app.on_event("startup")
def startup() -> None:
    ensure_schema()
    logger.info("Camp Allocation System started; auth_required=%s", AUTH_REQUIRED)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "auth_required": AUTH_REQUIRED})


@app.get("/health", response_model=HealthResponse)
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return HealthResponse(status="ok", database="ok", timestamp=utc_now())
    except Exception:
        logger.exception("Health check failed")
        raise HTTPException(status_code=503, detail="Database unavailable")


@app.get("/analyze")
def analyze(mode: str = "std", _: None = Depends(require_auth)):
    if mode not in {"std", "plan"}:
        raise HTTPException(status_code=400, detail="mode must be std or plan")
    try:
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
    actor = "admin"
    if x_admin_token:
        actor = "token-user"

    values = {
        "beds": data.beds,
        "mattresses": data.mattresses,
        "closets": data.closets,
        "ac_units": data.ac_units,
        "ac_remotes": data.ac_remotes,
    }

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
        db.add(InventoryAuditDB(
            apartment=apartment_name,
            changed_at=utc_now(),
            changed_by=actor,
            previous_values=previous,
            new_values=values,
        ))
        db.commit()
        return {"status": "success", "apartment": apartment_name, "checked_at": record.checked_at}
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Concurrent update detected; please retry")
    except Exception:
        db.rollback()
        logger.exception("Inventory update failed for apartment=%s", apartment_name)
        raise HTTPException(status_code=500, detail="Unable to save inventory")


@app.get("/audit/{apartment}")
def audit(apartment: str, db: Session = Depends(get_db), _: None = Depends(require_auth)):
    if not apartment.strip():
        raise HTTPException(status_code=400, detail="Apartment is required")
    rows = db.scalars(
        select(InventoryAuditDB)
        .where(InventoryAuditDB.apartment == apartment.strip())
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
    # Allocation is intentionally based on current inventory/capacity data, not on mutable CSV files.
    rows = db.execute(select(ActualDB.apartment, ActualDB.beds)).all()
    rooms = pd.DataFrame([{"room": apartment, "actual_capacity": beds} for apartment, beds in rows])
    if rooms.empty:
        return {"assignments": [], "unassigned_groups": [g.model_dump() for g in request.groups]}
    assignments = assign_groups(rooms, [group.model_dump() for group in request.groups], allow_split=request.allow_split)
    return {"assignments": assignments}
