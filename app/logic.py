from __future__ import annotations

import pandas as pd


VALID_MODES = {"std", "plan"}
INVENTORY_FIELDS = ("beds", "mattresses", "closets", "ac_units", "ac_remotes")


def validate_mode(mode: str) -> str:
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of: {', '.join(sorted(VALID_MODES))}")
    return mode


def compute_gaps(req_df: pd.DataFrame, act_df: pd.DataFrame, mode: str = "std") -> pd.DataFrame:
    """Calculate inventory gaps while distinguishing unchecked inventory from real zero stock."""
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

    req = req[["apartment", *(f"{field}{suffix}" for field in INVENTORY_FIELDS)]].rename(
        columns={f"{field}{suffix}": f"{field}_req" for field in INVENTORY_FIELDS}
    )

    actual_columns = ["apartment", *[field for field in INVENTORY_FIELDS if field in act.columns]]
    if "checked_at" in act.columns:
        actual_columns.append("checked_at")
    if "checked_by" in act.columns:
        actual_columns.append("checked_by")

    act = act[actual_columns].rename(
        columns={field: f"{field}_act" for field in INVENTORY_FIELDS}
    )

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

    # checked_at is the source of truth for whether a room's physical inventory
    # was actually inspected. A row created by CSV/bootstrap with zeros but no
    # checked_at is therefore NOT treated as a confirmed shortage.
    if "checked_at" in merged.columns:
        merged["inventory_checked"] = merged["checked_at"].notna()
    else:
        merged["inventory_checked"] = False

    merged["inventory_checked"] = merged["inventory_checked"].fillna(False).astype(bool)

    for field in INVENTORY_FIELDS:
        merged[f"gap_{field}"] = merged[f"{field}_act"] - merged[f"{field}_req"]

    def determine_status(row: pd.Series) -> str:
        if not bool(row["inventory_checked"]):
            return "לא נבדק"
        gaps = [row[f"gap_{field}"] for field in INVENTORY_FIELDS]
        if any(g < 0 for g in gaps):
            return "חסר"
        if any(g > 0 for g in gaps):
            return "עודף"
        return "תקין"

    merged["status"] = merged.apply(determine_status, axis=1)
    return merged.sort_values("apartment", kind="stable").reset_index(drop=True)


def dataframe_to_records(df: pd.DataFrame) -> list[dict]:
    return df.where(pd.notna(df), None).to_dict(orient="records")
