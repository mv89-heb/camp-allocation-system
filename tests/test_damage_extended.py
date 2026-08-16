from datetime import date

import pytest
from pydantic import ValidationError

from app.damage_extended import DamageItemCreate, RepairQuoteCreate


def test_damage_item_accepts_photo_urls_and_costs():
    item = DamageItemCreate(
        item_name="מזגן בחדר",
        quantity=2,
        estimated_unit_cost="450.00",
        evidence_urls=["https://example.com/photo.jpg"],
    )
    assert item.quantity == 2
    assert str(item.estimated_unit_cost) == "450.00"
    assert item.evidence_urls[0].startswith("https://")


def test_damage_item_rejects_non_http_evidence():
    with pytest.raises(ValidationError):
        DamageItemCreate(item_name="שבר", evidence_urls=["file:///C:/secret.jpg"])


def test_repair_quote_requires_positive_vendor_and_valid_url():
    quote = RepairQuoteCreate(
        vendor="ספק תיקונים",
        quoted_cost="1250.00",
        valid_until=date(2026, 9, 1),
        evidence_url="https://example.com/quote.pdf",
    )
    assert quote.vendor == "ספק תיקונים"
    assert str(quote.quoted_cost) == "1250.00"


def test_repair_quote_rejects_invalid_status():
    with pytest.raises(ValidationError):
        RepairQuoteCreate(vendor="ספק", quoted_cost=100, status="APPROVED")
