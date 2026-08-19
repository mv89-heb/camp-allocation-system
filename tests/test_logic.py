import pandas as pd
import pytest

from app.logic import compute_gaps


def requirements():
    return pd.DataFrame([
        {"apartment": "101", "standard_unit_id": "101-102", "standard_unit_label": "חדרים 101-102", "beds_std": 4, "mattresses_std": 4, "closets_std": 4, "ac_units_std": 4, "ac_remotes_std": 1, "beds_plan": 6, "mattresses_plan": 6, "closets_plan": 6, "ac_units_plan": 4, "ac_remotes_plan": 1},
        {"apartment": "102", "standard_unit_id": "101-102", "standard_unit_label": "חדרים 101-102", "beds_std": 4, "mattresses_std": 4, "closets_std": 4, "ac_units_std": 4, "ac_remotes_std": 1, "beds_plan": 6, "mattresses_plan": 6, "closets_plan": 6, "ac_units_plan": 4, "ac_remotes_plan": 1},
    ])


def actuals():
    return pd.DataFrame([
        {"apartment": "101", "beds": 2, "mattresses": 2, "closets": 2, "ac_units": 2, "ac_remotes": 0, "checked_at": "2026-08-19T08:00:00Z"},
        {"apartment": "102", "beds": 2, "mattresses": 2, "closets": 2, "ac_units": 2, "ac_remotes": 1, "checked_at": "2026-08-19T08:05:00Z"},
    ])


def test_grouped_standard_is_summed_once():
    result = compute_gaps(requirements(), actuals(), "std")
    first = result[result["apartment"] == "101"].iloc[0]
    assert first["unit_beds_req"] == 8
    assert first["unit_beds_act"] == 4
    assert first["unit_gap_beds"] == -4
    assert first["unit_status"] == "חסר בצמד"
    assert first["unit_room_count"] == 2


def test_each_room_remains_independently_reportable():
    result = compute_gaps(requirements(), actuals(), "std")
    room_101 = result[result["apartment"] == "101"].iloc[0]
    room_102 = result[result["apartment"] == "102"].iloc[0]
    assert room_101["beds_act"] == 2
    assert room_102["beds_act"] == 2
    assert bool(room_101["inventory_checked"])
    assert bool(room_102["inventory_checked"])


def test_partial_pair_is_not_reported_as_complete():
    partial = actuals().iloc[[0]].copy()
    result = compute_gaps(requirements(), partial, "std")
    row = result[result["apartment"] == "101"].iloc[0]
    assert row["unit_checked_count"] == 1
    assert bool(row["unit_inventory_partial"])
    assert not bool(row["unit_inventory_complete"])
    assert row["unit_status"] == "הצמד נבדק חלקית"


def test_plan_mode_sums_plan_standard():
    result = compute_gaps(requirements(), actuals(), "plan")
    row = result[result["apartment"] == "101"].iloc[0]
    assert row["unit_beds_req"] == 12
    assert row["unit_mattresses_req"] == 12


def test_invalid_mode_is_rejected():
    with pytest.raises(ValueError):
        compute_gaps(requirements(), actuals(), "anything")
