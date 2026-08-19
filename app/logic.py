from __future__ import annotations

import pandas as pd

VALID_MODES = {"std", "plan"}
BASE_INVENTORY_FIELDS = ("beds", "mattresses", "closets")
AC_INVENTORY_FIELDS = ("ac_units", "ac_remotes", "ac_control_boxes")
INVENTORY_FIELDS = BASE_INVENTORY_FIELDS + AC_INVENTORY_FIELDS


def validate_mode(mode: str) -> str:
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of: {', '.join(sorted(VALID_MODES))}")
    return mode


def _normalise_ac_requirements(req: pd.DataFrame, suffix: str) -> pd.DataFrame:
    """Make the AC standard explicit.

    CENTRAL rooms are checked by control-box count. INDIVIDUAL rooms are checked
    by AC-unit/remote counts. Legacy rows without ac_mode are treated as CENTRAL
    so the field workflow does not falsely require four individual AC units.
    """
    req = req.copy()
    if "ac_mode" not in req.columns:
        req["ac_mode"] = "CENTRAL"
    req["ac_mode"] = req["ac_mode"].fillna("CENTRAL").astype(str).str.upper()
    req.loc[~req["ac_mode"].isin({"CENTRAL", "INDIVIDUAL"}), "ac_mode"] = "CENTRAL"

    for field in AC_INVENTORY_FIELDS:
        col = f"{field}{suffix}"
        if col not in req.columns:
            req[col] = 0

    central = req["ac_mode"] == "CENTRAL"
    # Central AC: ignore legacy individual-unit requirements and require one
    # control box by default. Individual AC rooms retain their explicit counts.
    req.loc[central, f"ac_units{suffix}"] = 0
    req.loc[central, f"ac_remotes{suffix}"] = 0
    req.loc[central & (pd.to_numeric(req[f"ac_control_boxes{suffix}"], errors="coerce").fillna(0) <= 0), f"ac_control_boxes{suffix}"] = 1
    req.loc[~central, f"ac_control_boxes{suffix}"] = 0
    return req


def compute_gaps(req_df: pd.DataFrame, act_df: pd.DataFrame, mode: str = "std") -> pd.DataFrame:
    validate_mode(mode)
    suffix = "_std" if mode == "std" else "_plan"
    req = req_df.copy()
    act = act_df.copy() if act_df is not None else pd.DataFrame()
    required_columns = {"apartment", *(f"{field}{suffix}" for field in BASE_INVENTORY_FIELDS)}
    missing = required_columns - set(req.columns)
    if missing:
        raise ValueError(f"requirements is missing columns: {', '.join(sorted(missing))}")

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

    for column in ("standard_unit_id", "standard_unit_label"):
        if column not in req.columns:
            req[column] = req["apartment"]
        req[column] = req[column].fillna("").astype(str).str.strip()
        req.loc[req[column] == "", column] = req.loc[req[column] == "", "apartment"]

    req = _normalise_ac_requirements(req, suffix)
    required_all = {"apartment", *(f"{field}{suffix}" for field in INVENTORY_FIELDS)}
    missing = required_all - set(req.columns)
    if missing:
        raise ValueError(f"requirements is missing columns: {', '.join(sorted(missing))}")

    req = req[["apartment", "standard_unit_id", "standard_unit_label", "ac_mode", *[f"{field}{suffix}" for field in INVENTORY_FIELDS]]]
    req = req.rename(columns={f"{field}{suffix}": f"{field}_req" for field in INVENTORY_FIELDS})

    actual_columns = ["apartment", *[field for field in INVENTORY_FIELDS if field in act.columns]]
    for field in INVENTORY_FIELDS:
        if field not in act.columns:
            act[field] = 0
    actual_columns = ["apartment", *INVENTORY_FIELDS]
    if "checked_at" in act.columns:
        actual_columns.append("checked_at")
    if "checked_by" in act.columns:
        actual_columns.append("checked_by")
    act = act[actual_columns].rename(columns={field: f"{field}_act" for field in INVENTORY_FIELDS})

    merged = req.merge(act, on="apartment", how="left", validate="one_to_one")
    for field in INVENTORY_FIELDS:
        req_col, act_col = f"{field}_req", f"{field}_act"
        if act_col not in merged.columns:
            merged[act_col] = 0
        merged[req_col] = pd.to_numeric(merged[req_col], errors="coerce").fillna(0).astype(int)
        merged[act_col] = pd.to_numeric(merged[act_col], errors="coerce").fillna(0).astype(int)
        if (merged[req_col] < 0).any() or (merged[act_col] < 0).any():
            raise ValueError(f"negative inventory value found for {field}")

    merged["inventory_checked"] = merged["checked_at"].notna().fillna(False).astype(bool) if "checked_at" in merged.columns else False

    for field in INVENTORY_FIELDS:
        merged[f"room_gap_{field}"] = merged[f"{field}_act"] - merged[f"{field}_req"]
        merged[f"gap_{field}"] = merged[f"room_gap_{field}"]

    unit_keys = merged["standard_unit_id"].astype(str).str.strip().mask(lambda s: s == "", merged["apartment"])
    merged["standard_unit_id"] = unit_keys
    labels = merged["standard_unit_label"].astype(str).str.strip().mask(lambda s: s == "", merged["standard_unit_id"])
    merged["standard_unit_label"] = labels

    grouped = merged.groupby("standard_unit_id", sort=False, dropna=False)
    for field in INVENTORY_FIELDS:
        merged[f"unit_{field}_req"] = grouped[f"{field}_req"].transform("sum").astype(int)
        merged[f"unit_{field}_act"] = grouped[f"{field}_act"].transform("sum").astype(int)
        merged[f"unit_gap_{field}"] = merged[f"unit_{field}_act"] - merged[f"unit_{field}_req"]

    merged["unit_room_count"] = grouped["apartment"].transform("size").astype(int)
    merged["unit_checked_count"] = grouped["inventory_checked"].transform("sum").astype(int)
    merged["unit_inventory_complete"] = merged["unit_checked_count"] == merged["unit_room_count"]
    merged["unit_inventory_partial"] = (merged["unit_checked_count"] > 0) & ~merged["unit_inventory_complete"]

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
            return "הצמד נבדק חלקית" if bool(row["unit_inventory_partial"]) else "הצמד טרם נבדק"
        gaps = [row[f"unit_gap_{field}"] for field in INVENTORY_FIELDS]
        if any(g < 0 for g in gaps):
            return "חסר בצמד"
        if any(g > 0 for g in gaps):
            return "עודף בצמד"
        return "תקין בצמד"

    merged["room_status"] = merged.apply(room_status, axis=1)
    merged["unit_status"] = merged.apply(unit_status, axis=1)
    merged["status"] = merged["unit_status"]
    return merged.sort_values("apartment", kind="stable").reset_index(drop=True)


def dataframe_to_records(df: pd.DataFrame) -> list[dict]:
    return df.where(pd.notna(df), None).to_dict(orient="records")
