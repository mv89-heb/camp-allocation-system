# Camp Allocation System

מערכת FastAPI לניהול מלאי חדרים, חישוב פערים, הקצאת קבוצות ובקרת נזקים בחדרים.

## מה כולל המערכת

### מלאי
- PostgreSQL/Neon כמקור אמת; CSV אינו משמש בזמן ריצה.
- תקן סטנדרטי ותקן מתוכנן.
- עדכון מצאי עם ולידציה, transaction ו-audit trail.
- הבחנה בין נתוני תקן לבין נתוני מצאי בפועל.

### הקצאת קבוצות
- הקצאה דטרמיניסטית לפי קיבולת מיטות.
- מניעת overbooking.
- תמיכה בהקצאה מפוצלת כאשר `allow_split=true`.
- קבוצות שלא ניתן לשבץ מוחזרות במפורש כ-`unassigned`.

### בקרת נזקים
כל דיווח נזק נשמר במסד הנתונים וקשור ישירות לחדר/דירה.

השדות כוללים:
- חדר / דירה
- קטגוריה: ריהוט, חשמל, אינסטלציה, מבנה, ניקיון, מיזוג, אחר
- חומרה: נמוכה, בינונית, גבוהה, קריטית
- תיאור הנזק
- סטטוס: פתוח → בדיקה → בטיפול → טופל → סגור
- עלות משוערת
- עלות בפועל
- אחראי / ספק
- הערות טיפול
- קישורי תמונות/ראיות
- מדווח ומועד הדיווח
- מועד עדכון ומועד סגירה
- היסטוריית שינויים מלאה

### אבטחה
- `ADMIN_TOKEN` מגן על API תפעולי כאשר הוא מוגדר.
- ולידציה בצד השרת לכל קלט.
- אין החזרת חריגות DB גולמיות ללקוח.
- `ALLOWED_HOSTS` ניתן להגדרה לפריסה.

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

```powershell
python migrate_to_db.py
```

הסקריפט idempotent ואינו משתמש ב-`if_exists="replace"`.

## API

- `GET /health` — בדיקת DB.
- `GET /analyze?mode=std|plan` — חישוב פערי מלאי.
- `POST /update_actual` — עדכון מצאי + audit.
- `GET /audit/{apartment}` — היסטוריית מלאי.
- `POST /allocate` — הקצאת קבוצות.
- `GET /damages` — רשימת דיווחי נזק עם סינון.
- `POST /damages` — פתיחת דיווח נזק.
- `GET /damages/{damage_id}` — פרטי נזק.
- `PATCH /damages/{damage_id}` — עדכון נזק וסטטוס.
- `GET /damages/{damage_id}/audit` — היסטוריית הנזק.

## סטטוסי נזק

המערכת אינה מאפשרת קפיצות שרירותיות בין סטטוסים. מעבר לסגירה/טיפול דורש הערות טיפול.

## בדיקות

```powershell
pytest -q
```

GitHub Actions מריץ את הבדיקות בכל push ל-main או ל-branch העבודה ובכל Pull Request.

## מודל נתונים

- `requirements` — התקנים.
- `actuals` — המצאי האחרון שנבדק.
- `inventory_audit` — היסטוריית מלאי.
- `damage_reports` — דיווחי נזק.
- `damage_audit` — היסטוריית נזק מלאה.

## השלב הבא

לאחר אימות מודול בקרת הנזקים, ניתן להרחיב אותו לניהול תמונות/מסמכים בקבצים, אומדן נזק מפורט לפי פריט, הצעות מחיר, אישור תיקון, עלויות בפועל, וסגירת חדר רק לאחר בדיקת תקינות חוזרת.
