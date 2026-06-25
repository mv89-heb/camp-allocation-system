from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import pandas as pd

from app.models import ActualInventoryUpdate
from app.data_loader import load_required_inventory, load_actual_inventory, ACTUAL_INV_FILE
from app.logic import compute_gaps

app = FastAPI()

os.makedirs("app/static", exist_ok=True)
os.makedirs("app/templates", exist_ok=True)
os.makedirs("data", exist_ok=True)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/analyze")
def analyze():
    try:
        req_df = load_required_inventory()
        act_df = load_actual_inventory()

        df = compute_gaps(req_df, act_df)
        df = df.fillna("")
        return df.to_dict(orient="records")
    except Exception as e:
        return {"error": f"❌ שגיאה בלתי צפויה: {str(e)}"}

@app.post("/update_actual")
def update_actual_inventory(data: ActualInventoryUpdate):
    if os.path.exists(ACTUAL_INV_FILE):
        df = pd.read_csv(ACTUAL_INV_FILE)
    else:
        df = pd.DataFrame(columns=["apartment", "beds", "mattresses", "closets", "ac_units", "ac_remotes"])

    new_data = data.model_dump()
    new_data["apartment"] = str(new_data["apartment"]).strip()
    
    if new_data["apartment"] in df["apartment"].astype(str).values:
        idx = df.index[df["apartment"].astype(str) == new_data["apartment"]].tolist()[0]
        for key, value in new_data.items():
            df.at[idx, key] = value
    else:
        df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)

    df.to_csv(ACTUAL_INV_FILE, index=False)
    return {"status": "success", "message": f"הנתונים עבור דירה {data.apartment} נשמרו בהצלחה!"}