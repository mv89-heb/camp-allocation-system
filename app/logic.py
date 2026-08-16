from __future__ import annotations

import pandas as pd


VALID_MODES = {"std", "plan"}
INVENTORY_FIELDS = ("beds", "mattresses", "closets", "ac_units", "ac_remotes")


def validate_mode(mode: str) -> str:
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of: {', '.join(sorted(VALID_MODES))}")
    return mode


def compute_gaps(req_df: pd.DataFrame, act_df: pd.DataFrame, mode: str = "std") -> pd.DataFrame:
    """Return one normalized row per requirement with requested/actual values and gaps."""
    validate_mode(mode)

    required_columns = {"apartment"}
    suffix = "_std" if mode == "std" else "_plan"
    required_columns.update(f"{field}{suffix}" for field in INVENTORY_FIELDS)
    missing = required_columns - set(req_df.columns)
    if missing:
        raise ValueError(f"requirements is missing columns: {', '.join(sorted(missing))}")

    if "apartment" not in act_df.columns:
        act_df = pd.DataFrame(columns=["apartment", *INVENTORY_FIELDS])

    req = req_df.copy()
    act = act_df.copy()
    req["apartment"] = req["apartment"].astype(str).str.strip()
    act["apartment"] = act["apartment"].astype(str).str.strip()

    if req["apartment"].duplicated().any():
        duplicates = req.loc[req["apartment"].duplicated(), "apartment"].tolist()
        raise ValueError(f"duplicate requirements for apartment(s): {duplicates}")
    if act["apartment"].duplicated().any():
        act = act.drop_duplicates("apartment", keep="last")

    req = req[["apartment", *(f"{field}{suffix}" for field in INVENTORY_FIELDS)]].rename(
        columns={f"{field}{suffix}": f"{field}_req" for field in INVENTORY_FIELDS}
    )
    act = act[["apartment", *[field for field in INVENTORY_FIELDS if field in act.columns]]].rename(
        columns={field: f"{field}_act" for field in INVENTORY_FIELDS}
    )

    merged = req.merge(act, on="apartment", how="left", validate="one_to_one")

    for field in INVENTORY_FIELDS:
        for suffix_name in ("req", "act"):
            column = f"{field}_{suffix_name}"
            if column not in merged.columns:
                merged[column] = 0
            merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0).astype(int)
            if (merged[column] < 0).any():
                raise ValueError(f"negative inventory value found in {column}")

        merged[f"gap_{field}"] = merged[f"{field}_act"] - merged[f"{field}_req"]

    def determine_status(row: pd.Series) -> str:
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
