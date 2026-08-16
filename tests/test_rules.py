import pandas as pd

from app.rules import assign_groups


def test_largest_groups_are_allocated_without_overbooking():
    rooms = pd.DataFrame([
        {"room": "A", "actual_capacity": 6},
        {"room": "B", "actual_capacity": 4},
    ])
    result = assign_groups(rooms, [{"name": "G1", "size": 4}, {"name": "G2", "size": 6}])
    assert all(item["status"] == "assigned" for item in result)
    assert sum(item["campers"] for item in result) == 10
    assert all(item["remaining_capacity"] >= 0 for item in result)


def test_unassigned_group_is_explicit():
    rooms = pd.DataFrame([{"room": "A", "actual_capacity": 3}])
    result = assign_groups(rooms, [{"name": "G1", "size": 5}])
    assert result == [{
        "room": None,
        "group": "G1",
        "campers": 5,
        "remaining_capacity": None,
        "status": "unassigned",
    }]
