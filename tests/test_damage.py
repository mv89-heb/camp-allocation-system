import pytest
from pydantic import ValidationError

from app.models import DamageCreateRequest, DamageUpdateRequest


def test_damage_create_validation_and_normalization():
    item = DamageCreateRequest(
        apartment="ירושלים 201",
        category="hvac",
        severity="high",
        description="המזגן אינו מקרר והיחידה משמיעה רעש חריג",
        estimated_cost="850.50",
        evidence_urls=["https://example.com/photo.jpg"],
    )
    assert item.category == "HVAC"
    assert item.severity == "HIGH"
    assert float(item.estimated_cost) == 850.50


def test_damage_rejects_invalid_evidence_url():
    with pytest.raises(ValidationError):
        DamageCreateRequest(
            apartment="ירושלים 201",
            category="OTHER",
            severity="LOW",
            description="נזק קטן בדלת החדר",
            evidence_urls=["javascript:alert(1)"],
        )


def test_damage_close_requires_resolution_notes():
    with pytest.raises(ValidationError):
        DamageUpdateRequest(status="CLOSED")


def test_damage_update_allows_resolution_with_notes():
    item = DamageUpdateRequest(status="RESOLVED", resolution_notes="החלק הוחלף והחדר נבדק")
    assert item.status == "RESOLVED"
