import pandas as pd
import os

REQ_INV_FILE = "data/inventory.csv"
ACTUAL_INV_FILE = "data/actual_inventory.csv"

def load_required_inventory():
    if not os.path.exists(REQ_INV_FILE):
        raise FileNotFoundError("קובץ הדרישות חסר. אנא הרץ את הסקריפט build_db.py תחילה.")
    return pd.read_csv(REQ_INV_FILE)

def load_actual_inventory():
    if not os.path.exists(ACTUAL_INV_FILE):
        return pd.DataFrame(columns=["apartment", "beds", "mattresses", "closets", "ac_units", "ac_remotes"])
    return pd.read_csv(ACTUAL_INV_FILE)