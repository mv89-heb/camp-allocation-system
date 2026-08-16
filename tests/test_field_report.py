import pytest
from pydantic import ValidationError

from app.models import ActualInventoryUpdate, FieldRoomReportRequest, DamageCreateRequest


def test_field_room_report_accepts_same_room_damages():
    report = FieldRoomReportRequest(
        inventory=ActualInventoryUpdate(apartment="101", beds=4, mattresses=4, closets=4, ac_units=2, ac_remotes=2),
        damages=[DamageCreateRequest(apartment="101", category="HVAC", severity="HIGH", description="המזגן אינו עובד")],
    )
    assert report.inventory.apartment == "101"
    assert len(report.damages) == 1


def test_field_room_report_rejects_damage_for_another_room():
    with pytest.raises(ValidationError):
        FieldRoomReportRequest(
            inventory=ActualInventoryUpdate(apartment="101", beds=4),
            damages=[DamageCreateRequest(apartment="102", category="OTHER", severity="LOW", description="נזק בדלת")],
        )
