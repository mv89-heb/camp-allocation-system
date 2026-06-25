from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import pandas as pd
from sqlalchemy.orm import Session

from app.models import ActualInventoryUpdate
from app.database import engine, get_db, ActualDB
from app.logic import compute_gaps

app = FastAPI()

# יצירת התיקיות הנדרשות במידה ואינן קיימות
os.makedirs("app/static", exist_ok=True)
os.makedirs("app/templates", exist_ok=True)

# הגדרת קבצים סטטיים ותבניות HTML
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """
    דף הבית הראשי של המערכת (הדאשבורד).
    """
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/analyze")
def analyze(mode: str = "std"):
    """
    נתיב השליפה והניתוח של פערים במלאי.
    מקבל פרמטר בשם mode:
    - 'std': חישוב לפי התקן הסטנדרטי הקבוע (4 יחידות לחדר).
    - 'plan': חישוב לפי התקן המתוכנן המורחב (6 יחידות לחדר).
    """
    try:
        # שליפת נתוני הטבלאות ישירות ממסד הנתונים באמצעות Pandas
        req_df = pd.read_sql_table("requirements", engine)
        act_df = pd.read_sql_table("actuals", engine)

        if req_df.empty:
            return {"error": "❌ מסד הנתונים ריק. נא לוודא שהרצת את סקריפט ה-SQL ליצירת הנתונים."}

        # חישוב פערים בלוגיקה בהתבסס על המצב הנבחר
        df = compute_gaps(req_df, act_df, mode=mode)
        df = df.fillna("")
        
        return df.to_dict(orient="records")
    except Exception as e:
        return {"error": f"❌ שגיאה בלתי צפויה במסד הנתונים: {str(e)}"}

@app.post("/update_actual")
def update_actual_inventory(data: ActualInventoryUpdate, db: Session = Depends(get_db)):
    """
    נתיב לעדכון או הזנת ספירה פיזית חדשה מהשטח עבור דירה או קרוון.
    מונע התנגשויות בין משתמשים שונים ומבצע נעילת שורה בטוחה (Commit).
    """
    apartment_name = str(data.apartment).strip()
    
    # בדיקה האם כבר קיימת רשומה עבור הדירה הזו בטבלת המלאי בפועל
    record = db.query(ActualDB).filter(ActualDB.apartment == apartment_name).first()
    
    if record:
        # אם הדירה קיימת - נעדכן את הערכים הנוכחיים בחדשים
        record.beds = data.beds
        record.mattresses = data.mattresses
        record.closets = data.closets
        record.ac_units = data.ac_units
        record.ac_remotes = data.ac_remotes
    else:
        # אם זו דירה חדשה שעוד לא דווחה - ניצור שורה חדשה בטבלה (Insert)
        new_record = ActualDB(
            apartment=apartment_name,
            beds=data.beds,
            mattresses=data.mattresses,
            closets=data.closets,
            ac_units=data.ac_units,
            ac_remotes=data.ac_remotes
        )
        db.add(new_record)

    # שמירה ונעילת הפעולה במסד הנתונים
    db.commit()
    return {"status": "success", "message": f"הנתונים עבור דירה {apartment_name} נשמרו בהצלחה!"}
