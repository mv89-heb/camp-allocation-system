import os
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, JSON, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/inventory.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine_kwargs = {
    "pool_pre_ping": True,
    "future": True,
}
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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
