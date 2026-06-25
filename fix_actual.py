import pandas as pd

inv = pd.read_csv("data/inventory.csv")

# לוקחים רק בפועל
actual = inv[["apartment", "beds_actual", "mattresses_actual"]].copy()

actual = actual.rename(columns={
    "beds_actual": "beds",
    "mattresses_actual": "mattresses"
})

# עמודות נוספות (כרגע 0)
actual["closets"] = 0
actual["ac_units"] = 0
actual["ac_remotes"] = 0

actual.to_csv("data/actual_inventory.csv", index=False)

print("✅ actual_inventory.csv עודכן מהנתונים האמיתיים")