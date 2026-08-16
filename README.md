# Camp Allocation System

מערכת FastAPI לניהול מלאי חדרים, חישוב פערים, הקצאת קבוצות ובקרת נזקים בחדרים.

## מה כולל המערכת

### מלאי
- PostgreSQL/Neon כמקור אמת; CSV אינו משמש בזמן ריצה.
- תקן סטנדרטי ותקן מתוכנן.
- עדכון מצאי עם ולידציה, transaction ו-audit trail.
- הבחנה בין נתוני תקן לבין נתוני מצאי בפועל.
- Snapshot הנתונים ב-`data/inventory.csv` וב-`data/actual_inventory.csv` מסונכרן ל-Neon אוטומטית בעת עליית Uvicorn בפרודקשן.
- הסנכרון אינו מוחק טבלאות ואינו דורס מצאי שכבר סומן כבדיקה פיזית.
- שורות snapshot עם אפס אמיתי נשארות "לא נבדק" ולא הופכות אוטומטית לחוסר מאומת.

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

### פירוט פריטי נזק
לכל דיווח ניתן לנהל פריטים נפרדים:
- שם פריט ותיאור
- כמות
- עלות משוערת ליחידה
- עלות בפועל ליחידה
- סטטוס: פתוח / תוקן / הוחלף / הוסר
- קישורי תמונות או מסמכים

### הצעות מחיר
לכל נזק ניתן לשמור מספר הצעות מחיר:
- ספק
- מספר הצעה
- מחיר
- תוקף ההצעה
- סטטוס: התקבלה / נבחרה / נדחתה / פג תוקף
- קישור למסמך ההצעה
- הערות

המערכת מחשבת גם סכומי עלות מצטברים לפריטים ולהצעות שאינן נדחות.

### אבטחה
- `ADMIN_TOKEN` מגן על API תפעולי כאשר הוא מוגדר.
- ולידציה בצד השרת לכל קלט.
- כתובות ראיות/מסמכים מוגבלות ל-HTTP/HTTPS.
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

בפרודקשן, `sitecustomize.py` מפעיל את `bootstrap_neon.py` אוטומטית לפני Uvicorn כאשר `DATABASE_URL` מוגדר. לכן הסנכרון אינו תלוי ב-Start Command שנשמר ידנית ב-Render.

## API

### מלאי והקצאה
- `GET /health` — בדיקת DB.
- `GET /analyze?mode=std|plan` — חישוב פערי מלאי.
- `POST /update_actual` — עדכון מצאי + audit.
- `GET /audit/{apartment}` — היסטוריית מלאי.
- `POST /allocate` — הקצאת קבוצות.

### נזקים
- `GET /damages` — רשימת דיווחי נזק עם סינון.
- `POST /damages` — פתיחת דיווח נזק.
- `GET /damages/{damage_id}` — פרטי נזק.
- `PATCH /damages/{damage_id}` — עדכון נזק וסטטוס.
- `GET /damages/{damage_id}/audit` — היסטוריית הנזק.
- `GET /damages/{damage_id}/summary` — נזק + פריטים + הצעות מחיר + audit + סיכומי עלות.

### פריטי נזק
- `GET /damages/{damage_id}/items` — פריטי הנזק.
- `POST /damages/{damage_id}/items` — הוספת פריט.
- `PATCH /damages/{damage_id}/items/{item_id}` — עדכון פריט.

### הצעות מחיר
- `GET /damages/{damage_id}/quotes` — הצעות מחיר.
- `POST /damages/{damage_id}/quotes` — הוספת הצעה.
- `PATCH /damages/{damage_id}/quotes/{quote_id}` — עדכון הצעה.

## מסד הנתונים

`Base.metadata.create_all()` יוצר את הטבלאות החדשות באופן לא-הרסני בעת האתחול. לא נעשה שימוש ב-`DROP TABLE` או ב-`if_exists="replace"`.

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
- `damage_items` — פירוט פריטי נזק ועלויות.
- `repair_quotes` — הצעות מחיר לתיקון.
