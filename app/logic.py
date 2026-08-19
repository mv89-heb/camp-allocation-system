from __future__ import annotations

import pandas as pd


VALID_MODES = {"std", "plan"}
INVENTORY_FIELDS = ("beds", "mattresses", "closets", "ac_units", "ac_remotes")


def validate_mode(mode: str) -> str:
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of: {', '.join(sorted(VALID_MODES))}")
    return mode


def compute_gaps(req_df: pd.DataFrame, act_df: pd.DataFrame, mode: str = "std") -> pd.DataFrame:
    """Calculate room-level inventory while evaluating the official standard per unit.

    A standard unit can contain one room or multiple rooms (for example 101-102).
    Physical inventory remains stored and reported per room, but compliance is
    calculated from the sum of the rooms in the same standard unit.
    """
    validate_mode(mode)
    suffix = "_std" if mode == "std" else "_plan"
    required_columns = {"apartment", *(f"{field}{suffix}" for field in INVENTORY_FIELDS)}
    missing = required_columns - set(req_df.columns)
    if missing:
        raise ValueError(f"requirements is missing columns: {', '.join(sorted(missing))}")

    req = req_df.copy()
    act = act_df.copy() if act_df is not None else pd.DataFrame()
    req["apartment"] = req["apartment"].astype(str).str.strip()

    if "apartment" not in act.columns:
        act = pd.DataFrame(columns=["apartment", *INVENTORY_FIELDS, "checked_at", "checked_by"])
    else:
        act["apartment"] = act["apartment"].astype(str).str.strip()

    if req["apartment"].duplicated().any():
        duplicates = req.loc[req["apartment"].duplicated(), "apartment"].tolist()
        raise ValueError(f"duplicate requirements for apartment(s): {duplicates}")
    if act["apartment"].duplicated().any():
        act = act.drop_duplicates("apartment", keep="last")

    for column, default in (("standard_unit_id", None), ("standard_unit_label", None)):
        if column not in req.columns:
            req[column] = req["apartment"]
        req[column] = req[column].fillna("").astype(str).str.strip()
        if default is None:
            req.loc[req[column] == "", column] = req.loc[req[column] == "", "apartment"]

    req = req[[
        "apartment", "standard_unit_id", "standard_unit_label",
        *[f"{field}{suffix}" for field in INVENTORY_FIELDS],
    ]].rename(columns={f"{field}{suffix}": f"{field}_req" for field in INVENTORY_FIELDS})

    actual_columns = ["apartment", *[field for field in INVENTORY_FIELDS if field in act.columns]]
    if "checked_at" in act.columns:
        actual_columns.append("checked_at")
    if "checked_by" in act.columns:
        actual_columns.append("checked_by")
    act = act[actual_columns].rename(columns={field: f"{field}_act" for field in INVENTORY_FIELDS})

    merged = req.merge(act, on="apartment", how="left", validate="one_to_one")

    for field in INVENTORY_FIELDS:
        req_col = f"{field}_req"
        act_col = f"{field}_act"
        if act_col not in merged.columns:
            merged[act_col] = 0
        merged[req_col] = pd.to_numeric(merged[req_col], errors="coerce").fillna(0).astype(int)
        merged[act_col] = pd.to_numeric(merged[act_col], errors="coerce").fillna(0).astype(int)
        if (merged[req_col] < 0).any() or (merged[act_col] < 0).any():
            raise ValueError(f"negative inventory value found for {field}")

    merged["inventory_checked"] = (
        merged["checked_at"].notna().fillna(False).astype(bool)
        if "checked_at" in merged.columns
        else False
    )

    # Keep legacy room-level fields for API compatibility. They are informational
    # only; official compliance is represented by unit_* fields below.
    for field in INVENTORY_FIELDS:
        merged[f"room_gap_{field}"] = merged[f"{field}_act"] - merged[f"{field}_req"]
        merged[f"gap_{field}"] = merged[f"room_gap_{field}"]

    unit_keys = merged["standard_unit_id"].astype(str).str.strip()
    unit_keys = unit_keys.mask(unit_keys == "", merged["apartment"])
    merged["standard_unit_id"] = unit_keys
    labels = merged["standard_unit_label"].astype(str).str.strip()
    merged["standard_unit_label"] = labels.mask(labels == "", merged["standard_unit_id"])

    # Official standard and actual stock are summed across every room belonging
    # to the same standard unit. No standard is duplicated onto each room.
    grouped = merged.groupby("standard_unit_id", sort=False, dropna=False)
    for field in INVENTORY_FIELDS:
        merged[f"unit_{field}_req"] = grouped[f"{field}_req"].transform("sum").astype(int)
        merged[f"unit_{field}_act"] = grouped[f"{field}_act"].transform("sum").astype(int)
        merged[f"unit_gap_{field}"] = merged[f"unit_{field}_act"] - merged[f"unit_{field}_req"]

    merged["unit_room_count"] = grouped["apartment"].transform("size").astype(int)
    merged["unit_checked_count"] = grouped["inventory_checked"].transform("sum").astype(int)
    merged["unit_inventory_complete"] = merged["unit_checked_count"] == merged["unit_room_count"]
    merged["unit_inventory_partial"] = (
        (merged["unit_checked_count"] > 0) & ~merged["unit_inventory_complete"]
    )

    def room_status(row: pd.Series) -> str:
        if not bool(row["inventory_checked"]):
            return "לא נבדק"
        gaps = [row[f"room_gap_{field}"] for field in INVENTORY_FIELDS]
        if any(g < 0 for g in gaps):
            return "חסר בחדר"
        if any(g > 0 for g in gaps):
            return "עודף בחדר"
        return "תקין בחדר"

    def unit_status(row: pd.Series) -> str:
        if not bool(row["unit_inventory_complete"]):
            if bool(row["unit_inventory_partial"]):
                return "הצמד נבדק חלקית"
            return "הצמד טרם נבדק"
        gaps = [row[f"unit_gap_{field}"] for field in INVENTORY_FIELDS]
        if any(g < 0 for g in gaps):
            return "חסר בצמד"
        if any(g > 0 for g in gaps):
            return "עודף בצמד"
        return "תקין בצמד"

    merged["room_status"] = merged.apply(room_status, axis=1)
    merged["unit_status"] = merged.apply(unit_status, axis=1)
    # `status` now means official standard-unit status. Consumers that relied on
    # the old field therefore automatically receive the correct compliance state.
    merged["status"] = merged["unit_status"]
    return merged.sort_values("apartment", kind="stable").reset_index(drop=True)


def dataframe_to_records(df: pd.DataFrame) -> list[dict]:
    return df.where(pd.notna(df), None).to_dict(orient="records")
