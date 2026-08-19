DAMAGE_CATALOG = {
    "FURNITURE": {"label": "ריהוט ופרזול", "subcategories": {
        "CABINETS": {"label": "ארונות", "items": ["ארון ראשי", "ארון ימני", "ארון שמאלי", "ארון פנימי", "ארון כניסה", "ארון משני / ספייר"]},
        "DRAWERS": {"label": "מגירות", "items": ["מגירה תחתונה", "מגירה תחתונה ימנית", "מגירה תחתונה שמאלית", "מגירה חסרה"]},
        "DOORS": {"label": "דלתות / ידיות / צירים", "items": ["דלת ימין", "דלת שמאל", "דלת ארון", "ידית ארון", "ציר דלת / ארון"]},
        "SHELVES": {"label": "מדפים", "items": ["מדף", "מדף עליון", "מדף באזור הדוש"]},
        "SHUTTERS": {"label": "תריסים / פתחי אוורור", "items": ["תריס", "מנגנון תריס", "חוט / רצועת גלילת תריס", "פתח אוורור"]},
        "STABILITY": {"label": "יציבות וחיזוק", "items": ["ארון מתנדנד", "חיזוק מבני"]},
        "OTHER": {"label": "אחר בריהוט", "items": []},
    }},
    "ELECTRICAL": {"label": "חשמל ותאורה", "subcategories": {
        "BULBS": {"label": "נורות", "items": ["נורה לא נדלקת", "נורה מהבהבת", "נורה בעוצמה נמוכה", "נורה תקולה"]},
        "FIXTURES": {"label": "בתי נורה / גופי תאורה", "items": ["בית נורה", "גוף תאורה"]},
        "OUTLETS": {"label": "שקעים חשמליים", "items": ["שקע חשמלי פתוח", "שקע חשמלי חשוף", "שקע חשמלי לא בטיחותי"]},
        "OTHER": {"label": "אחר בחשמל", "items": []},
    }},
    "PLUMBING": {"label": "אינסטלציה", "subcategories": {
        "FAUCETS": {"label": "ברזים", "items": ["ברז", "ברז ימני", "ברז שלישי משמאל", "ברז קיצוני שמאלי"]},
        "WATER_FLOW": {"label": "לחץ / ספיקת מים", "items": ["ספיקת מים חמים נמוכה", "לחץ מים חלש", "ספיקת מים נמוכה"]},
        "SHOWER": {"label": "מקלחת / דוש", "items": ["ראש מקלחת / דוש חסר", "ראש מקלחת"]},
        "TOILET": {"label": "אסלה והדחה", "items": ["לחץ מים באסלה", "מנגנון הדחה", "אסלה"]},
        "OTHER": {"label": "אחר באינסטלציה", "items": []},
    }},
    "HVAC": {"label": "מיזוג אוויר", "subcategories": {
        "CENTRAL": {"label": "מיזוג מרכזי / קופסת בקרה", "items": ["קופסת בקרה לשלט המרכזי", "קופסת בקרה משוחררת", "שלט מרכזי"]},
        "INDIVIDUAL": {"label": "מזגן נפרד", "items": ["יחידת מזגן", "שלט מזגן"]},
        "OTHER": {"label": "אחר במיזוג", "items": []},
    }},
    "CLEANLINESS": {"label": "ניקיון וגימור", "subcategories": {
        "CLEANING": {"label": "ניקיון", "items": ["ניקוי קיר", "ניקיון ייעודי", "לכלוך"]},
        "PAINT": {"label": "צבע וגימור", "items": ["תיקון צבע", "תיקון גימור", "צבע סביב בית נורה"]},
        "OTHER": {"label": "אחר בניקיון וגימור", "items": []},
    }},
    "SAFETY": {"label": "בטיחות והיערכות לשריפות", "subcategories": {
        "EMERGENCY_EXIT": {"label": "יציאת חירום", "items": ["מיקום מיטה ליד יציאת חירום", "גישה ליציאת חירום"]},
        "ELECTRICAL": {"label": "בטיחות חשמלית", "items": ["שקע חשמלי חשוף", "שקע חשמלי פתוח"]},
        "OTHER": {"label": "אחר בבטיחות", "items": []},
    }},
    "STRUCTURE": {"label": "מבנה ותחזוקה", "subcategories": {
        "STRUCTURAL": {"label": "ליקוי מבני", "items": ["חיזוק מבני", "חלק שבור", "חלק מפורק"]},
        "OTHER": {"label": "אחר במבנה", "items": []},
    }},
    "OTHER": {"label": "אחר", "subcategories": {"GENERAL": {"label": "כללי", "items": ["אחר"]}}},
}

def catalog_for_api():
    return DAMAGE_CATALOG

def validate_catalog_selection(category, subcategory=None, item_name=None):
    category = (category or "").upper()
    if category not in DAMAGE_CATALOG:
        raise ValueError("Unknown damage category")
    if not subcategory:
        return
    sub = DAMAGE_CATALOG[category]["subcategories"].get(subcategory)
    if sub is None:
        raise ValueError("Unknown damage subcategory")
    if item_name and sub["items"] and item_name not in sub["items"]:
        raise ValueError("Unknown damage item for selected subcategory")
