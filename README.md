# Camp Allocation System

מערכת FastAPI לניהול מלאי חדרים, חישוב פערים והקצאת קבוצות לפי קיבולת.

## מה השתנה בגרסה 2

- PostgreSQL/Neon הוא מקור האמת של המערכת; קבצי CSV אינם משמשים בזמן ריצה.
- בוטל `to_sql(..., if_exists="replace")` כדי למנוע מחיקת טבלאות ו-constraints.
- נוספה סכימת DB קנונית לדרישות, מצאי והיסטוריית שינויים.
- עדכוני מצאי כוללים ולידציה, transaction ו-audit trail.
- נוספה הגנת `ADMIN_TOKEN` ל-API כאשר המשתנה מוגדר.
- שגיאות פנימיות אינן מוחזרות ללקוח.
- `mode` מוגבל ל-`std` או `plan`.
- מנוע ההקצאה הפך לדטרמיניסטי ומונע overbooking.
- נוספו בדיקות regression ל-gap calculation ולהקצאות.
- הוסרה שכבת CSV runtime והסקריפטים הישנים שעלולים להחזיר את המערכת למצב לא עקבי.

## הרצה מקומית

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL="sqlite:///./data/inventory.db"
uvicorn app.main:app --reload
```

## מעבר ל-Neon / PostgreSQL

הגדר `DATABASE_URL` עם connection string של Neon. מומלץ להשתמש ב-`sslmode=require`.

לפני שימוש במערכת קיימת:

```powershell
python migrate_to_db.py
```

הסקריפט הוא idempotent ואינו מחליף טבלאות קיימות.

## אבטחה

בפריסה ציבורית חובה להגדיר `ADMIN_TOKEN` סודי וחזק. ה-UI ישתמש בו דרך header בשם `X-Admin-Token`.

מומלץ להגדיר גם `ALLOWED_HOSTS` לדומיינים המדויקים של השירות במקום `*`.

## API

- `GET /health` — בדיקת זמינות DB.
- `GET /analyze?mode=std|plan` — חישוב פערים.
- `POST /update_actual` — עדכון מצאי + audit.
- `GET /audit/{apartment}` — היסטוריית שינויים.
- `POST /allocate` — הקצאת קבוצות לפי קיבולת המיטות הנוכחית.

## בדיקות

```powershell
pytest -q
```

## מודל הנתונים

`requirements` מכיל את התקן הסטנדרטי והמתוכנן.

`actuals` מכיל את המצאי האחרון שנבדק, כולל זמן ושם מבצע הדיווח.

`inventory_audit` שומר כל שינוי משמעותי כדי שניתן יהיה לעקוב אחורה.

## השלב הבא

בקרת נזקים בחדרים צריכה להיבנות מעל אותה תשתית DB, ולא כטבלת CSV נוספת. מומלץ להוסיף מודול נפרד ל-`room_damage_reports`, קטגוריות נזק, חומרה, תמונות/מסמכים, סטטוס טיפול, עלות משוערת ועלות בפועל, והיסטוריית שינויי סטטוס.
