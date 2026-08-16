from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class Allocation:
    room: str
    group: str
    campers: int
    remaining_capacity: int


def sort_rooms(rooms_df: pd.DataFrame) -> pd.DataFrame:
    required = {"room", "actual_capacity"}
    missing = required - set(rooms_df.columns)
    if missing:
        raise ValueError(f"rooms data is missing columns: {', '.join(sorted(missing))}")
    result = rooms_df[["room", "actual_capacity"]].copy()
    result["room"] = result["room"].astype(str).str.strip()
    result["actual_capacity"] = pd.to_numeric(result["actual_capacity"], errors="coerce").fillna(0).astype(int)
    result = result[result["actual_capacity"] >= 0]
    return result.sort_values(["actual_capacity", "room"], ascending=[False, True], kind="stable").reset_index(drop=True)


def assign_groups(rooms_df: pd.DataFrame, groups: Iterable[dict], allow_split: bool = False) -> list[dict]:
    """Greedy capacity allocation with deterministic ordering and explicit unassigned groups."""
    rooms = sort_rooms(rooms_df)
    normalized_groups = []
    for group in groups:
        name = str(group.get("name", "")).strip()
        size = int(group.get("size", 0))
        if not name or size <= 0:
            raise ValueError("every group must have a non-empty name and a positive size")
        normalized_groups.append({"name": name, "size": size})

    # Largest groups first reduces fragmentation and makes the result deterministic.
    normalized_groups.sort(key=lambda item: (-item["size"], item["name"]))
    remaining = {row.room: int(row.actual_capacity) for row in rooms.itertuples()}
    assignments: list[dict] = []

    for group in normalized_groups:
        name, size = group["name"], group["size"]
        candidates = [room for room in remaining if remaining[room] >= size]
        if candidates:
            room = min(candidates, key=lambda candidate: (remaining[candidate] - size, candidate))
            remaining[room] -= size
            assignments.append({
                "room": room,
                "group": name,
                "campers": size,
                "remaining_capacity": remaining[room],
                "status": "assigned",
            })
            continue

        if allow_split:
            left = size
            for room in sorted(remaining, key=lambda candidate: (-remaining[candidate], candidate)):
                if left <= 0:
                    break
                take = min(left, remaining[room])
                if take <= 0:
                    continue
                remaining[room] -= take
                assignments.append({
                    "room": room,
                    "group": name,
                    "campers": take,
                    "remaining_capacity": remaining[room],
                    "status": "partial" if take < left else "assigned",
                })
                left -= take
            if left == 0:
                continue

        assignments.append({
            "room": None,
            "group": name,
            "campers": size,
            "remaining_capacity": None,
            "status": "unassigned",
        })

    return assignments
