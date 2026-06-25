import os
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker

# שליפת כתובת ה-Database ממשתני הסביבה (Render/Neon). אם לא קיים, תיווצר סביבת SQLite מקומית.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/inventory.db")

# תיקון תאימות קל עבור שרתי PostgreSQL בענן
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class RequirementDB(Base):
    __tablename__ = "requirements"
    apartment = Column(String, primary_key=True, index=True)
    # תקן סטנדרטי קבוע
    beds_std = Column(Integer, default=4)
    mattresses_std = Column(Integer, default=4)
    closets_std = Column(Integer, default=4)
    ac_units_std = Column(Integer, default=4)
    ac_remotes_std = Column(Integer, default=1)
    # תקן קיבולת מתוכנן
    beds_plan = Column(Integer, default=6)
    mattresses_plan = Column(Integer, default=6)
    closets_plan = Column(Integer, default=6)
    ac_units_plan = Column(Integer, default=4)
    ac_remotes_plan = Column(Integer, default=1)

class ActualDB(Base):
    __tablename__ = "actuals"
    apartment = Column(String, primary_key=True, index=True)
    beds = Column(Integer, default=0)
    mattresses = Column(Integer, default=0)
    closets = Column(Integer, default=0)
    ac_units = Column(Integer, default=0)
    ac_remotes = Column(Integer, default=0)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
