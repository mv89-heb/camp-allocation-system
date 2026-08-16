import pandas as pd
import pytest

from app.logic import compute_gaps


def requirements():
    return pd.DataFrame([
        {
            "apartment": "101",
            "beds_std": 4, "mattresses_std": 4, "closets_std": 4, "ac_units_std": 4, "ac_remotes_std": 1,
            "beds_plan": 6, "mattresses_plan": 6, "closets_plan": 6, "ac_units_plan": 4, "ac_remotes_plan": 1,
        }
    ])


def actuals():
    return pd.DataFrame([{"apartment": "101", "beds": 3, "mattresses": 4, "closets": 5, "ac_units": 4, "ac_remotes": 1}])


def test_std_gap_and_status():
    result = compute_gaps(requirements(), actuals(), "std").iloc[0]
    assert result["gap_beds"] == -1
    assert result["gap_closets"] == 1
    assert result["status"] == "חסר"


def test_plan_mode():
    result = compute_gaps(requirements(), actuals(), "plan").iloc[0]
    assert result["gap_beds"] == -3
    assert result["gap_mattresses"] == -2


def test_invalid_mode_is_rejected():
    with pytest.raises(ValueError):
        compute_gaps(requirements(), actuals(), "anything")
