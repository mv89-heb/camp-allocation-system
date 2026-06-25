import pandas as pd
import os

os.makedirs("data", exist_ok=True)

# הנתונים חולצו במדויק מתמונות המסמך שלך
data = [
    *[{"apartment": f"קרוון {i}", "beds": 6, "mattresses": 6, "closets": 6, "ac_units": 3, "ac_remotes": 1} for i in range(1, 8)],
    *[{"apartment": str(i), "beds": 10, "mattresses": 10, "closets": 10, "ac_units": 5, "ac_remotes": 1} for i in [101, 102, 103, 104, 106]],
    {"apartment": "105", "beds": 8, "mattresses": 8, "closets": 8, "ac_units": 4, "ac_remotes": 1},
    *[{"apartment": str(i), "beds": 10, "mattresses": 10, "closets": 10, "ac_units": 5, "ac_remotes": 1} for i in [201, 202, 203, 204, 206]],
    {"apartment": "205", "beds": 8, "mattresses": 8, "closets": 8, "ac_units": 4, "ac_remotes": 1},
    *[{"apartment": str(i), "beds": 10, "mattresses": 10, "closets": 10, "ac_units": 5, "ac_remotes": 1} for i in [301, 302, 303, 304, 306]],
    {"apartment": "305", "beds": 8, "mattresses": 8, "closets": 8, "ac_units": 4, "ac_remotes": 1},
    *[{"apartment": str(i), "beds": 10, "mattresses": 10, "closets": 10, "ac_units": 5, "ac_remotes": 1} for i in [401, 402, 403, 404, 406]],
    {"apartment": "405", "beds": 8, "mattresses": 8, "closets": 8, "ac_units": 4, "ac_remotes": 1},
    {"apartment": "501", "beds": 8, "mattresses": 8, "closets": 8, "ac_units": 4, "ac_remotes": 1},
    *[{"apartment": str(i), "beds": 10, "mattresses": 10, "closets": 10, "ac_units": 5, "ac_remotes": 1} for i in [502, 503, 504, 505, 506]],
    {"apartment": "601", "beds": 8, "mattresses": 8, "closets": 8, "ac_units": 4, "ac_remotes": 1},
    *[{"apartment": str(i), "beds": 10, "mattresses": 10, "closets": 10, "ac_units": 5, "ac_remotes": 1} for i in [602, 603, 604, 605, 606]],
    {"apartment": "מדריכים 1", "beds": 4, "mattresses": 4, "closets": 4, "ac_units": 4, "ac_remotes": 1},
    {"apartment": "מדריכים 2", "beds": 4, "mattresses": 4, "closets": 4, "ac_units": 4, "ac_remotes": 1},
    {"apartment": "מדריכים 3", "beds": 3, "mattresses": 3, "closets": 3, "ac_units": 3, "ac_remotes": 1},
    {"apartment": "מדריכים 4", "beds": 2, "mattresses": 2, "closets": 2, "ac_units": 2, "ac_remotes": 1},
    {"apartment": "מדריכים 5", "beds": 2, "mattresses": 2, "closets": 2, "ac_units": 2, "ac_remotes": 1},
    {"apartment": "מדריכים 6", "beds": 1, "mattresses": 1, "closets": 1, "ac_units": 1, "ac_remotes": 1},
    {"apartment": "אב בית", "beds": 1, "mattresses": 1, "closets": 3, "ac_units": 3, "ac_remotes": 3},
    {"apartment": "בנות שירות", "beds": 6, "mattresses": 6, "closets": 6, "ac_units": 3, "ac_remotes": 1},
]

df = pd.DataFrame(data)
df.to_csv("data/inventory.csv", index=False)
print("✅ קובץ inventory.csv (תקן הדירות הנדרש) נוצר בהצלחה מתוך הנתונים במסמך!")