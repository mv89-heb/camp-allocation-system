import os
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, JSON, Numeric, String, Text, create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

ENVIRONMENT = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "")).strip().lower()
IS_PRODUCTION = ENVIRONMENT in {"production", "prod"} or os.getenv("RENDER", "").strip().lower() == "true"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    if IS_PRODUCTION:
        raise RuntimeError("DATABASE_URL is required in production. Configure the Neon PostgreSQL connection string.")
    DATABASE_URL = "sqlite:///./data/inventory.db"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine_kwargs = {"pool_pre_ping": True, "future": True}
if not DATABASE_URL.startswith("sqlite"):
    engine_kwargs.update({"pool_size": 5, "max_overflow": 10})
engine = create_engine(DATABASE_URL, connect_args=connect_args, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


class RequirementDB(Base):
    __tablename__ = "requirements"
    apartment = Column(String(120), primary_key=True, index=True)
    standard_unit_id = Column(String(120), nullable=False, default="")
    standard_unit_label = Column(String(240), nullable=False, default="")
    beds_std = Column(Integer, nullable=False, default=4)
    mattresses_std = Column(Integer, nullable=False, default=4)
    closets_std = Column(Integer, nullable=False, default=4)
    ac_mode = Column(String(20), nullable=False, default="CENTRAL")
    ac_units_std = Column(Integer, nullable=False, default=0)
    ac_remotes_std = Column(Integer, nullable=False, default=0)
    ac_control_boxes_std = Column(Integer, nullable=False, default=1)
    beds_plan = Column(Integer, nullable=False, default=6)
    mattresses_plan = Column(Integer, nullable=False, default=6)
    closets_plan = Column(Integer, nullable=False, default=6)
    ac_units_plan = Column(Integer, nullable=False, default=0)
    ac_remotes_plan = Column(Integer, nullable=False, default=0)
    ac_control_boxes_plan = Column(Integer, nullable=False, default=1)


class ActualDB(Base):
    __tablename__ = "actuals"
    apartment = Column(String(120), primary_key=True, index=True)
    beds = Column(Integer, nullable=False, default=0)
    mattresses = Column(Integer, nullable=False, default=0)
    closets = Column(Integer, nullable=False, default=0)
    ac_units = Column(Integer, nullable=False, default=0)
    ac_remotes = Column(Integer, nullable=False, default=0)
    ac_control_boxes = Column(Integer, nullable=False, default=0)
    checked_at = Column(DateTime(timezone=True), nullable=True)
    checked_by = Column(String(120), nullable=True)


class InventoryAuditDB(Base):
    __tablename__ = "inventory_audit"
    id = Column(Integer, primary_key=True, autoincrement=True)
    apartment = Column(String(120), nullable=False, index=True)
    changed_at = Column(DateTime(timezone=True), nullable=False)
    changed_by = Column(String(120), nullable=False)
    previous_values = Column(JSON, nullable=True)
    new_values = Column(JSON, nullable=False)


class DamageReportDB(Base):
    __tablename__ = "damage_reports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    apartment = Column(String(120), nullable=False, index=True)
    category = Column(String(40), nullable=False, index=True)
    subcategory = Column(String(60), nullable=True, index=True)
    item_name = Column(String(160), nullable=True, index=True)
    severity = Column(String(20), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    description = Column(Text, nullable=False)
    estimated_cost = Column(Numeric(12, 2), nullable=True)
    actual_cost = Column(Numeric(12, 2), nullable=True)
    responsible_party = Column(String(160), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    evidence_urls = Column(JSON, nullable=False, default=list)
    reported_by = Column(String(120), nullable=False)
    reported_at = Column(DateTime(timezone=True), nullable=False)
    updated_by = Column(String(120), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class DamageAuditDB(Base):
    __tablename__ = "damage_audit"
    id = Column(Integer, primary_key=True, autoincrement=True)
    damage_id = Column(Integer, nullable=False, index=True)
    apartment = Column(String(120), nullable=False, index=True)
    changed_at = Column(DateTime(timezone=True), nullable=False)
    changed_by = Column(String(120), nullable=False)
    action = Column(String(30), nullable=False)
    previous_values = Column(JSON, nullable=True)
    new_values = Column(JSON, nullable=False)


def ensure_grouped_room_schema() -> None:
    """Upgrade existing databases without replacing any existing data."""
    inspector = inspect(engine)
    if not inspector.has_table("requirements"):
        return
    req_columns = {c["name"] for c in inspector.get_columns("requirements")}
    actual_columns = {c["name"] for c in inspector.get_columns("actuals")} if inspector.has_table("actuals") else set()
    damage_columns = {c["name"] for c in inspector.get_columns("damage_reports")} if inspector.has_table("damage_reports") else set()
    req_additions = {
        "standard_unit_id": "VARCHAR(120)",
        "standard_unit_label": "VARCHAR(240)",
        "ac_mode": "VARCHAR(20) DEFAULT 'CENTRAL'",
        "ac_control_boxes_std": "INTEGER DEFAULT 1",
        "ac_control_boxes_plan": "INTEGER DEFAULT 1",
    }
    actual_additions = {"ac_control_boxes": "INTEGER DEFAULT 0"}
    damage_additions = {
        "subcategory": "VARCHAR(60)",
        "item_name": "VARCHAR(160)",
    }
    with engine.begin() as conn:
        for name, definition in req_additions.items():
            if name not in req_columns:
                conn.execute(text(f'ALTER TABLE requirements ADD COLUMN "{name}" {definition}'))
        for name, definition in actual_additions.items():
            if name not in actual_columns:
                conn.execute(text(f'ALTER TABLE actuals ADD COLUMN "{name}" {definition}'))
        for name, definition in damage_additions.items():
            if name not in damage_columns:
                conn.execute(text(f'ALTER TABLE damage_reports ADD COLUMN "{name}" {definition}'))
        conn.execute(text(
            'UPDATE requirements SET "standard_unit_id" = COALESCE(NULLIF("standard_unit_id", \'\'), apartment) '
            'WHERE "standard_unit_id" IS NULL OR "standard_unit_id" = \'\''
        ))
        conn.execute(text(
            'UPDATE requirements SET "standard_unit_label" = COALESCE(NULLIF("standard_unit_label", \'\'), "standard_unit_id", apartment) '
            'WHERE "standard_unit_label" IS NULL OR "standard_unit_label" = \'\''
        ))
        conn.execute(text(
            'UPDATE requirements SET "ac_mode" = COALESCE(NULLIF("ac_mode", \'\'), \'CENTRAL\') '
            'WHERE "ac_mode" IS NULL OR "ac_mode" = \'\''
        ))
        conn.execute(text(
            'UPDATE requirements SET "ac_control_boxes_std" = COALESCE("ac_control_boxes_std", 1), '
            '"ac_control_boxes_plan" = COALESCE("ac_control_boxes_plan", 1)'
        ))


ensure_grouped_room_schema()


def database_backend() -> str:
    return "postgresql" if DATABASE_URL.startswith(("postgresql://", "postgresql+")) else "sqlite"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
