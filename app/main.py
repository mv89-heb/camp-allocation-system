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

from app.database import ActualDB, Base, InventoryAuditDB, RequirementDB, engine, get_db, utc_now
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

app = FastAPI(title="Camp Allocation System", version="2.0.0")
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
            # Legacy tables used generic columns. Copy them unconditionally into the new plan
            # columns so the default value does not mask the original source data.
            legacy_map = {
                "beds": ("beds_std", "beds_plan", 4),
                "mattresses": ("mattresses_std", "mattresses_plan", 4),
                "closets": ("closets_std", "closets_plan", 4),
                "ac_units": ("ac_units_std", "ac_units_plan", 4),
                "ac_remotes": ("ac_remotes_std", "ac_remotes_plan", 1),
            }
            for legacy, (std_col, plan_col, std_cap) in legacy_map.items():
                if legacy in existing:
                    conn.execute(text(
                        f'UPDATE requirements SET "{plan_col}" = CAST("{legacy}" AS INTEGER), '
                        f'"{std_col}" = CASE WHEN CAST("{legacy}" AS INTEGER) < :cap '
                        f'THEN CAST("{legacy}" AS INTEGER) ELSE :cap END'
                    ), {"cap": std_cap})

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
def update_actual_inventory(data: ActualInventoryUpdate, db: Session = Depends(get_db), x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    if not _safe_token_equal(x_admin_token):
        raise HTTPException(status_code=401, detail="Authentication required")
    apartment_name = data.apartment
    actor = "admin" if not x_admin_token else "token-user"
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
    rows = db.scalars(select(InventoryAuditDB).where(InventoryAuditDB.apartment == apartment).order_by(InventoryAuditDB.changed_at.desc()).limit(100)).all()
    return [{
        "id": row.id,
        "apartment": row.apartment,
        "changed_at": row.changed_at.astimezone(timezone.utc).isoformat(),
        "changed_by": row.changed_by,
        "previous_values": row.previous_values,
        "new_values": row.new_values,
    } for row in rows]


@app.post("/allocate")
def allocate(request: AllocationRequest, db: Session = Depends(get_db), _: None = Depends(require_auth)):
    rows = db.execute(select(ActualDB.apartment, ActualDB.beds)).all()
    rooms = pd.DataFrame([{"room": apartment, "actual_capacity": beds} for apartment, beds in rows])
    assignments = assign_groups(rooms, [group.model_dump() for group in request.groups], allow_split=request.allow_split) if not rooms.empty else []
    return {"assignments": assignments}
