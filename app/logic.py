import pandas as pd

def compute_gaps(req_df, act_df, mode="std"):
    """
    mode: 'std' (תקן קבוע של 4 לחדר) או 'plan' (תקן מתוכנן מורחב של 6 לחדר)
    """
    req_df["apartment"] = req_df["apartment"].astype(str).str.strip()
    act_df["apartment"] = act_df["apartment"].astype(str).str.strip()

    # בחירת הסיומת של העמודות לפי התקן המבוקש
    suffix = "_std" if mode == "std" else "_plan"
    
    # חילוץ העמודות המתאימות ושינוי שמות אחיד לצורך המיזוג והחישוב
    req_filtered = req_df[["apartment", f"beds{suffix}", f"mattresses{suffix}", f"closets{suffix}", f"ac_units{suffix}", f"ac_remotes{suffix}"]].copy()
    req_filtered = req_filtered.rename(columns={
        f"beds{suffix}": "beds_req", 
        f"mattresses{suffix}": "mattresses_req", 
        f"closets{suffix}": "closets_req", 
        f"ac_units{suffix}": "ac_units_req", 
        f"ac_remotes{suffix}": "ac_remotes_req"
    })

    act_filtered = act_df.rename(columns={
        "beds": "beds_act", 
        "mattresses": "mattresses_act", 
        "closets": "closets_act", 
        "ac_units": "ac_units_act", 
        "ac_remotes": "ac_remotes_act"
    })

    # מיזוג שתי הטבלאות
    merged = req_filtered.merge(act_filtered, on="apartment", how="left")

    # השלמת ערכים ריקים ומניעת בעיות NaN ב-JSON
    cols = ["beds_act", "mattresses_act", "closets_act", "ac_units_act", "ac_remotes_act",
            "beds_req", "mattresses_req", "closets_req", "ac_units_req", "ac_remotes_req"]
    for col in cols:
        if col not in merged.columns:
            merged[col] = 0
        merged[col] = pd.to_numeric(merged[col], errors='coerce').fillna(0).astype(int)

    # חישוב פערים
    merged["gap_beds"] = merged["beds_act"] - merged["beds_req"]
    merged["gap_mattresses"] = merged["mattresses_act"] - merged["mattresses_req"]
    merged["gap_closets"] = merged["closets_act"] - merged["closets_req"]
    merged["gap_ac_units"] = merged["ac_units_act"] - merged["ac_units_req"]
    merged["gap_ac_remotes"] = merged["ac_remotes_act"] - merged["ac_remotes_req"]

    def determine_status(row):
        gaps = [row["gap_beds"], row["gap_mattresses"], row["gap_closets"], row["gap_ac_units"], row["gap_ac_remotes"]]
        if any(g < 0 for g in gaps):
            return "❌ חסר"
        if any(g > 0 for g in gaps):
            return "🟢 עודף"
        return "✅ תקין"

    merged["status"] = merged.apply(determine_status, axis=1)
    return merged
