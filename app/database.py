import os
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, JSON, Numeric, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


ENVIRONMENT = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "")).strip().lower()
IS_PRODUCTION = ENVIRONMENT in {"production", "prod"} or os.getenv("RENDER", "").strip().lower() == "true"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
FIELD_TOKEN = os.getenv("FIELD_TOKEN", "").strip()

# Production must use the real Neon/PostgreSQL database.
if not DATABASE_URL:
    if IS_PRODUCTION:
        raise RuntimeError(
            "DATABASE_URL is required in production. Configure the Neon PostgreSQL connection string."
        )
    DATABASE_URL = "sqlite:///./data/inventory.db"

# Authentication is intentionally optional for the current field workflow.
# It can be re-enabled later without changing the data model.

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
    beds_std = Column(Integer, nullable=False, default=4)
    mattresses_std = Column(Integer, nullable=False, default=4)
    closets_std = Column(Integer, nullable=False, default=4)
    ac_units_std = Column(Integer, nullable=False, default=4)
    ac_remotes_std = Column(Integer, nullable=False, default=1)
    beds_plan = Column(Integer, nullable=False, default=6)
    mattresses_plan = Column(Integer, nullable=False, default=6)
    closets_plan = Column(Integer, nullable=False, default=6)
    ac_units_plan = Column(Integer, nullable=False, default=4)
    ac_remotes_plan = Column(Integer, nullable=False, default=1)


class ActualDB(Base):
    __tablename__ = "actuals"

    apartment = Column(String(120), primary_key=True, index=True)
    beds = Column(Integer, nullable=False, default=0)
    mattresses = Column(Integer, nullable=False, default=0)
    closets = Column(Integer, nullable=False, default=0)
    ac_units = Column(Integer, nullable=False, default=0)
    ac_remotes = Column(Integer, nullable=False, default=0)
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
