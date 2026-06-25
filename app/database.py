import os
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

# המערכת תבדוק אם יש כתובת של מסד נתונים בענן (Render). אם לא, היא תיצור SQLite מקומי.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/inventory.db")

# תיקון תאימות קטן לשרתי PostgreSQL של Render
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# חיבור למסד הנתונים
connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# -----------------
# מודלים של הטבלאות
# -----------------
class ActualDB(Base):
    __tablename__ = "actuals"
    apartment = Column(String, primary_key=True, index=True)
    beds = Column(Integer, default=0)
    mattresses = Column(Integer, default=0)
    closets = Column(Integer, default=0)
    ac_units = Column(Integer, default=0)
    ac_remotes = Column(Integer, default=0)

class RequirementDB(Base):
    __tablename__ = "requirements"
    apartment = Column(String, primary_key=True, index=True)
    beds = Column(Integer, default=0)
    mattresses = Column(Integer, default=0)
    closets = Column(Integer, default=0)
    ac_units = Column(Integer, default=0)
    ac_remotes = Column(Integer, default=0)

# פונקציית עזר לפתיחה וסגירה בטוחה של החיבור
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
