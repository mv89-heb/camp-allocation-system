import pandas as pd

def compute_gaps(req_df, act_df):
    req_df["apartment"] = req_df["apartment"].astype(str).str.strip()
    act_df["apartment"] = act_df["apartment"].astype(str).str.strip()

    # שינוי שמות עמודות
    req_df = req_df.rename(columns={
        "beds": "beds_req", "mattresses": "mattresses_req", 
        "closets": "closets_req", "ac_units": "ac_units_req", "ac_remotes": "ac_remotes_req"
    })
    act_df = act_df.rename(columns={
        "beds": "beds_act", "mattresses": "mattresses_act", 
        "closets": "closets_act", "ac_units": "ac_units_act", "ac_remotes": "ac_remotes_act"
    })

    # מיזוג
    merged = req_df.merge(act_df, on="apartment", how="left")

    # השלמת נתונים חסרים ל-0 *עבור כל* העמודות הרלוונטיות למניעת שגיאות חישוב ו-JSON NaN
    cols_to_fill = ["beds_act", "mattresses_act", "closets_act", "ac_units_act", "ac_remotes_act",
                    "beds_req", "mattresses_req", "closets_req", "ac_units_req", "ac_remotes_req"]
    for col in cols_to_fill:
        if col not in merged.columns:
            merged[col] = 0
        # הפיכה למספר והחלפת NaN ב-0
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