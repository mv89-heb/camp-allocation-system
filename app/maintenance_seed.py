from __future__ import annotations

from sqlalchemy import select

from app.database import DamageAuditDB, DamageReportDB, RequirementDB, SessionLocal, utc_now

SOURCE = "central-maintenance-report-2026-08-19"

ISSUES = [
    ("אילת 107", "FURNITURE", "תקלות תפעוליות בדלת הימנית ובמגירה התחתונה של הארון הראשי."),
    ("אילת 107", "FURNITURE", "ארון משני (ספייר) פגום, כולל מדף שבור הדורש תיקון או החלפה."),
    ("אילת 108", "ELECTRICAL", "בית מנורה מנותק ויוצא מקו הקיר."),
    ("אילת 108", "FURNITURE", "מנגנון תריס תקול שאינו פועל כשורה."),
    ("אשדוד 105", "FURNITURE", "מנגנון תריס פגום שאינו יורד או פועל כהלכה."),
    ("אשדוד 105", "FURNITURE", "מגירה תחתונה בצד ימין של הארון הימני אינה תקינה."),
    ("באר שבע 102", "ELECTRICAL", "נורת תאורה מהבהבת."),
    ("אשקלון 104", "ELECTRICAL", "נורת תאורה מהבהבת."),
    ("אשקלון 103", "FURNITURE", "ארון שמאלי: מדף עליון אינו מונח כיאות במסילה."),
    ("אשקלון 103", "ELECTRICAL", "נורת תאורה מהבהבת."),
    ("אשקלון 103", "ELECTRICAL", "חשיפה בנקודת שקע חשמלי — דורש בדיקת בטיחות."),
    ("אשקלון 103", "FURNITURE", "קריעה ברצועת/חוט גלילת התריס."),
    ("באר שבע 101", "PLUMBING", "ספיקת מים חמים נמוכה בברז; זרם המים הקרים תקין."),
    ("באר שבע 101", "CLEANLINESS", "נדרש טיפול ניקיון ייעודי לקיר השמאלי."),
    ("באר שבע 101", "ELECTRICAL", "נורת תאורה מהבהבת ותקולה."),
    ("באר שבע 101", "FURNITURE", "ליקויי סגירה במגירות התחתונות בשני ארונות שונים."),
    ("באר שבע 101", "FURNITURE", "ארון כניסה במצב שבור ומפורק לחלוטין."),
    ("יבנה 212", "FURNITURE", "ארון ימני: חסרה מגירה."),
    ("יבנה 212", "FURNITURE", "ארון שמאלי: דלת שמאלית אינה תקינה."),
    ("יבנה 212", "ELECTRICAL", "בית נורה סמוך למיטה השמאלית ליד החלון יצא ממקומו בקיר."),
    ("יבנה 211", "ELECTRICAL", "בית נורה ליד המיטה הימנית, סמוך לחלון, אינו נדלק."),
    ("יבנה 211", "ELECTRICAL", "נורה ליד המיטה השמאלית, בקרבת הארונות, מהבהבת לאורך זמן."),
    ("יבנה 211", "FURNITURE", "ארון שמאלי: דלת תקולה."),
    ("יבנה 211", "FURNITURE", "ארון פנימי בחדר: דלת שמאלית יצאה ממקומה."),
    ("בני ברק 210", "PLUMBING", "ברז ימני: ספיקת לחץ מים חלשה."),
    ("בני ברק 209", "ELECTRICAL", "בית נורה ליד המיטה, סמוך ליציאת חירום, פועל בעוצמה נמוכה מאוד — בקושי נדלק."),
    ("בני ברק 209", "FURNITURE", "ידית ארון ימני תקולה."),
    ("בני ברק 209", "ELECTRICAL", "בית נורה / גוף תאורה ליד המיטה הימנית סמוך לחלון."),
    ("בני ברק 209", "FURNITURE", "מנגנון תריס תקול לחלוטין."),
    ("בני ברק 209", "STRUCTURE", "הסדרת מיקום המיטה הסמוכה ליציאת חירום — הנושא הוסדר.", "RESOLVED", "טופל והוסדר לפי דוח התקלות המרכזי."),
    ("יפו 208", "FURNITURE", "ארון צד שמאל: מגירה תחתונה תקולה."),
    ("יפו 208", "FURNITURE", "מנגנון תריס פגום; כבל/חוט הגלילה אינו פועל כראוי."),
    ("יפו 207", "FURNITURE", "תריס תקוע במצבו."),
    ("יפו 207", "FURNITURE", "ארון שמאלי: מגירה תחתונה שמאלית אינה תקינה."),
    ("רחובות 206", "FURNITURE", "ארון ימני: דלת יצאה ממקומה."),
    ("רחובות 206", "FURNITURE", "ארון שמאלי: חסרה מגירה."),
    ("רחובות 206", "PLUMBING", "ברז קיצוני שמאלי תקול עקב ספיקת מים נמוכה."),
    ("חברון 204", "FURNITURE", "ארון שמאלי: חסרים מדפים."),
    ("חברון 204", "FURNITURE", "ארון נוסף: דלת שמאלית מנותקת ממקומה."),
    ("חברון 204", "HVAC", "קופסת הבקרה של השלט המרכזי למזגן משוחררת ממקומה."),
    ("חברון 204", "PLUMBING", "חסר ראש מקלחת (דוש)."),
    ("חברון 204", "ELECTRICAL", "בית נורה ליד המיטה התנתק מקו הקיר."),
    ("חברון 203", "PLUMBING", "חסר ראש מקלחת."),
    ("חברון 203", "ELECTRICAL", "נורה ליד המיטה בצד ימין אינה פועלת."),
    ("חברון 203", "ELECTRICAL", "שקע חשמלי פתוח המהווה מפגע בטיחותי."),
    ("ירושלים 202", "FURNITURE", "חבל/חוט תריס קרוע."),
    ("ירושלים 202", "FURNITURE", "ארון פנימי הסמוך למיטות מתנדנד ודורש חיזוק מבני."),
    ("ירושלים 202", "PLUMBING", "לחץ מים חלש באסלה השמאלית; תקלה מלאה במנגנון ההדחה באסלה הימנית — אין ירידת מים כלל."),
    ("ירושלים 201", "FURNITURE", "ארון ימני: חסרה מגירה."),
    ("ירושלים 201", "FURNITURE", "ארון פנימי ליד המיטות: במצב שבור."),
    ("ירושלים 201", "FURNITURE", "חדר רחצה: חסר מדף באזור הדוש."),
    ("ירושלים 201", "ELECTRICAL", "שקע חשמלי פתוח ולא בטיחותי."),
    ("ירושלים 201", "CLEANLINESS", "נדרשות עבודות תיקון צבע וגימור מסביב לבית הנורה בצד ימין של החדר."),
    ("ירושלים 201", "PLUMBING", "ברז שלישי מצד שמאל אינו תקין."),
]


def seed_maintenance_issues() -> tuple[int, int]:
    """Idempotently import the supplied central maintenance report.

    Existing records are never duplicated and existing operational records are never overwritten.
    Returns (inserted, skipped_missing_rooms).
    """
    db = SessionLocal()
    inserted = 0
    skipped = 0
    try:
        known_rooms = set(db.scalars(select(RequirementDB.apartment)).all())
        for issue in ISSUES:
            apartment, category, description = issue[:3]
            status = issue[3] if len(issue) > 3 else "OPEN"
            resolution_notes = issue[4] if len(issue) > 4 else None
            if apartment not in known_rooms:
                skipped += 1
                continue
            exists = db.scalar(
                select(DamageReportDB.id).where(
                    DamageReportDB.apartment == apartment,
                    DamageReportDB.description == description,
                    DamageReportDB.reported_by == SOURCE,
                )
            )
            if exists is not None:
                continue
            now = utc_now()
            row = DamageReportDB(
                apartment=apartment,
                category=category,
                severity="MEDIUM",
                status=status,
                description=description,
                resolution_notes=resolution_notes,
                evidence_urls=[],
                reported_by=SOURCE,
                reported_at=now,
                updated_by=SOURCE,
                updated_at=now,
                resolved_at=now if status == "RESOLVED" else None,
            )
            db.add(row)
            db.flush()
            db.add(DamageAuditDB(
                damage_id=row.id,
                apartment=apartment,
                changed_at=now,
                changed_by=SOURCE,
                action="IMPORTED_CENTRAL_REPORT",
                previous_values=None,
                new_values={"status": status, "severity": "MEDIUM", "description": description},
            ))
            inserted += 1
        db.commit()
        return inserted, skipped
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
