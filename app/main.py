from __future__ import annotations

# Existing imports / app remain unchanged above.
# This file update adds structured damage filtering and summary endpoints below
# the existing damage routes.

from sqlalchemy import select, func

# ... existing code ...

@app.get("/damages/summary")
def damage_summary(
    apartment: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    item_name: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_auth),
):
    query = select(
        DamageReportDB.category,
        DamageReportDB.subcategory,
        DamageReportDB.item_name,
        DamageReportDB.status,
        func.count(DamageReportDB.id).label("count"),
    )
    if apartment:
        query = query.where(DamageReportDB.apartment == apartment.strip())
    if category:
        query = query.where(DamageReportDB.category == category.upper())
    if subcategory:
        query = query.where(DamageReportDB.subcategory == subcategory.strip())
    if item_name:
        query = query.where(DamageReportDB.item_name == item_name.strip())
    if status:
        query = query.where(DamageReportDB.status == status.upper())
    if severity:
        query = query.where(DamageReportDB.severity == severity.upper())
    rows = db.execute(
        query.group_by(
            DamageReportDB.category,
            DamageReportDB.subcategory,
            DamageReportDB.item_name,
            DamageReportDB.status,
        ).order_by(func.count(DamageReportDB.id).desc())
    ).all()
    return [
        {
            "category": row.category,
            "subcategory": row.subcategory,
            "item_name": row.item_name,
            "status": row.status,
            "count": int(row.count),
        }
        for row in rows
    ]
